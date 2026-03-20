"""Tests for deterministic fresh capital alert building."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.alerts.builder import build_fresh_capital_alert
from fresh_capital.builders.cohort import CohortBuildParticipant, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.detectors.fresh_capital import detect_fresh_capital_flow
from fresh_capital.domain.enums import AlertType, ServiceType, Severity, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.extractors.token_features import (
    TokenFeatureExtractionResult,
    TokenFeatureMetrics,
    extract_token_detection_features,
)


class AlertBuilderTests(unittest.TestCase):
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

    def make_snapshot(self) -> TokenMarketSnapshot:
        return TokenMarketSnapshot(
            snapshot_id="snap-1",
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            captured_at=self.now,
            price_usd=1.0,
            liquidity_usd=150000.0,
            volume_24h_usd=400000.0,
            holders_count=4200,
            market_cap_usd=1000000.0,
        )

    def build_positive_context(self):
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )
        cohort_result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)
        assert cohort_result.cohort is not None
        feature_result = extract_token_detection_features(cohort_result.cohort, self.make_snapshot())
        decision_result = detect_fresh_capital_flow(feature_result)
        return cohort_result.cohort, feature_result, decision_result

    def test_positive_detection_builds_alert(self) -> None:
        cohort, feature_result, decision_result = self.build_positive_context()

        result = build_fresh_capital_alert(decision_result, cohort, feature_result)

        self.assertTrue(result.is_alert_built)
        self.assertEqual(result.reject_reasons, ())
        self.assertIsNotNone(result.alert_record)
        assert result.alert_record is not None
        self.assertEqual(result.alert_record.alert_type, AlertType.FRESH_ACCUMULATION)
        self.assertEqual(result.alert_record.token, "0xtoken")

    def test_negative_detection_does_not_build_alert(self) -> None:
        cohort, _, _ = self.build_positive_context()
        feature_result = TokenFeatureExtractionResult(
            metrics=TokenFeatureMetrics(
                fresh_participant_count=2,
                total_fresh_capital_usd=18000.0,
                average_capital_per_fresh_participant_usd=9000.0,
                top_participant_share=0.6,
                top_2_participant_concentration_ratio=None,
                cohort_timing_span_minutes=30.0,
                cohort_age_to_snapshot_minutes=5.0,
                market_cap_relative_funding_ratio=None,
                liquidity_relative_funding_ratio=0.12,
            ),
            unavailable_fields=(),
        )
        decision_result = detect_fresh_capital_flow(feature_result)

        result = build_fresh_capital_alert(decision_result, cohort, feature_result)

        self.assertFalse(result.is_alert_built)
        self.assertEqual(result.reject_reasons, ("detection_not_positive",))
        self.assertIsNone(result.alert_record)

    def test_severity_mapping_behavior(self) -> None:
        cohort, _, _ = self.build_positive_context()
        feature_result = TokenFeatureExtractionResult(
            metrics=TokenFeatureMetrics(
                fresh_participant_count=3,
                total_fresh_capital_usd=25000.0,
                average_capital_per_fresh_participant_usd=25000.0 / 3.0,
                top_participant_share=0.4,
                top_2_participant_concentration_ratio=None,
                cohort_timing_span_minutes=None,
                cohort_age_to_snapshot_minutes=5.0,
                market_cap_relative_funding_ratio=None,
                liquidity_relative_funding_ratio=None,
            ),
            unavailable_fields=("cohort_timing_span_minutes", "liquidity_relative_funding_ratio"),
        )
        decision_result = detect_fresh_capital_flow(feature_result)

        result = build_fresh_capital_alert(decision_result, cohort, feature_result)

        self.assertTrue(result.is_alert_built)
        assert result.alert_record is not None
        self.assertEqual(result.alert_record.severity, Severity.MEDIUM)

    def test_triggered_rules_are_preserved(self) -> None:
        cohort, feature_result, decision_result = self.build_positive_context()

        result = build_fresh_capital_alert(decision_result, cohort, feature_result)

        assert result.alert_record is not None
        self.assertEqual(result.alert_record.payload_json["triggered_rules"], list(decision_result.triggered_rules))

    def test_supporting_metrics_are_carried_into_alert(self) -> None:
        cohort, feature_result, decision_result = self.build_positive_context()

        result = build_fresh_capital_alert(decision_result, cohort, feature_result)

        assert result.alert_record is not None
        self.assertEqual(
            result.alert_record.payload_json["fresh_participant_count"],
            decision_result.metrics.fresh_participant_count,
        )
        self.assertEqual(
            result.alert_record.payload_json["total_fresh_capital_usd"],
            decision_result.metrics.total_fresh_capital_usd,
        )
        self.assertEqual(result.summary.score if result.summary is not None else None, 100.0)

    def test_deterministic_reject_reason_ordering(self) -> None:
        cohort, feature_result, _ = self.build_positive_context()
        mismatched_feature_result = TokenFeatureExtractionResult(
            metrics=TokenFeatureMetrics(
                fresh_participant_count=1,
                total_fresh_capital_usd=1.0,
                average_capital_per_fresh_participant_usd=1.0,
                top_participant_share=1.0,
                top_2_participant_concentration_ratio=None,
                cohort_timing_span_minutes=30.0,
                cohort_age_to_snapshot_minutes=5.0,
                market_cap_relative_funding_ratio=None,
                liquidity_relative_funding_ratio=0.01,
            ),
            unavailable_fields=(),
        )
        decision_result = detect_fresh_capital_flow(mismatched_feature_result)

        result = build_fresh_capital_alert(decision_result, cohort, feature_result)

        self.assertEqual(
            result.reject_reasons,
            (
                "detection_not_positive",
                "feature_decision_participant_count_mismatch",
                "feature_decision_funding_mismatch",
            ),
        )

    def test_invalid_input_handling(self) -> None:
        cohort, feature_result, decision_result = self.build_positive_context()

        with self.assertRaises(TypeError):
            build_fresh_capital_alert(object(), cohort, feature_result)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            build_fresh_capital_alert(decision_result, object(), feature_result)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            build_fresh_capital_alert(decision_result, cohort, object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
