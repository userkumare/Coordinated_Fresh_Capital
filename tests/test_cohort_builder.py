"""Tests for deterministic fresh cohort construction."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.builders.cohort import CohortBuildParticipant, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.domain.enums import ServiceType, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent


class CohortBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_participant(
        self,
        *,
        suffix: str,
        amount_usd: float,
        address_age_days: int = 7,
        previous_tx_count: int = 5,
        distinct_tokens_before_window: int = 3,
        service_type: ServiceType = ServiceType.NONE,
        chain: str = "ethereum",
        funded_at: datetime | None = None,
    ) -> CohortBuildParticipant:
        address = AddressRecord(
            address=f"0xaddr{suffix}",
            chain=chain,
            first_seen_at=self.now - timedelta(days=max(address_age_days, 1)),
            last_seen_at=self.now,
            address_age_days=address_age_days,
            previous_tx_count=previous_tx_count,
            distinct_tokens_before_window=distinct_tokens_before_window,
            service_type=service_type,
            labels=("normalized",),
        )
        funding_event = FundingEvent(
            event_id=f"fund-{suffix}",
            address=address.address,
            chain=chain,
            funded_at=funded_at or (self.now - timedelta(minutes=int(suffix) * 10)),
            source_address=f"0xfunder{suffix}",
            source_type=SourceType.EXCHANGE,
            asset_symbol="USDC",
            amount=amount_usd,
            amount_usd=amount_usd,
            tx_hash=f"0xtx{suffix}",
        )
        return CohortBuildParticipant(
            address=address,
            fresh_classification=classify_fresh_address(address),
            funding_event=funding_event,
        )

    def test_valid_cohort_creation(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0),
            self.make_participant(suffix="2", amount_usd=8000.0),
            self.make_participant(suffix="3", amount_usd=7000.0),
        )

        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)

        self.assertTrue(result.is_valid_cohort)
        self.assertEqual(result.reject_reasons, ())
        self.assertEqual(result.metrics.unique_fresh_participant_count, 3)
        self.assertEqual(result.metrics.total_fresh_capital_usd, 25000.0)
        self.assertIsNotNone(result.cohort)
        assert result.cohort is not None
        self.assertEqual(result.cohort.member_count, 3)
        self.assertEqual(result.cohort.fresh_ratio, 1.0)

    def test_rejects_insufficient_member_count(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=15000.0),
            self.make_participant(suffix="2", amount_usd=12000.0),
        )

        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)

        self.assertFalse(result.is_valid_cohort)
        self.assertEqual(result.reject_reasons, ("insufficient_fresh_participant_count",))
        self.assertIsNone(result.cohort)

    def test_rejects_insufficient_aggregate_capital(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=5000.0),
            self.make_participant(suffix="2", amount_usd=5000.0),
            self.make_participant(suffix="3", amount_usd=5000.0),
        )

        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)

        self.assertFalse(result.is_valid_cohort)
        self.assertEqual(result.reject_reasons, ("insufficient_aggregate_capital",))
        self.assertIsNone(result.cohort)

    def test_filters_mixed_valid_and_invalid_participants(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0),
            self.make_participant(suffix="2", amount_usd=8000.0),
            self.make_participant(suffix="3", amount_usd=7000.0),
            self.make_participant(
                suffix="4",
                amount_usd=50000.0,
                service_type=ServiceType.EXCHANGE,
            ),
        )

        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)

        self.assertTrue(result.is_valid_cohort)
        self.assertEqual(result.metrics.unique_fresh_participant_count, 3)
        self.assertEqual(result.metrics.total_fresh_capital_usd, 25000.0)
        assert result.cohort is not None
        self.assertEqual(tuple(member.address for member in result.cohort.members), ("0xaddr1", "0xaddr2", "0xaddr3"))

    def test_reject_reason_ordering_is_deterministic(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=5000.0),
            self.make_participant(suffix="2", amount_usd=5000.0),
        )

        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)

        self.assertEqual(
            result.reject_reasons,
            ("insufficient_fresh_participant_count", "insufficient_aggregate_capital"),
        )

    def test_threshold_edge_equality_is_valid(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=9000.0),
            self.make_participant(suffix="2", amount_usd=8000.0),
            self.make_participant(suffix="3", amount_usd=8000.0),
        )

        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)

        self.assertTrue(result.is_valid_cohort)
        self.assertEqual(result.metrics.unique_fresh_participant_count, 3)
        self.assertEqual(result.metrics.total_fresh_capital_usd, 25000.0)

    def test_invalid_input_type_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            build_fresh_cohort("ethereum", "0xtoken", "ABC", [object()])  # type: ignore[list-item]

    def test_chain_mismatch_is_rejected(self) -> None:
        participant = self.make_participant(suffix="1", amount_usd=10000.0, chain="base")

        with self.assertRaises(ValueError):
            build_fresh_cohort("ethereum", "0xtoken", "ABC", [participant])


if __name__ == "__main__":
    unittest.main()
