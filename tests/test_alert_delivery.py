"""Tests for deterministic local alert delivery."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.alerts.builder import build_fresh_capital_alert
from fresh_capital.alerts.delivery import deliver_logged_alerts, read_delivered_alerts
from fresh_capital.alerts.handler import AlertStatus, handle_alert_build_result, read_alert_log
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


class AlertDeliveryTests(unittest.TestCase):
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

    def test_successful_alert_delivery(self) -> None:
        build_result = self.build_positive_alert_result()

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "alerts.jsonl"
            db_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            handle_alert_build_result(build_result, log_path)
            results = deliver_logged_alerts(log_path, db_path, status_log_path)
            delivered_rows = read_delivered_alerts(db_path)
            status_entries = read_alert_log(status_log_path)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].is_delivered)
        self.assertEqual(results[0].status, AlertStatus.DELIVERED)
        self.assertEqual(len(delivered_rows), 1)
        self.assertEqual(delivered_rows[0]["status"], "delivered")
        self.assertEqual(status_entries[0].status, AlertStatus.DELIVERED)

    def test_unsuccessful_delivery_mock_failure(self) -> None:
        build_result = self.build_positive_alert_result()
        assert build_result.alert_record is not None

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "alerts.jsonl"
            db_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            handle_alert_build_result(build_result, log_path)
            results = deliver_logged_alerts(
                log_path,
                db_path,
                status_log_path,
                fail_alert_ids=(build_result.alert_record.alert_id,),
            )
            delivered_rows = read_delivered_alerts(db_path)
            status_entries = read_alert_log(status_log_path)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_delivered)
        self.assertEqual(results[0].reject_reasons, ("mock_delivery_failed",))
        self.assertEqual(delivered_rows, ())
        self.assertEqual(status_entries[0].status, AlertStatus.FAILED)

    def test_correct_database_insertion_behavior(self) -> None:
        build_result = self.build_positive_alert_result()

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "alerts.jsonl"
            db_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            handle_alert_build_result(build_result, log_path)
            deliver_logged_alerts(log_path, db_path, status_log_path)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT alert_id, alert_type, status FROM delivered_alerts ORDER BY rowid"
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "FRESH_ACCUMULATION")
        self.assertEqual(rows[0][2], "delivered")

    def test_alert_status_updates_from_created_to_delivered(self) -> None:
        build_result = self.build_positive_alert_result()

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "alerts.jsonl"
            db_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            handle_alert_build_result(build_result, log_path)
            created_entries = read_alert_log(log_path)
            deliver_logged_alerts(log_path, db_path, status_log_path)
            status_entries = read_alert_log(status_log_path)

        self.assertEqual(created_entries[0].status, AlertStatus.CREATED)
        self.assertEqual(status_entries[0].status, AlertStatus.DELIVERED)

    def test_invalid_input_handling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "alerts.jsonl"
            db_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            with self.assertRaises(TypeError):
                deliver_logged_alerts(123, db_path, status_log_path)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                deliver_logged_alerts(log_path, 123, status_log_path)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                read_delivered_alerts(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
