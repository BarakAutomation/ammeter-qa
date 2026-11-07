"""Archive: save, list, load and compare runs."""
import tempfile
import unittest
from datetime import datetime, timezone

from src.testing.results_store import ResultsStore


def _report(mean):
    return {"statistics": {"count": 2, "mean": mean, "median": mean,
                           "stdev": 0.1, "min": mean - 1, "max": mean + 1}}


class TestResultsStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = ResultsStore(self.dir)

    def test_save_list_load_roundtrip(self):
        run_id = self.store.save_run(
            "greenlee", {"sampling": {}},
            datetime.now(timezone.utc), datetime.now(timezone.utc), _report(0.5),
        )
        runs = self.store.list_runs()
        self.assertEqual([r["run_id"] for r in runs], [run_id])
        record = self.store.load_run(run_id)
        self.assertEqual(record["ammeter_type"], "greenlee")
        self.assertEqual(record["report"]["statistics"]["mean"], 0.5)
        self.assertIn("config_snapshot", record)

    def test_compare_runs_side_by_side(self):
        id1 = self.store.save_run("greenlee", {}, datetime.now(timezone.utc),
                                  datetime.now(timezone.utc), _report(0.5))
        id2 = self.store.save_run("entes", {}, datetime.now(timezone.utc),
                                  datetime.now(timezone.utc), _report(50.0))
        rows = self.store.compare_runs([id2, id1])
        self.assertEqual([r["ammeter_type"] for r in rows], ["entes", "greenlee"])
        self.assertEqual(rows[0]["mean"], 50.0)


if __name__ == "__main__":
    unittest.main()
