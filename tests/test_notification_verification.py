"""Tests for final notification status verification and reporting."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.persistence import NotificationStatus, queue_notification_alert, read_notification_attempts, read_notification_states
from fresh_capital.notifications.verification import (
    check_alert_notification_status,
    verify_alert_notification_processing,
    write_alert_notification_verification_report,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


class AlertNotificationVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_alert_record(self, suffix: str) -> AlertRecord:
        return AlertRecord(
            alert_id=f"ethereum:0x{suffix}:FRESH_ACCUMULATION:2026-03-20T11:55:00+00:00",
            token=f"0x{suffix}",
            chain="ethereum",
            alert_type=AlertType.FRESH_ACCUMULATION,
            severity=Severity.HIGH,
            score=100.0,
            window_start=self.now - timedelta(minutes=30),
            window_end=self.now - timedelta(minutes=5),
            dedup_key=f"ethereum:0x{suffix}:FRESH_ACCUMULATION",
            payload_json={"triggered_rules": ["rule_a"], "suffix": suffix},
            created_at=self.now,
            updated_at=self.now,
        )

    def test_verification_retries_until_successful_processing(self) -> None:
        alert_record = self.make_alert_record("success")
        attempts = {"count": 0}

        def sender(_: AlertRecord, __: AlertNotificationConfig) -> None:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            queue_notification_alert(alert_record, db_path, max_attempts=3, retry_delay_seconds=60.0, queued_at=self.now)
            report = verify_alert_notification_processing(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                started_at=self.now,
            )
            states = read_notification_states(db_path)
            attempt_rows = read_notification_attempts(db_path)

        self.assertTrue(report.all_processed)
        self.assertEqual(report.status_check.pending_count, 0)
        self.assertEqual(report.status_check.sent_count, 1)
        self.assertEqual(report.status_check.failed_count, 0)
        self.assertEqual(report.retry_rounds, 3)
        self.assertEqual(attempts["count"], 3)
        self.assertEqual(states[0].status, NotificationStatus.SENT)
        self.assertEqual(states[0].attempt_count, 3)
        self.assertEqual([row.status.value for row in attempt_rows], ["retrying", "retrying", "sent"])

    def test_verification_handles_undelivered_alerts_as_failed(self) -> None:
        alert_record = self.make_alert_record("failure")

        def sender(_: AlertRecord, __: AlertNotificationConfig) -> None:
            raise RuntimeError("permanent failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            queue_notification_alert(alert_record, db_path, max_attempts=2, retry_delay_seconds=60.0, queued_at=self.now)
            report = verify_alert_notification_processing(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                started_at=self.now,
            )
            states = read_notification_states(db_path)
            attempt_rows = read_notification_attempts(db_path)

        self.assertTrue(report.all_processed)
        self.assertEqual(report.status_check.pending_count, 0)
        self.assertEqual(report.status_check.failed_count, 1)
        self.assertEqual(report.status_check.sent_count, 0)
        self.assertEqual(report.retry_rounds, 2)
        self.assertEqual(states[0].status, NotificationStatus.FAILED)
        self.assertEqual(states[0].attempt_count, 2)
        self.assertEqual([row.status.value for row in attempt_rows], ["retrying", "failed"])

    def test_status_check_interface_and_final_report_generation(self) -> None:
        alert_record = self.make_alert_record("report")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            report_path = Path(temp_dir) / "verification_report.json"
            queue_notification_alert(alert_record, db_path, max_attempts=1, retry_delay_seconds=60.0, queued_at=self.now)

            initial_check = check_alert_notification_status(db_path, checked_at=self.now)
            report = verify_alert_notification_processing(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _record, _config: None,
                started_at=self.now,
                report_path=report_path,
            )
            saved_report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertFalse(initial_check.all_processed)
        self.assertEqual(initial_check.pending_count, 1)
        self.assertTrue(report.all_processed)
        self.assertEqual(report.status_check.sent_count, 1)
        self.assertEqual(report.status_check.pending_count, 0)
        self.assertEqual(saved_report["all_processed"], True)
        self.assertEqual(saved_report["status_check"]["sent_count"], 1)
        self.assertEqual(saved_report["status_check"]["pending_count"], 0)


if __name__ == "__main__":
    unittest.main()
