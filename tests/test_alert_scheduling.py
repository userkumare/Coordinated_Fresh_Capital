"""Tests for alert scheduling and rescheduling."""

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
    read_notification_attempts,
    read_notification_states,
)
from fresh_capital.notifications.scheduling import (
    AlertScheduleEvent,
    AlertScheduleStatus,
    process_due_alert_schedules,
    read_alert_schedule_log,
    read_alert_schedules,
    read_due_alert_schedules,
    schedule_alert_notification,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


class AlertSchedulingTests(unittest.TestCase):
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

    def test_schedules_and_triggers_alert_at_specified_time(self) -> None:
        alert_record = self.make_alert_record("oneoff")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "scheduling.sqlite"
            log_path = Path(temp_dir) / "schedule.jsonl"
            scheduled_for = self.now + timedelta(minutes=15)
            schedule_alert_notification(
                alert_record,
                db_path,
                scheduled_for=scheduled_for,
                created_at=self.now,
                log_path=log_path,
            )
            due_before = read_due_alert_schedules(db_path, as_of=self.now)
            trigger_results = process_due_alert_schedules(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _record, _config: None,
                as_of=scheduled_for,
                log_path=log_path,
            )
            schedules = read_alert_schedules(db_path)
            notification_states = read_notification_states(db_path)
            notification_attempts = read_notification_attempts(db_path)
            log_entries = read_alert_schedule_log(log_path)

        self.assertEqual(due_before, ())
        self.assertEqual(len(trigger_results), 1)
        self.assertEqual(trigger_results[0].status, AlertScheduleStatus.COMPLETED)
        self.assertFalse(trigger_results[0].was_rescheduled)
        self.assertEqual(schedules[0].status, AlertScheduleStatus.COMPLETED)
        self.assertEqual(schedules[0].trigger_count, 1)
        self.assertIsNone(schedules[0].next_run_at)
        self.assertEqual(notification_states[0].status, NotificationStatus.SENT)
        self.assertEqual(notification_attempts[0].attempt_number, 1)
        self.assertEqual([entry.event for entry in log_entries], [
            AlertScheduleEvent.SCHEDULED,
            AlertScheduleEvent.TRIGGERED,
            AlertScheduleEvent.COMPLETED,
        ])

    def test_handles_missed_interval_and_reschedules_next_run(self) -> None:
        alert_record = self.make_alert_record("interval")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "scheduling.sqlite"
            log_path = Path(temp_dir) / "schedule.jsonl"
            schedule_alert_notification(
                alert_record,
                db_path,
                scheduled_for=self.now,
                interval_seconds=3600.0,
                created_at=self.now,
                log_path=log_path,
            )
            trigger_results = process_due_alert_schedules(
                db_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _record, _config: None,
                as_of=self.now + timedelta(hours=2, minutes=15),
                log_path=log_path,
            )
            schedules = read_alert_schedules(db_path)
            log_entries = read_alert_schedule_log(log_path)

        self.assertEqual(len(trigger_results), 1)
        self.assertTrue(trigger_results[0].was_rescheduled)
        self.assertEqual(trigger_results[0].status, AlertScheduleStatus.RESCHEDULED)
        self.assertEqual(schedules[0].status, AlertScheduleStatus.RESCHEDULED)
        self.assertEqual(schedules[0].trigger_count, 1)
        self.assertEqual(schedules[0].next_run_at, self.now + timedelta(hours=3))
        self.assertEqual([entry.event for entry in log_entries], [
            AlertScheduleEvent.SCHEDULED,
            AlertScheduleEvent.TRIGGERED,
            AlertScheduleEvent.RESCHEDULED,
        ])

    def test_invalid_schedule_inputs_raise(self) -> None:
        alert_record = self.make_alert_record("invalid")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "scheduling.sqlite"

            with self.assertRaises(ValueError):
                schedule_alert_notification(alert_record, db_path, created_at=self.now)
            with self.assertRaises(ValueError):
                schedule_alert_notification(alert_record, db_path, delay_seconds=-1.0, created_at=self.now)
            with self.assertRaises(ValueError):
                schedule_alert_notification(alert_record, db_path, interval_seconds=0.0, created_at=self.now)


if __name__ == "__main__":
    unittest.main()
