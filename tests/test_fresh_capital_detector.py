"""Tests for deterministic fresh capital detection decisions."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.builders.cohort import CohortBuildParticipant, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.detectors.fresh_capital import detect_fresh_capital_flow
from fresh_capital.domain.enums import ServiceType, Severity, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.extractors.token_features import (
    TokenFeatureExtractionResult,
    TokenFeatureMetrics,
    extract_token_detection_features,
)


class FreshCapitalDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_participant(
        self,
        *,
        suffix: str,
        amount_usd: float,
        funded_at: datetime | None = None,
        service_type: ServiceType = ServiceType.NONE,
    ) -> CohortBuildParticipant:
        address = AddressRecord(
            address=f"0xaddr{suffix}",
            chain="ethereum",
            first_seen_at=self.now - timedelta(days=7),
            last_seen_at=self.now,
            address_age_days=7,
            previous_tx_count=5,
            distinct_tokens_before_window=3,
            service_type=service_type,
            labels=("normalized",),
        )
        funding_event = FundingEvent(
            event_id=f"fund-{suffix}",
            address=address.address,
            chain="ethereum",
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

    def make_snapshot(
        self,
        *,
        liquidity_usd: float = 150000.0,
        market_cap_usd: float | None = 1000000.0,
    ) -> TokenMarketSnapshot:
        return TokenMarketSnapshot(
            snapshot_id="snap-1",
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            captured_at=self.now,
            price_usd=1.0,
            liquidity_usd=liquidity_usd,
            volume_24h_usd=400000.0,
            holders_count=4200,
            market_cap_usd=market_cap_usd,
        )

    def build_feature_result(
        self,
        participants: tuple[CohortBuildParticipant, ...],
        *,
        liquidity_usd: float = 150000.0,
        market_cap_usd: float | None = 1000000.0,
    ):
        cohort_result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)
        assert cohort_result.cohort is not None
        return extract_token_detection_features(
            cohort_result.cohort,
            self.make_snapshot(liquidity_usd=liquidity_usd, market_cap_usd=market_cap_usd),
        )

    def make_feature_result(
        self,
        *,
        fresh_participant_count: int,
        total_fresh_capital_usd: float,
        top_participant_share: float | None,
        liquidity_relative_funding_ratio: float | None,
        market_cap_relative_funding_ratio: float | None = None,
        cohort_timing_span_minutes: float | None = 30.0,
        unavailable_fields: tuple[str, ...] = (),
    ) -> TokenFeatureExtractionResult:
        average_capital = total_fresh_capital_usd / fresh_participant_count if fresh_participant_count else 0.0
        return TokenFeatureExtractionResult(
            metrics=TokenFeatureMetrics(
                fresh_participant_count=fresh_participant_count,
                total_fresh_capital_usd=total_fresh_capital_usd,
                average_capital_per_fresh_participant_usd=average_capital,
                top_participant_share=top_participant_share,
                top_2_participant_concentration_ratio=None,
                cohort_timing_span_minutes=cohort_timing_span_minutes,
                cohort_age_to_snapshot_minutes=5.0,
                market_cap_relative_funding_ratio=market_cap_relative_funding_ratio,
                liquidity_relative_funding_ratio=liquidity_relative_funding_ratio,
            ),
            unavailable_fields=unavailable_fields,
        )

    def test_positive_detection_path(self) -> None:
        feature_result = self.build_feature_result(
            (
                self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
                self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
                self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
            )
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertTrue(result.is_detected)
        self.assertEqual(result.reject_reasons, ())
        self.assertEqual(
            result.triggered_rules,
            (
                "valid_cohort_present",
                "minimum_participant_count_passed",
                "minimum_aggregate_fresh_capital_passed",
                "concentration_guardrail_passed",
                "liquidity_relative_funding_ratio_passed",
                "cohort_timing_span_passed",
            ),
        )
        self.assertEqual(result.severity, Severity.HIGH)

    def test_rejection_due_to_insufficient_funding(self) -> None:
        feature_result = self.make_feature_result(
            fresh_participant_count=3,
            total_fresh_capital_usd=24000.0,
            top_participant_share=0.375,
            liquidity_relative_funding_ratio=0.20,
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertFalse(result.is_detected)
        self.assertEqual(result.reject_reasons, ("insufficient_aggregate_fresh_capital",))
        self.assertEqual(result.severity, Severity.LOW)

    def test_rejection_due_to_insufficient_cohort_strength(self) -> None:
        feature_result = self.make_feature_result(
            fresh_participant_count=2,
            total_fresh_capital_usd=25000.0,
            top_participant_share=0.52,
            liquidity_relative_funding_ratio=25000.0 / 150000.0,
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertFalse(result.is_detected)
        self.assertEqual(result.reject_reasons, ("insufficient_fresh_participant_count",))

    def test_rejection_due_to_excessive_concentration(self) -> None:
        feature_result = self.build_feature_result(
            (
                self.make_participant(suffix="1", amount_usd=20000.0),
                self.make_participant(suffix="2", amount_usd=3000.0),
                self.make_participant(suffix="3", amount_usd=2000.0),
            )
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertFalse(result.is_detected)
        self.assertEqual(result.reject_reasons, ("excessive_top_participant_concentration",))

    def test_optional_market_and_liquidity_unavailable_are_explicit(self) -> None:
        feature_result = self.build_feature_result(
            (
                self.make_participant(suffix="1", amount_usd=10000.0),
                self.make_participant(suffix="2", amount_usd=8000.0),
                self.make_participant(suffix="3", amount_usd=7000.0),
            ),
            liquidity_usd=0.0,
            market_cap_usd=None,
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertTrue(result.is_detected)
        self.assertEqual(
            result.unavailable_metrics,
            (
                "liquidity_relative_funding_ratio",
                "market_cap_relative_funding_ratio",
            ),
        )
        self.assertEqual(
            result.skipped_rules,
            (
                "liquidity_relative_funding_ratio_unavailable",
                "market_cap_relative_funding_ratio_unavailable_or_unsupported",
            ),
        )

    def test_reject_reason_ordering_is_deterministic(self) -> None:
        feature_result = self.make_feature_result(
            fresh_participant_count=2,
            total_fresh_capital_usd=18000.0,
            top_participant_share=0.66,
            liquidity_relative_funding_ratio=18000.0 / 300000.0,
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertEqual(
            result.reject_reasons,
            (
                "insufficient_fresh_participant_count",
                "insufficient_aggregate_fresh_capital",
                "insufficient_liquidity_relative_funding_ratio",
            ),
        )

    def test_threshold_edge_equality_behavior(self) -> None:
        feature_result = self.build_feature_result(
            (
                self.make_participant(suffix="1", amount_usd=10000.0),
                self.make_participant(suffix="2", amount_usd=7500.0),
                self.make_participant(suffix="3", amount_usd=7500.0),
            ),
            liquidity_usd=150000.0,
        )

        result = detect_fresh_capital_flow(feature_result)

        self.assertTrue(result.is_detected)
        self.assertEqual(result.metrics.total_fresh_capital_usd, 25000.0)
        self.assertAlmostEqual(
            result.metrics.liquidity_relative_funding_ratio or 0.0,
            result.metrics.min_required_liquidity_relative_funding_ratio,
        )

    def test_invalid_input_handling(self) -> None:
        with self.assertRaises(TypeError):
            detect_fresh_capital_flow(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
