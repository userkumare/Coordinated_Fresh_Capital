"""Tests for the notification operations CLI."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.ops import (
    build_notification_ops_report,
    list_notification_ops_entries,
    main,
    write_notification_ops_report,
)
from fresh_capital.notifications.persistence import (
    NotificationStatus,
    dispatch_due_notifications,
    queue_notification_alert,
    read_notification_states,
)
from fresh_capital.notifications.scheduling import (
    AlertScheduleStatus,
    schedule_alert_notification,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


class NotificationOpsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_alert_record(self, suffix: str, alert_type: AlertType = AlertType.FRESH_ACCUMULATION) -> AlertRecord:
        return AlertRecord(
            alert_id=f"ethereum:0x{suffix}:{alert_type.value}:2026-03-20T11:55:00+00:00",
            token=f"0x{suffix}",
            chain="ethereum",
            alert_type=alert_type,
            severity=Severity.HIGH,
            score=100.0,
            window_start=self.now - timedelta(minutes=30),
            window_end=self.now - timedelta(minutes=5),
            dedup_key=f"ethereum:0x{suffix}:{alert_type.value}",
            payload_json={"triggered_rules": ["rule_a"], "suffix": suffix},
            created_at=self.now,
            updated_at=self.now,
        )

    def test_summary_data_generation_counts_current_state(self) -> None:
        pending_record = self.make_alert_record("pending")
        scheduled_record = self.make_alert_record("scheduled", alert_type=AlertType.ACCUMULATION_CONFIRMED)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite"
            queue_notification_alert(pending_record, db_path, queued_at=self.now)
            schedule_alert_notification(
                scheduled_record,
                db_path,
                scheduled_for=self.now + timedelta(minutes=30),
                created_at=self.now,
            )

            report = build_notification_ops_report(db_path, as_of=self.now)

        self.assertEqual(report.notification_summary.total_alerts, 1)
        self.assertEqual(report.notification_summary.pending_count, 1)
        self.assertEqual(report.notification_summary.due_count, 1)
        self.assertEqual(report.schedule_summary.total_alerts, 1)
        self.assertEqual(report.schedule_summary.scheduled_count, 1)
        self.assertEqual(report.schedule_summary.due_count, 0)

    def test_listing_due_and_terminal_alerts_is_deterministic(self) -> None:
        due_record = self.make_alert_record("due")
        sent_record = self.make_alert_record("sent")
        failed_record = self.make_alert_record("failed")
        canceled_record = self.make_alert_record("canceled")
        scheduled_record = self.make_alert_record("schedule", alert_type=AlertType.ACCUMULATION_CONFIRMED)

        with tempfile.TemporaryDirectory() as temp_dir:
            due_db = Path(temp_dir) / "due.sqlite"
            queue_notification_alert(due_record, due_db, queued_at=self.now)
            due_entries = list_notification_ops_entries(
                due_db,
                collection="notifications",
                state="due",
                as_of=self.now,
            )

            sent_db = Path(temp_dir) / "sent.sqlite"
            queue_notification_alert(sent_record, sent_db, queued_at=self.now)
            dispatch_due_notifications(
                sent_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _record, _config: None,
                as_of=self.now,
            )
            sent_entries = list_notification_ops_entries(
                sent_db,
                collection="notifications",
                state="sent",
                as_of=self.now,
            )

            failed_db = Path(temp_dir) / "failed.sqlite"
            queue_notification_alert(failed_record, failed_db, max_attempts=1, queued_at=self.now)
            dispatch_due_notifications(
                failed_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _record, _config: (_ for _ in ()).throw(RuntimeError("failure")),
                as_of=self.now,
            )
            failed_entries = list_notification_ops_entries(
                failed_db,
                collection="notifications",
                state="failed",
                as_of=self.now,
            )

            canceled_db = Path(temp_dir) / "canceled.sqlite"
            queue_notification_alert(
                canceled_record,
                canceled_db,
                expiration_at=self.now - timedelta(seconds=1),
                queued_at=self.now,
            )
            dispatch_due_notifications(
                canceled_db,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=lambda _record, _config: None,
                as_of=self.now,
            )
            canceled_entries = list_notification_ops_entries(
                canceled_db,
                collection="notifications",
                state="canceled",
                as_of=self.now,
            )

            schedule_db = Path(temp_dir) / "schedule.sqlite"
            schedule_alert_notification(
                scheduled_record,
                schedule_db,
                scheduled_for=self.now + timedelta(minutes=15),
                created_at=self.now,
            )
            scheduled_entries = list_notification_ops_entries(
                schedule_db,
                collection="schedules",
                state="scheduled",
                as_of=self.now,
            )

        self.assertEqual([entry["alert_id"] for entry in due_entries], [due_record.alert_id])
        self.assertEqual([entry["status"] for entry in due_entries], [NotificationStatus.PENDING.value])
        self.assertEqual([entry["alert_id"] for entry in sent_entries], [sent_record.alert_id])
        self.assertEqual([entry["status"] for entry in sent_entries], [NotificationStatus.SENT.value])
        self.assertEqual([entry["alert_id"] for entry in failed_entries], [failed_record.alert_id])
        self.assertEqual([entry["status"] for entry in failed_entries], [NotificationStatus.FAILED.value])
        self.assertEqual([entry["alert_id"] for entry in canceled_entries], [canceled_record.alert_id])
        self.assertEqual([entry["status"] for entry in canceled_entries], [NotificationStatus.CANCELED.value])
        self.assertEqual([entry["alert_id"] for entry in scheduled_entries], [scheduled_record.alert_id])
        self.assertEqual([entry["status"] for entry in scheduled_entries], [AlertScheduleStatus.SCHEDULED.value])

    def test_cli_processes_due_alerts_through_existing_flow(self) -> None:
        scheduled_record = self.make_alert_record("process", alert_type=AlertType.ACCUMULATION_CONFIRMED)
        delivered_alert_ids: list[str] = []

        def sender(alert_record: AlertRecord, _config: AlertNotificationConfig) -> None:
            delivered_alert_ids.append(alert_record.alert_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite"
            schedule_alert_notification(
                scheduled_record,
                db_path,
                scheduled_for=self.now,
                created_at=self.now,
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "process",
                        "--db-path",
                        str(db_path),
                        "--webhook-url",
                        "http://example.invalid",
                        "--as-of",
                        self.now.isoformat(),
                    ],
                    sender=sender,
                )

            payload = json.loads(stdout.getvalue())
            schedules = read_notification_states(db_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(delivered_alert_ids, [scheduled_record.alert_id])
        self.assertEqual(payload["schedule_results"][0]["status"], AlertScheduleStatus.COMPLETED.value)
        self.assertEqual(
            payload["schedule_results"][0]["notification_results"][0]["is_delivered"],
            True,
        )
        self.assertEqual(schedules[0].status, NotificationStatus.SENT)

    def test_report_generation_writes_deterministic_json(self) -> None:
        alert_record = self.make_alert_record("report")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite"
            report_path_1 = Path(temp_dir) / "report-1.json"
            report_path_2 = Path(temp_dir) / "report-2.json"
            queue_notification_alert(alert_record, db_path, queued_at=self.now)
            report = build_notification_ops_report(db_path, as_of=self.now)
            written_1 = write_notification_ops_report(report, report_path_1)
            written_2 = write_notification_ops_report(report, report_path_2)

            payload_1 = json.loads(written_1.read_text(encoding="utf-8"))
            payload_2 = json.loads(written_2.read_text(encoding="utf-8"))

        self.assertEqual(payload_1, payload_2)
        self.assertEqual(payload_1["notification_summary"]["pending_count"], 1)
        self.assertEqual(payload_1["schedule_summary"]["total_alerts"], 0)

    def test_invalid_cli_argument_handling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite"
            with self.assertRaises(SystemExit) as exc_info:
                main(
                    [
                        "list",
                        "--db-path",
                        str(db_path),
                        "--collection",
                        "notifications",
                        "--state",
                        "scheduled",
                    ]
                )

        self.assertEqual(exc_info.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

