"""Tests for alert expiration and automatic cancellation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.expiration import (
    AlertExpirationEvent,
    cancel_expired_notifications,
    read_alert_expiration_log,
)
from fresh_capital.notifications.persistence import (
    NotificationStatus,
    dispatch_due_notifications,
    queue_notification_alert,
    read_notification_attempts,
    read_notification_states,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


class AlertExpirationTests(unittest.TestCase):
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

    def test_expired_alert_is_canceled_before_retry_and_not_retried(self) -> None:
        alert_record = self.make_alert_record("auto")
        call_count = {"count": 0}

        def sender(_: AlertRecord, __: AlertNotificationConfig) -> None:
            call_count["count"] += 1
            raise RuntimeError("temporary failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            log_path = Path(temp_dir) / "expiration.jsonl"
            queue_notification_alert(
                alert_record,
                db_path,
                max_attempts=3,
                retry_delay_seconds=60.0,
                expiration_seconds=30.0,
                queued_at=self.now,
            )
            first_results = dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now,
                expiration_log_path=log_path,
            )
            second_results = dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now + timedelta(seconds=60),
                expiration_log_path=log_path,
            )
            states = read_notification_states(db_path)
            attempts = read_notification_attempts(db_path)
            log_entries = read_alert_expiration_log(log_path)

        self.assertEqual(len(first_results), 1)
        self.assertEqual(first_results[0].status, NotificationStatus.PENDING)
        self.assertEqual(len(second_results), 0)
        self.assertEqual(call_count["count"], 1)
        self.assertEqual(states[0].status, NotificationStatus.CANCELED)
        self.assertEqual(states[0].canceled_at, self.now + timedelta(seconds=60))
        self.assertEqual(len(attempts), 1)
        self.assertEqual([attempt.status.value for attempt in attempts], ["retrying"])
        self.assertEqual([entry.event for entry in log_entries], [AlertExpirationEvent.EXPIRED, AlertExpirationEvent.CANCELED])

    def test_explicit_cancellation_logs_expiration_and_cancellation_events(self) -> None:
        alert_record = self.make_alert_record("explicit")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            log_path = Path(temp_dir) / "expiration.jsonl"
            queue_notification_alert(
                alert_record,
                db_path,
                max_attempts=3,
                retry_delay_seconds=60.0,
                expiration_seconds=30.0,
                queued_at=self.now,
            )
            results = cancel_expired_notifications(
                db_path,
                as_of=self.now + timedelta(seconds=31),
                log_path=log_path,
            )
            states = read_notification_states(db_path)
            log_entries = read_alert_expiration_log(log_path)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].was_canceled)
        self.assertEqual(results[0].status, NotificationStatus.CANCELED)
        self.assertEqual(states[0].status, NotificationStatus.CANCELED)
        self.assertEqual([entry.event for entry in log_entries], [AlertExpirationEvent.EXPIRED, AlertExpirationEvent.CANCELED])

    def test_canceled_alert_is_not_retried_after_expiration(self) -> None:
        alert_record = self.make_alert_record("blocked")
        call_count = {"count": 0}

        def sender(_: AlertRecord, __: AlertNotificationConfig) -> None:
            call_count["count"] += 1

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            queue_notification_alert(
                alert_record,
                db_path,
                max_attempts=3,
                retry_delay_seconds=60.0,
                expiration_seconds=30.0,
                queued_at=self.now,
            )
            cancel_expired_notifications(db_path, as_of=self.now + timedelta(seconds=31))
            results = dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now + timedelta(minutes=2),
            )
            states = read_notification_states(db_path)

        self.assertEqual(results, ())
        self.assertEqual(call_count["count"], 0)
        self.assertEqual(states[0].status, NotificationStatus.CANCELED)


if __name__ == "__main__":
    unittest.main()
