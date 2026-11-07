"""
The unified testing framework required by the exercise.

One entry point - AmmeterTestFramework.run_test(ammeter_type) - works with
every ammeter type through the same flow: load config -> build a defensive
client -> sample on a precise schedule -> analyse -> archive -> (optionally)
visualise. Everything is driven by config/config.yaml.

run_test ALWAYS returns a report dict with a "status": "ok" (at least one
successful measurement) or "failed" (every sample failed). Both are archived
with their errors, timing, raw samples and the resolved configuration, so a
failed run is traceable too. A bad CONFIG is different: it raises ConfigError
before anything runs.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List

from src.client.ammeter_client import AmmeterClient, ClientConfig
from src.testing import stats
from src.testing.accuracy import assess_conformance
from src.testing.results_store import ResultsStore
from src.testing.sampler import ConfigError, SamplingConfig, run_sampling
from src.utils.config import load_config
from src.utils.logger import TestLogger


def _section(config: dict, *path) -> dict:
    """config[path[0]][path[1]]... as a dict; a missing/empty section is {}."""
    node = config
    for key in path:
        node = (node or {}).get(key) if isinstance(node, dict) else None
    if node is None:
        return {}
    if not isinstance(node, dict):
        raise ConfigError(f"config: '{'.'.join(path)}' must be a mapping")
    return node


class AmmeterTestFramework:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config = load_config(config_path)
        if not isinstance(self.config, dict):
            raise ConfigError(f"config: {config_path} is empty or not a mapping")
        self._validate_config()
        rm = _section(self.config, "result_management")
        self.store = ResultsStore(rm.get("results_dir", "results/runs"))
        self.plots_dir = rm.get("plots_dir", "results/plots")
        self.logs_dir = rm.get("logs_dir", "results/logs")

    def _validate_config(self):
        """Check the config at the boundary, so errors are ConfigErrors, not KeyErrors."""
        ammeters = _section(self.config, "ammeters")
        if not ammeters:
            raise ConfigError("config: no ammeters section configured")
        for name, entry in ammeters.items():
            if not isinstance(entry, dict) or "port" not in entry or "command" not in entry:
                raise ConfigError(f"config: ammeter '{name}' needs port and command")
            port = entry["port"]
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ConfigError(f"config: ammeter '{name}' port must be 1-65535, got {port!r}")
            if not isinstance(entry["command"], str) or not entry["command"]:
                raise ConfigError(f"config: ammeter '{name}' command must be a non-empty string")
        if not _section(self.config, "testing", "sampling"):
            raise ConfigError("config: testing.sampling is missing")
        # Fail now (not mid-run) on a bad sampling or client section.
        self._sampling_config()
        self._client_config()

    def ammeter_types(self) -> List[str]:
        return list(self.config["ammeters"].keys())

    def _client_config(self) -> ClientConfig:
        # Only keys that are present are passed on, so ClientConfig's defaults
        # apply to missing keys while an explicit null is rejected there.
        client_cfg = _section(self.config, "testing", "client")
        known = ("connect_timeout_seconds", "read_timeout_seconds", "retries",
                 "retry_backoff_seconds")
        kwargs = {k: client_cfg[k] for k in known if k in client_cfg}
        return ClientConfig(
            error_simulation=_section(self.config, "testing", "error_simulation"),
            **kwargs,
        )

    def _build_client(self, ammeter_type: str) -> AmmeterClient:
        entry = self.config["ammeters"][ammeter_type]
        return AmmeterClient(
            name=ammeter_type,
            port=entry["port"],
            command=entry["command"],
            config=self._client_config(),
        )

    def _sampling_config(self) -> SamplingConfig:
        s = _section(self.config, "testing", "sampling")
        timing = _section(self.config, "testing", "timing")
        return SamplingConfig(
            measurements_count=s.get("measurements_count"),
            total_duration_seconds=s.get("total_duration_seconds"),
            sampling_frequency_hz=s.get("sampling_frequency_hz"),
            overrun_tolerance_ratio=timing.get("overrun_tolerance_ratio", 0.5),
        ).resolve()

    def run_test(self, ammeter_type: str) -> Dict:
        if ammeter_type not in self.config["ammeters"]:
            raise KeyError(
                f"unknown ammeter type '{ammeter_type}'. "
                f"configured: {self.ammeter_types()}"
            )
        logger = TestLogger(f"run_{ammeter_type}", self.logs_dir)
        sampling = self._sampling_config()
        client = self._build_client(ammeter_type)

        logger.info(
            f"starting run: {sampling.measurements_count} samples at "
            f"{sampling.sampling_frequency_hz} Hz from {ammeter_type} "
            f"(port {client.port})"
        )
        started_at = datetime.now(timezone.utc)
        sampling_result = run_sampling(sampling, client.measure_once)
        ended_at = datetime.now(timezone.utc)

        values = sampling_result.values
        failures = sampling_result.failures
        report = {
            "status": "ok" if values else "failed",
            "statistics": stats.compute_statistics(values) if values else None,
            "timing": sampling_result.timing_report(
                sampling.sampling_frequency_hz,
                sampling.overrun_tolerance_ratio,
            ),
            "failed_samples": len(failures),
            "sample_errors": [s.error for s in failures],
            "values": values,
            # Raw per-sample record: schedule, actual start, duration, value, error.
            "samples": [
                {
                    "index": s.index,
                    "scheduled_at_offset": s.scheduled_at_offset,
                    "actual_at_offset": s.actual_at_offset,
                    "duration_seconds": s.duration_seconds,
                    "value": s.value,
                    "error": s.error,
                }
                for s in sampling_result.samples
            ],
        }
        if not values:
            logger.error(
                f"all {len(failures)} measurements failed for {ammeter_type}: "
                f"{failures[0].error}"
            )
        elif _section(self.config, "analysis", "accuracy_assessment").get("enabled"):
            report["accuracy_assessment"] = assess_conformance(
                ammeter_type, report["statistics"]
            )

        # The RESOLVED configuration this run actually used (not the raw YAML).
        client_cfg = asdict(client.config)
        run_id = self.store.save_run(
            ammeter_type,
            config_snapshot={
                "config_file": self.config_path,
                "sampling": {
                    "measurements_count": sampling.measurements_count,
                    "total_duration_seconds": sampling.total_duration_seconds,
                    "sampling_frequency_hz": sampling.sampling_frequency_hz,
                },
                "timing": {"overrun_tolerance_ratio": sampling.overrun_tolerance_ratio},
                "client": client_cfg,
                "ammeter": self.config["ammeters"][ammeter_type],
            },
            started_at=started_at,
            ended_at=ended_at,
            report=report,
        )
        report["run_id"] = run_id
        if values:
            logger.info(
                f"run {run_id} archived: mean={report['statistics']['mean']:.4f}A, "
                f"failures={report['failed_samples']}"
            )
        else:
            logger.info(f"run {run_id} archived with status=failed")

        vis = _section(self.config, "analysis").get("visualization") or {}
        if values and vis.get("enabled") and "time_series" in (vis.get("plot_types") or []):
            from src.testing import visualization
            path = visualization.plot_run(
                run_id, ammeter_type, sampling_result.samples, self.plots_dir
            )
            report["plot"] = path
            logger.info(f"plot saved to {path}")

        return report

    def compare_ammeters(self, run_ids: List[str]) -> List[dict]:
        return self.store.compare_runs(run_ids)
