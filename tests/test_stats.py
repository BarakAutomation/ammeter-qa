"""Statistics over known inputs."""
import unittest

from src.testing.stats import compute_statistics


class TestStatistics(unittest.TestCase):
    def test_known_values(self):
        s = compute_statistics([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(s["count"], 4)
        self.assertAlmostEqual(s["mean"], 2.5)
        self.assertAlmostEqual(s["median"], 2.5)
        self.assertAlmostEqual(s["stdev"], 1.2909944, places=6)
        self.assertEqual(s["min"], 1.0)
        self.assertEqual(s["max"], 4.0)


if __name__ == "__main__":
    unittest.main()
