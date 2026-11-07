"""Sampling schedule and failure recording, with a fake clock so the tests are fast and deterministic."""
import unittest

from src.testing.sampler import SamplingConfig, run_sampling


class FakeClock:
    def __init__(self):
        self.t = 0.0
    def monotonic(self):
        return self.t
    def sleep(self, seconds):
        self.t += seconds


class TestSamplerFakeClock(unittest.TestCase):
    def test_schedule_offsets_and_first_sample_immediate(self):
        clock = FakeClock()
        cfg = SamplingConfig(4, 2, 2).resolve()  # 4 samples at 2Hz
        result = run_sampling(cfg, lambda: 1.0, clock.monotonic, clock.sleep)
        offsets = [s.scheduled_at_offset for s in result.samples]
        self.assertEqual(offsets, [0.0, 0.5, 1.0, 1.5])  # last at (n-1)/f
        self.assertEqual([s.value for s in result.samples], [1.0] * 4)
        for s in result.samples:
            self.assertAlmostEqual(s.start_lateness_seconds, 0.0)

    def test_failures_are_recorded_and_run_continues(self):
        clock = FakeClock()
        def measure():
            if measure.calls == 2:
                measure.calls += 1
                raise RuntimeError("device exploded")
            measure.calls += 1
            return 1.0
        measure.calls = 0
        cfg = SamplingConfig(3, 1.5, 2).resolve()
        result = run_sampling(cfg, measure, clock.monotonic, clock.sleep)
        self.assertEqual(len(result.samples), 3)
        self.assertEqual(len(result.failures), 1)
        self.assertIn("device exploded", result.failures[0].error)
        self.assertEqual(result.values, [1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
