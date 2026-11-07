"""
End-to-end example: run the framework over every configured ammeter,
archive the results, compare them, and produce plots.

Prerequisite: the emulators must be running:
    python main.py --serve
Then, in another terminal (from the project root):
    python examples/run_tests.py
"""
import argparse
import os
import sys

# Fix #8: put the project root on the import path and run from it (config paths are relative).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START_CWD = os.getcwd()
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import yaml

from src.testing.sampler import ConfigError
from src.testing.test_framework import AmmeterTestFramework
from src.testing import visualization


def fmt(value, spec: str, none: str = "n/a") -> str:
    """Format a number, or `none` when it is undefined (e.g. stdev with 1 sample)."""
    return format(value, spec) if value is not None else none


def main():
    parser = argparse.ArgumentParser(description="Run the ammeter test cycle.")
    parser.add_argument("--config", default="config/config.yaml",
                        help="config file (relative paths: from the project root)")
    args = parser.parse_args()
    # a --config path is taken from where the command was typed, else the project root
    config_path = os.path.join(START_CWD, args.config)
    if not os.path.exists(config_path):
        config_path = args.config
    config_path = os.path.abspath(config_path)
    if config_path.startswith(ROOT + os.sep):
        config_path = os.path.relpath(config_path, ROOT)
    try:
        framework = AmmeterTestFramework(config_path)
    except (ConfigError, OSError, yaml.YAMLError) as exc:
        print(f"Configuration error ({config_path}): {exc}", file=sys.stderr)
        sys.exit(1)

    run_ids = []
    series = {}
    for ammeter_type in framework.ammeter_types():
        print(f"\n=== Testing {ammeter_type} ===")
        report = framework.run_test(ammeter_type)
        t = report["timing"]
        if report["status"] == "failed":
            print(
                f"FAILED: all {t['scheduled_samples']} samples failed "
                f"(archived as run {report['run_id']}). "
                f"First error: {report['sample_errors'][0]}"
            )
            continue
        run_ids.append(report["run_id"])
        series[ammeter_type] = report["values"]
        s = report["statistics"]
        print(
            f"samples={s['count']} failed={report['failed_samples']} "
            f"mean={s['mean']:.4f}A median={s['median']:.4f}A "
            f"stdev={fmt(s['stdev'], '.4f', 'n/a (n<2)')} "
            f"min={s['min']:.4f} max={s['max']:.4f}"
        )
        print(
            f"attempted mean interval={fmt(t['attempted_mean_interval_seconds'], '.6f', 'n/a')}s "
            f"(achieved {fmt(t['attempted_achieved_frequency_hz'], '.4f', 'n/a')} Hz), "
            f"max start lateness={t['max_start_lateness_ms']} ms, "
            f"overruns={t['overruns']}"
        )
        acc = report.get("accuracy_assessment")
        if acc and acc.get("status") == "descriptive_comparison":
            print(
                f"documented-model comparison (descriptive): empirical mean "
                f"{acc['empirical_mean']}A vs theoretical "
                f"{acc['theoretical_expected_mean']}A "
                f"({acc['deviation_pct']}% deviation, n={acc['sample_count']})"
            )
        elif acc:
            print(f"accuracy assessment: {acc['status']} ({acc['reason']})")

    if not run_ids:
        print("\nNo successful runs - nothing to compare.")
        return

    print("\n=== Comparison across ammeters ===")
    for row in framework.compare_ammeters(run_ids):
        print(
            f"{row['ammeter_type']:>9}: mean={row['mean']:.4f}A "
            f"median={row['median']:.4f}A stdev={fmt(row['stdev'], '.4f')}"
        )
    print(
        "\nNote: ranges differ by orders of magnitude by design (each device "
        "simulates a different physical setup). See the accuracy_assessment "
        "limitation in each run's report - no device-accuracy ranking is made."
    )

    vis = (framework.config.get("analysis") or {}).get("visualization") or {}
    if vis.get("enabled") and "comparison" in (vis.get("plot_types") or []):
        path = visualization.plot_comparison(series, framework.plots_dir)
        print(f"\ncomparison plot saved to {path}")


if __name__ == "__main__":
    main()
