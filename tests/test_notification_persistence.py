"""Tests for SQLite notification persistence and resend behavior."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.persistence import (
    NotificationStatus,
    dispatch_due_notifications,
    queue_notification_alert,
    read_due_notification_states,
    read_notification_attempts,
    read_notification_states,
    resend_undelivered_notifications,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


class NotificationPersistenceTests(unittest.TestCase):
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

    def test_persistence_of_alert_statuses_pending_sent_failed(self) -> None:
        pending_record = self.make_alert_record("pending")
        sent_record = self.make_alert_record("sent")
        failed_record = self.make_alert_record("failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            pending_db = Path(temp_dir) / "pending.sqlite"
            queue_notification_alert(pending_record, pending_db, max_attempts=3, retry_delay_seconds=60.0, queued_at=self.now)
            dispatch_due_notifications(
                pending_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _, __: (_ for _ in ()).throw(RuntimeError("still pending")),
                as_of=self.now,
            )
            pending_state = read_notification_states(pending_db)[0]
            pending_attempts = read_notification_attempts(pending_db)

            sent_db = Path(temp_dir) / "sent.sqlite"
            queue_notification_alert(sent_record, sent_db, max_attempts=3, retry_delay_seconds=60.0, queued_at=self.now)
            dispatch_due_notifications(
                sent_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _, __: None,
                as_of=self.now,
            )
            sent_state = read_notification_states(sent_db)[0]
            sent_attempts = read_notification_attempts(sent_db)

            failed_db = Path(temp_dir) / "failed.sqlite"
            queue_notification_alert(failed_record, failed_db, max_attempts=2, retry_delay_seconds=60.0, queued_at=self.now)
            dispatch_due_notifications(
                failed_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _, __: (_ for _ in ()).throw(RuntimeError("always failing")),
                as_of=self.now,
            )
            dispatch_due_notifications(
                failed_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _, __: (_ for _ in ()).throw(RuntimeError("always failing")),
                as_of=self.now + timedelta(seconds=60),
            )
            failed_state = read_notification_states(failed_db)[0]
            failed_attempts = read_notification_attempts(failed_db)

        self.assertEqual(pending_state.status, NotificationStatus.PENDING)
        self.assertEqual(pending_state.attempt_count, 1)
        self.assertEqual([attempt.status.value for attempt in pending_attempts], ["retrying"])
        self.assertEqual(sent_state.status, NotificationStatus.SENT)
        self.assertEqual(sent_state.attempt_count, 1)
        self.assertEqual([attempt.status.value for attempt in sent_attempts], ["sent"])
        self.assertEqual(failed_state.status, NotificationStatus.FAILED)
        self.assertEqual(failed_state.attempt_count, 2)
        self.assertEqual([attempt.status.value for attempt in failed_attempts], ["retrying", "failed"])

    def test_resending_undelivered_alerts_after_set_period(self) -> None:
        alert_record = self.make_alert_record("retry")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            queue_notification_alert(alert_record, db_path, max_attempts=3, retry_delay_seconds=60.0, queued_at=self.now)

            attempts = {"count": 0}

            def sender(_: AlertRecord, __: AlertNotificationConfig) -> None:
                attempts["count"] += 1
                if attempts["count"] < 2:
                    raise RuntimeError("temporary failure")

            first_results = dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now,
            )
            not_due_states = read_due_notification_states(db_path, as_of=self.now + timedelta(seconds=30))
            second_results = resend_undelivered_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now + timedelta(seconds=60),
            )
            states = read_notification_states(db_path)
            attempts_log = read_notification_attempts(db_path)

        self.assertFalse(first_results[0].is_delivered)
        self.assertEqual(first_results[0].status, NotificationStatus.PENDING)
        self.assertEqual(not_due_states, ())
        self.assertTrue(second_results[0].is_delivered)
        self.assertEqual(states[0].status, NotificationStatus.SENT)
        self.assertEqual(states[0].attempt_count, 2)
        self.assertEqual(len(attempts_log), 2)

    def test_correct_logging_of_delivery_attempts_and_statuses(self) -> None:
        alert_record = self.make_alert_record("log")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            queue_notification_alert(alert_record, db_path, max_attempts=2, retry_delay_seconds=30.0, queued_at=self.now)

            def sender(_: AlertRecord, __: AlertNotificationConfig) -> None:
                raise RuntimeError("no delivery")

            dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now,
            )
            dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now + timedelta(seconds=30),
            )
            attempts_log = read_notification_attempts(db_path)
            states = read_notification_states(db_path)

        self.assertEqual([attempt.status.value for attempt in attempts_log], ["retrying", "failed"])
        self.assertEqual([attempt.attempt_number for attempt in attempts_log], [1, 2])
        self.assertEqual(states[0].status, NotificationStatus.FAILED)
        self.assertEqual(states[0].attempt_count, 2)


if __name__ == "__main__":
    unittest.main()
