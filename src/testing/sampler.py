"""
Sampling engine.

Timing convention: with n samples at frequency f, sample k is due at
offset k/f for k = 0..n-1. The first sample is taken immediately and the
last at (n-1)/f, so the samples occupy the window [0, n/f) and
total_duration_seconds = n/f is the length of that window.

Samples are scheduled against absolute targets from a monotonic clock
instead of accumulating sleep() in a loop, which drifts. Every sample
records its scheduled offset, actual start offset and measurement duration.
The report separates the ATTEMPTED schedule (all samples, whether their
measurement succeeded or not) from the count of successful measurements, so
a failing device cannot masquerade as a different sampling rate.

Clock and sleep are injectable so tests can use deterministic fakes.
"""
import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


class ConfigError(Exception):
    """The sampling configuration is missing or internally inconsistent."""


_WHOLE_TOLERANCE = 1e-6


def _require_positive_finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be positive and finite, got {value!r}")
    return float(value)


def _require_positive_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer, got {value!r}")
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value!r}")
    return value


def _require_whole_number_of_samples(value: float) -> int:
    """duration*frequency must land on a whole number of samples - fail loud."""
    nearest = round(value)
    if abs(value - nearest) > _WHOLE_TOLERANCE or nearest <= 0:
        raise ConfigError(
            f"total_duration_seconds * sampling_frequency_hz = {value!r} is not a "
            f"whole number of samples; adjust the values so the run contains an "
            f"integer number of samples"
        )
    return nearest


@dataclass
class SamplingConfig:
    measurements_count: Optional[int] = None
    total_duration_seconds: Optional[float] = None
    sampling_frequency_hz: Optional[float] = None
    overrun_tolerance_ratio: float = 0.5

    def resolve(self) -> "SamplingConfig":
        """
        Any TWO of (count, duration, frequency) determine the third:
          count    = duration * frequency   (must be a whole number of samples)
          duration = count / frequency
          frequency = count / duration
        If all three are given they must be consistent with the window
        convention (duration * frequency == count, within a small float
        tolerance); an inconsistent trio fails fast - silently "fixing" it
        would hide a user error.
        """
        if self.overrun_tolerance_ratio is None:
            raise ConfigError("overrun_tolerance_ratio must be set and positive")
        _require_positive_finite_number(
            self.overrun_tolerance_ratio, "overrun_tolerance_ratio"
        )
        count, duration, freq = (
            self.measurements_count,
            self.total_duration_seconds,
            self.sampling_frequency_hz,
        )
        if count is not None:
            count = _require_positive_int(count, "measurements_count")
        if duration is not None:
            duration = _require_positive_finite_number(duration, "total_duration_seconds")
        if freq is not None:
            freq = _require_positive_finite_number(freq, "sampling_frequency_hz")

        provided = sum(x is not None for x in (count, duration, freq))
        if provided < 2:
            raise ConfigError(
                "set at least two of: measurements_count, "
                "total_duration_seconds, sampling_frequency_hz"
            )
        if count is None:
            count = _require_whole_number_of_samples(duration * freq)
        if duration is None:
            duration = count / freq
        if freq is None:
            freq = count / duration
        if abs(duration * freq - count) > _WHOLE_TOLERANCE:
            raise ConfigError(
                f"inconsistent sampling config: count={count}, duration={duration}s, "
                f"frequency={freq}Hz - duration x frequency must equal count "
                f"(window [0, count/frequency)). Fix the config or drop one value."
            )
        return SamplingConfig(count, duration, freq, self.overrun_tolerance_ratio)


@dataclass
class Sample:
    index: int
    scheduled_at_offset: float       # seconds from run start, per the plan
    actual_at_offset: float          # seconds from run start when the measurement STARTED
    duration_seconds: float          # how long the measurement itself took
    value: Optional[float]           # None when the measurement failed
    error: Optional[str] = None

    @property
    def start_lateness_seconds(self) -> float:
        return self.actual_at_offset - self.scheduled_at_offset


@dataclass
class SamplingResult:
    samples: List[Sample] = field(default_factory=list)

    @property
    def values(self) -> List[float]:
        return [s.value for s in self.samples if s.value is not None]

    @property
    def failures(self) -> List[Sample]:
        return [s for s in self.samples if s.error is not None]

    def timing_report(self, frequency_hz: float, overrun_tolerance_ratio: float = 0.5) -> dict:
        """
        Schedule adherence is computed over ALL attempted samples; successful
        measurements are counted separately. A failed sample still happened
        on (or off) schedule, and excluding it would flatter the achieved rate.
        """
        slot = 1.0 / frequency_hz
        attempted = self.samples
        lateness_ms = [s.start_lateness_seconds * 1000 for s in attempted]
        durations_ms = [s.duration_seconds * 1000 for s in attempted]
        overruns = sum(
            1 for s in attempted
            if s.start_lateness_seconds > slot * overrun_tolerance_ratio
        )
        report = {
            "scheduled_samples": len(attempted),
            "successful_samples": len(attempted) - len(self.failures),
            "failed_samples": len(self.failures),
            "slot_seconds": slot,
            "max_start_lateness_ms": round(max(lateness_ms), 3) if lateness_ms else None,
            "mean_start_lateness_ms": round(sum(lateness_ms) / len(lateness_ms), 3) if lateness_ms else None,
            "max_measurement_duration_ms": round(max(durations_ms), 3) if durations_ms else None,
            "overruns": overruns,
            "attempted_mean_interval_seconds": None,
            "attempted_achieved_frequency_hz": None,
            "attempted_interval_jitter_seconds": None,
        }
        if len(attempted) >= 2:
            intervals = [
                attempted[i + 1].actual_at_offset - attempted[i].actual_at_offset
                for i in range(len(attempted) - 1)
            ]
            mean_interval = sum(intervals) / len(intervals)
            variance = (
                sum((x - mean_interval) ** 2 for x in intervals) / (len(intervals) - 1)
                if len(intervals) > 1 else 0.0
            )
            report["attempted_mean_interval_seconds"] = mean_interval
            report["attempted_achieved_frequency_hz"] = (
                1.0 / mean_interval if mean_interval else None
            )
            report["attempted_interval_jitter_seconds"] = variance ** 0.5
        return report


def run_sampling(
    config: SamplingConfig,
    measure: Callable[[], float],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SamplingResult:
    """
    Take config.measurements_count samples at config.sampling_frequency_hz.

    A measurement that overruns its slot (e.g. while retrying) does not shift
    later targets: each sample is still due at its absolute offset. Overruns
    are reported, not hidden. One failed measurement does not fail the run:
    the sample is recorded with its error and the schedule continues.
    """
    result = SamplingResult()
    start = clock()
    slot = 1.0 / config.sampling_frequency_hz
    for index in range(config.measurements_count):
        target = start + index * slot
        delay = target - clock()
        if delay > 0:
            sleep(delay)
        actual = clock()
        try:
            t0 = clock()
            value = measure()
            duration = clock() - t0
            result.samples.append(
                Sample(index, index * slot, actual - start, duration, value)
            )
        except Exception as exc:  # recorded, not raised: see module docstring
            duration = clock() - actual
            result.samples.append(
                Sample(index, index * slot, actual - start, duration, None, str(exc))
            )
    return result
