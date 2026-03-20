"""Tests for the deterministic fresh address classifier."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.domain.enums import ServiceType
from fresh_capital.domain.models import AddressRecord


class FreshAddressClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_address(
        self,
        *,
        address_age_days: int = 7,
        previous_tx_count: int = 5,
        distinct_tokens_before_window: int = 3,
        service_type: ServiceType = ServiceType.NONE,
    ) -> AddressRecord:
        return AddressRecord(
            address="0xabc",
            chain="ethereum",
            first_seen_at=self.now - timedelta(days=max(address_age_days, 1)),
            last_seen_at=self.now,
            address_age_days=address_age_days,
            previous_tx_count=previous_tx_count,
            distinct_tokens_before_window=distinct_tokens_before_window,
            service_type=service_type,
            labels=("normalized",),
        )

    def test_positive_fresh_case(self) -> None:
        result = classify_fresh_address(self.make_address())

        self.assertTrue(result.is_fresh)
        self.assertEqual(result.reject_reasons, ())
        self.assertEqual(result.metrics.address_age_days, 7)
        self.assertEqual(result.metrics.previous_tx_count, 5)
        self.assertEqual(result.metrics.distinct_tokens_before_window, 3)
        self.assertEqual(result.metrics.service_type, ServiceType.NONE)

    def test_rejects_age_above_threshold(self) -> None:
        result = classify_fresh_address(self.make_address(address_age_days=31))

        self.assertFalse(result.is_fresh)
        self.assertEqual(result.reject_reasons, ("address_age_days_exceeds_max",))

    def test_rejects_previous_tx_count_above_threshold(self) -> None:
        result = classify_fresh_address(self.make_address(previous_tx_count=21))

        self.assertFalse(result.is_fresh)
        self.assertEqual(result.reject_reasons, ("previous_tx_count_exceeds_max",))

    def test_rejects_distinct_tokens_above_threshold(self) -> None:
        result = classify_fresh_address(self.make_address(distinct_tokens_before_window=11))

        self.assertFalse(result.is_fresh)
        self.assertEqual(result.reject_reasons, ("distinct_tokens_before_window_exceeds_max",))

    def test_rejects_blocked_service_type(self) -> None:
        result = classify_fresh_address(self.make_address(service_type=ServiceType.EXCHANGE))

        self.assertFalse(result.is_fresh)
        self.assertEqual(result.reject_reasons, ("service_type_blocked",))

    def test_returns_multiple_rejection_reasons(self) -> None:
        result = classify_fresh_address(
            self.make_address(
                address_age_days=45,
                previous_tx_count=50,
                distinct_tokens_before_window=25,
                service_type=ServiceType.ROUTER,
            )
        )

        self.assertFalse(result.is_fresh)
        self.assertEqual(
            result.reject_reasons,
            (
                "address_age_days_exceeds_max",
                "previous_tx_count_exceeds_max",
                "distinct_tokens_before_window_exceeds_max",
                "service_type_blocked",
            ),
        )

    def test_threshold_equality_cases_pass(self) -> None:
        result = classify_fresh_address(
            self.make_address(
                address_age_days=30,
                previous_tx_count=20,
                distinct_tokens_before_window=10,
            )
        )

        self.assertTrue(result.is_fresh)
        self.assertEqual(result.reject_reasons, ())

    def test_classifier_rejects_invalid_input_type(self) -> None:
        with self.assertRaises(TypeError):
            classify_fresh_address(object())  # type: ignore[arg-type]

    def test_address_model_rejects_invalid_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            self.make_address(address_age_days=-1)


if __name__ == "__main__":
    unittest.main()
