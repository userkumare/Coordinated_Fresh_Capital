"""Tests for alert prioritization and priority-aware processing order."""

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
    dispatch_due_notifications,
    queue_notification_alert,
    read_notification_states,
    update_notification_priority,
)
from fresh_capital.notifications.prioritization import (
    AlertPriority,
    AlertPriorityEvent,
    classify_alert_priority,
    read_alert_priority_log,
)
from fresh_capital.notifications.scheduling import (
    process_due_alert_schedules,
    schedule_alert_notification,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


class AlertPrioritizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_alert_record(self, suffix: str, alert_type: AlertType, severity: Severity) -> AlertRecord:
        return AlertRecord(
            alert_id=f"ethereum:0x{suffix}:{alert_type.value}:2026-03-20T11:55:00+00:00",
            token=f"0x{suffix}",
            chain="ethereum",
            alert_type=alert_type,
            severity=severity,
            score=100.0,
            window_start=self.now - timedelta(minutes=30),
            window_end=self.now - timedelta(minutes=5),
            dedup_key=f"ethereum:0x{suffix}:{alert_type.value}",
            payload_json={"triggered_rules": ["rule_a"], "suffix": suffix},
            created_at=self.now,
            updated_at=self.now,
        )

    def test_classifies_priority_and_reprioritizes_alerts(self) -> None:
        low_record = self.make_alert_record("low", AlertType.FRESH_ACCUMULATION, Severity.LOW)
        high_record = self.make_alert_record("high", AlertType.SHORT_WATCH, Severity.HIGH)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            log_path = Path(temp_dir) / "priority.jsonl"
            queue_notification_alert(low_record, db_path, queued_at=self.now, priority_log_path=log_path)
            queue_notification_alert(high_record, db_path, queued_at=self.now + timedelta(minutes=1), priority_log_path=log_path)
            updated_state = update_notification_priority(
                low_record.alert_id,
                db_path,
                priority=AlertPriority.HIGH,
                priority_reason="manual_override",
                changed_at=self.now + timedelta(minutes=2),
                priority_log_path=log_path,
            )
            states = read_notification_states(db_path)
            log_entries = read_alert_priority_log(log_path)

        self.assertEqual(classify_alert_priority(low_record), AlertPriority.LOW)
        self.assertEqual(classify_alert_priority(high_record), AlertPriority.HIGH)
        self.assertEqual(updated_state.priority, AlertPriority.HIGH)
        self.assertEqual(next(state.priority for state in states if state.alert_id == low_record.alert_id), AlertPriority.HIGH)
        self.assertEqual(next(state.priority for state in states if state.alert_id == high_record.alert_id), AlertPriority.HIGH)
        self.assertEqual([entry.event for entry in log_entries], [
            AlertPriorityEvent.CLASSIFIED,
            AlertPriorityEvent.CLASSIFIED,
            AlertPriorityEvent.CHANGED,
        ])
        self.assertEqual(log_entries[-1].previous_priority, AlertPriority.LOW)

    def test_high_priority_alerts_are_processed_before_low_priority_retry_targets(self) -> None:
        low_record = self.make_alert_record("retry-low", AlertType.FRESH_ACCUMULATION, Severity.LOW)
        high_record = self.make_alert_record("retry-high", AlertType.SHORT_WATCH, Severity.HIGH)
        processed_order: list[str] = []

        def sender(alert_record: AlertRecord, _config: AlertNotificationConfig) -> None:
            processed_order.append(alert_record.alert_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "notifications.sqlite"
            log_path = Path(temp_dir) / "priority.jsonl"
            queue_notification_alert(low_record, db_path, queued_at=self.now, priority_log_path=log_path)
            queue_notification_alert(high_record, db_path, queued_at=self.now, priority_log_path=log_path)
            dispatch_due_notifications(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now,
                priority_log_path=log_path,
            )
            log_entries = read_alert_priority_log(log_path)

        self.assertEqual(processed_order, [high_record.alert_id, low_record.alert_id])
        processed_entries = [entry for entry in log_entries if entry.event == AlertPriorityEvent.PROCESSED]
        self.assertEqual([entry.alert_id for entry in processed_entries], [high_record.alert_id, low_record.alert_id])
        self.assertEqual([entry.processing_order for entry in processed_entries], [1, 2])

    def test_priority_order_is_respected_in_scheduling_processing(self) -> None:
        low_record = self.make_alert_record("sched-low", AlertType.FRESH_ACCUMULATION, Severity.LOW)
        high_record = self.make_alert_record("sched-high", AlertType.SHORT_WATCH, Severity.HIGH)
        processed_order: list[str] = []

        def sender(alert_record: AlertRecord, _config: AlertNotificationConfig) -> None:
            processed_order.append(alert_record.alert_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "scheduling.sqlite"
            log_path = Path(temp_dir) / "priority.jsonl"
            schedule_alert_notification(
                low_record,
                db_path,
                scheduled_for=self.now,
                created_at=self.now,
                priority_log_path=log_path,
            )
            schedule_alert_notification(
                high_record,
                db_path,
                scheduled_for=self.now,
                created_at=self.now,
                priority_log_path=log_path,
            )
            process_due_alert_schedules(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender,
                as_of=self.now,
                priority_log_path=log_path,
            )
            log_entries = read_alert_priority_log(log_path)

        self.assertEqual(processed_order, [high_record.alert_id, low_record.alert_id])
        processed_entries = [entry for entry in log_entries if entry.event == AlertPriorityEvent.PROCESSED]
        self.assertEqual([entry.alert_id for entry in processed_entries], [high_record.alert_id, low_record.alert_id])
        self.assertTrue(all(entry.processing_order == 1 for entry in processed_entries))


if __name__ == "__main__":
    unittest.main()
