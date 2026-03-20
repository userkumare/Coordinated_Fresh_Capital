"""Tests for deterministic local alert handling and audit logging."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.alerts.builder import build_fresh_capital_alert
from fresh_capital.alerts.handler import (
    AlertStatus,
    handle_alert_build_result,
    read_alert_log,
    update_alert_status,
)
from fresh_capital.builders.cohort import CohortBuildParticipant, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.detectors.fresh_capital import detect_fresh_capital_flow
from fresh_capital.domain.enums import ServiceType, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.extractors.token_features import (
    TokenFeatureExtractionResult,
    TokenFeatureMetrics,
    extract_token_detection_features,
)


class AlertHandlerTests(unittest.TestCase):
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

    def build_positive_alert_result(self):
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )
        cohort_result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)
        assert cohort_result.cohort is not None
        feature_result = extract_token_detection_features(cohort_result.cohort, self.make_snapshot())
        decision_result = detect_fresh_capital_flow(feature_result)
        return build_fresh_capital_alert(decision_result, cohort_result.cohort, feature_result)

    def build_negative_alert_result(self):
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )
        cohort_result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)
        assert cohort_result.cohort is not None
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
        return build_fresh_capital_alert(decision_result, cohort_result.cohort, feature_result)

    def test_positive_alert_storage(self) -> None:
        build_result = self.build_positive_alert_result()

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "alerts.jsonl"
            result = handle_alert_build_result(build_result, storage_path)
            entries = read_alert_log(storage_path)

        self.assertTrue(result.is_stored)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, AlertStatus.CREATED)
        self.assertEqual(entries[0].triggered_rules, tuple(build_result.alert_record.payload_json["triggered_rules"]))  # type: ignore[union-attr]

    def test_alert_creation_and_status_change(self) -> None:
        build_result = self.build_positive_alert_result()
        assert build_result.alert_record is not None

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "alerts.jsonl"
            created = handle_alert_build_result(build_result, storage_path)
            processed = update_alert_status(
                build_result.alert_record,
                AlertStatus.PROCESSED,
                storage_path,
                logged_at=build_result.alert_record.updated_at + timedelta(minutes=1),
            )
            entries = read_alert_log(storage_path)

        self.assertTrue(created.is_stored)
        self.assertTrue(processed.is_stored)
        self.assertEqual([entry.status for entry in entries], [AlertStatus.CREATED, AlertStatus.PROCESSED])

    def test_rejection_of_invalid_alerts(self) -> None:
        build_result = self.build_negative_alert_result()

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "alerts.jsonl"
            result = handle_alert_build_result(build_result, storage_path)
            entries = read_alert_log(storage_path)

        self.assertTrue(result.is_stored)
        self.assertEqual(entries[0].status, AlertStatus.REJECTED)
        self.assertEqual(entries[0].reject_reasons, ("detection_not_positive",))

    def test_structured_logging_behavior(self) -> None:
        build_result = self.build_positive_alert_result()

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "alerts.jsonl"
            handle_alert_build_result(build_result, storage_path)
            raw_lines = storage_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(raw_lines), 1)
        self.assertIn("\"status\": \"created\"", raw_lines[0])
        self.assertIn("\"triggered_rules\"", raw_lines[0])
        self.assertIn("\"severity\": \"high\"", raw_lines[0])

    def test_invalid_input_handling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "alerts.jsonl"
            with self.assertRaises(TypeError):
                handle_alert_build_result(object(), storage_path)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                read_alert_log(123)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                update_alert_status(object(), AlertStatus.PROCESSED, storage_path)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
