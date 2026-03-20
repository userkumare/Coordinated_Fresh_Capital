"""Tests for MVP threshold configuration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.config.thresholds import MVP_THRESHOLDS


class ConfigTests(unittest.TestCase):
    def test_thresholds_import_cleanly(self) -> None:
        self.assertEqual(MVP_THRESHOLDS.fresh_address.max_age_days, 30)
        self.assertEqual(MVP_THRESHOLDS.cohort.min_size, 3)
        self.assertEqual(MVP_THRESHOLDS.accumulation.score_threshold, 70.0)
        self.assertEqual(MVP_THRESHOLDS.distribution.score_threshold, 65.0)
        self.assertEqual(MVP_THRESHOLDS.short_watch.min_dist_score, 75.0)


if __name__ == "__main__":
    unittest.main()
