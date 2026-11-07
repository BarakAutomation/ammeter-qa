"""
Result management: every run is archived as one JSON file with a unique ID
and full metadata, and past runs can be listed, loaded and compared.

Plain JSON on disk (human-readable, diff-able, no database dependency).
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


class ResultsStore:
    def __init__(self, results_dir: str = "results/runs"):
        self.results_dir = results_dir
        os.makedirs(self.results_dir, exist_ok=True)

    def save_run(self, ammeter_type: str, config_snapshot: dict,
                 started_at: datetime, ended_at: datetime, report: dict) -> str:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        record = {
            "run_id": run_id,
            "ammeter_type": ammeter_type,
            "started_at_utc": started_at.isoformat(),
            "ended_at_utc": ended_at.isoformat(),
            "config_snapshot": config_snapshot,
            "report": report,
        }
        path = os.path.join(self.results_dir, f"{run_id}_{ammeter_type}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        return run_id

    def list_runs(self) -> List[dict]:
        runs = []
        for name in sorted(os.listdir(self.results_dir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(self.results_dir, name), encoding="utf-8") as f:
                record = json.load(f)
            runs.append({
                "run_id": record["run_id"],
                "ammeter_type": record["ammeter_type"],
                "started_at_utc": record["started_at_utc"],
                "status": record["report"].get("status", "ok"),
            })
        return runs

    def load_run(self, run_id: str) -> Optional[dict]:
        for name in os.listdir(self.results_dir):
            if not (name.startswith(run_id + "_") and name.endswith(".json")):
                continue
            with open(os.path.join(self.results_dir, name), encoding="utf-8") as f:
                record = json.load(f)
            # The filename alone is ambiguous: the timestamp half of an id is also
            # a filename prefix. The id stored in the record is the source of truth.
            if record.get("run_id") == run_id:
                return record
        return None

    def compare_runs(self, run_ids: List[str]) -> List[dict]:
        """Side-by-side statistics for the given runs (in the given order)."""
        comparison = []
        for run_id in run_ids:
            record = self.load_run(run_id)
            if record is None:
                raise KeyError(f"unknown run id: {run_id}")
            stats = record["report"].get("statistics") or {}  # None for a failed run
            comparison.append({
                "run_id": run_id,
                "ammeter_type": record["ammeter_type"],
                "status": record["report"].get("status", "ok"),
                **{k: stats.get(k) for k in ("count", "mean", "median", "stdev", "min", "max")},
            })
        return comparison
