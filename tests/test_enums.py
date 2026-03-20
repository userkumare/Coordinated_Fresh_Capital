"""Tests for enum definitions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity, SourceType, TokenLifecycleState, TradeSide
from fresh_capital.domain.validation import ensure_enum_member


class EnumTests(unittest.TestCase):
    def test_enum_values_are_stable(self) -> None:
        self.assertEqual(AlertType.FRESH_ACCUMULATION.value, "FRESH_ACCUMULATION")
        self.assertEqual(TokenLifecycleState.DISTRIBUTION_STARTED.value, "distribution_started")
        self.assertEqual(TradeSide.BUY.value, "buy")
        self.assertEqual(Severity.HIGH.value, "high")
        self.assertEqual(SourceType.EXCHANGE.value, "exchange")

    def test_enum_validator_accepts_string_values(self) -> None:
        state = ensure_enum_member("state", "short_watch", TokenLifecycleState)
        self.assertEqual(state, TokenLifecycleState.SHORT_WATCH)


if __name__ == "__main__":
    unittest.main()
