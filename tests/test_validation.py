"""Tests for shared validation helpers and validation failures."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import TokenLifecycleState
from fresh_capital.domain.models import Cohort
from fresh_capital.domain.validation import (
    ensure_enum_member,
    ensure_non_negative_number,
    ensure_percentage,
    ensure_timestamp_order,
)


class ValidationTests(unittest.TestCase):
    def test_non_negative_validator_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            ensure_non_negative_number("funding_usd", -1.0)

    def test_percentage_validator_accepts_zero_to_one(self) -> None:
        self.assertEqual(ensure_percentage("fresh_ratio", 0.5), 0.5)

    def test_percentage_validator_rejects_values_above_one(self) -> None:
        with self.assertRaises(ValueError):
            ensure_percentage("fresh_ratio", 1.2)

    def test_timestamp_order_validator_rejects_reversed_order(self) -> None:
        earlier = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        later = datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            ensure_timestamp_order("window_start", earlier, "window_end", later)

    def test_enum_validator_rejects_invalid_value(self) -> None:
        with self.assertRaises(ValueError):
            ensure_enum_member("state", "bad_state", TokenLifecycleState)

    def test_model_validation_rejects_empty_cohort(self) -> None:
        now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            Cohort(
                cohort_id="cohort-1",
                chain="ethereum",
                token_address="0xtoken",
                token_symbol="ABC",
                window_start=now,
                window_end=now,
                fresh_ratio=0.5,
                funding_window_min=180,
                buy_window_min=240,
                members=(),
            )


if __name__ == "__main__":
    unittest.main()
