"""
Bonus: visualization of measurement data (matplotlib, non-interactive).
Enabled via config (analysis.visualization.enabled); import is lazy so the
rest of the framework works even without matplotlib installed.
"""
import os
from typing import Dict, List


def plot_run(run_id: str, ammeter_type: str, samples, plots_dir: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = [s for s in samples if s.value is not None]
    os.makedirs(plots_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot([s.actual_at_offset for s in ok], [s.value for s in ok],
            marker="o", linestyle="-", label="measured current")
    values = [s.value for s in ok]
    ax.axhline(sum(values) / len(values), color="gray", linestyle="--", linewidth=1, label="mean")
    ax.set_xlabel("seconds from run start")
    ax.set_ylabel("current (A)")
    ax.set_title(f"{ammeter_type} - run {run_id}")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(plots_dir, f"{run_id}_{ammeter_type}.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_comparison(series: Dict[str, List[float]], plots_dir: str) -> str:
    if not series:
        raise ValueError("no data series to plot")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(plots_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.boxplot(list(series.values()))
    ax.set_xticklabels(list(series.keys()))
    ax.set_ylabel("current (A)")
    ax.set_title("Output distribution per ammeter (log scale: ranges differ by design)")
    ax.set_yscale("log")
    fig.tight_layout()
    path = os.path.join(plots_dir, "ammeter_comparison.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
