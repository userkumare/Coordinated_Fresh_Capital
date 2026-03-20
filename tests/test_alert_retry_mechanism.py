"""Tests for the alert retry mechanism."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.retry import (
    AlertRetryPolicy,
    AlertRetryStatus,
    execute_alert_delivery_with_retry,
    read_alert_retry_log,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig, send_alert_notifications


class AlertRetryMechanismTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_alert_record(self) -> AlertRecord:
        return AlertRecord(
            alert_id="ethereum:0xtoken:FRESH_ACCUMULATION:2026-03-20T11:55:00+00:00",
            token="0xtoken",
            chain="ethereum",
            alert_type=AlertType.FRESH_ACCUMULATION,
            severity=Severity.HIGH,
            score=100.0,
            window_start=self.now - timedelta(minutes=30),
            window_end=self.now - timedelta(minutes=5),
            dedup_key="ethereum:0xtoken:FRESH_ACCUMULATION",
            payload_json={"triggered_rules": ["rule_a", "rule_b"]},
            created_at=self.now,
            updated_at=self.now,
        )

    def test_successful_alert_delivery_after_retries(self) -> None:
        alert_record = self.make_alert_record()
        call_count = {"count": 0}

        def fake_sender(record: AlertRecord) -> None:
            self.assertEqual(record, alert_record)
            call_count["count"] += 1
            if call_count["count"] < 3:
                raise RuntimeError("temporary failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "retry_attempts.jsonl"
            result = execute_alert_delivery_with_retry(
                (alert_record,),
                AlertRetryPolicy(max_attempts=3, retry_delay_seconds=300.0),
                fake_sender,
                log_path=log_path,
                started_at=self.now,
            )
            logged_entries = read_alert_retry_log(log_path)

        self.assertTrue(result[0].is_delivered)
        self.assertEqual(result[0].final_status, AlertRetryStatus.SENT)
        self.assertEqual(call_count["count"], 3)
        self.assertEqual(
            [attempt.status for attempt in result[0].attempts],
            [
                AlertRetryStatus.RETRYING,
                AlertRetryStatus.RETRYING,
                AlertRetryStatus.SENT,
            ],
        )
        self.assertEqual(len(logged_entries), 3)
        self.assertEqual(logged_entries[-1].status, AlertRetryStatus.SENT)

    def test_failed_alert_delivery_after_maximum_retries(self) -> None:
        alert_record = self.make_alert_record()
        call_count = {"count": 0}

        def fake_sender(record: AlertRecord) -> None:
            self.assertEqual(record, alert_record)
            call_count["count"] += 1
            raise RuntimeError("delivery failed")

        result = execute_alert_delivery_with_retry(
            (alert_record,),
            AlertRetryPolicy(max_attempts=2, retry_delay_seconds=60.0),
            fake_sender,
            started_at=self.now,
        )

        self.assertFalse(result[0].is_delivered)
        self.assertEqual(result[0].final_status, AlertRetryStatus.FAILED)
        self.assertEqual(call_count["count"], 2)
        self.assertEqual(
            [attempt.status for attempt in result[0].attempts],
            [
                AlertRetryStatus.RETRYING,
                AlertRetryStatus.FAILED,
            ],
        )
        self.assertIsNotNone(result[0].error_message)

    def test_retry_attempt_logging_and_status_changes(self) -> None:
        alert_record = self.make_alert_record()
        failures = {"count": 0}

        def fake_sender(_: AlertRecord) -> None:
            failures["count"] += 1
            if failures["count"] < 2:
                raise RuntimeError("retry me")

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "retry_attempts.jsonl"
            result = execute_alert_delivery_with_retry(
                [alert_record],
                AlertRetryPolicy(max_attempts=3, retry_delay_seconds=120.0),
                fake_sender,
                log_path=log_path,
                started_at=self.now,
            )
            raw_lines = log_path.read_text(encoding="utf-8").splitlines()
            logged_entries = read_alert_retry_log(log_path)

        self.assertTrue(result[0].is_delivered)
        self.assertEqual(len(raw_lines), 2)
        raw_first = json.loads(raw_lines[0])
        raw_second = json.loads(raw_lines[1])
        self.assertEqual(raw_first["status"], "retrying")
        self.assertEqual(raw_second["status"], "sent")
        self.assertEqual(raw_first["scheduled_for"], self.now.isoformat())
        self.assertEqual(
            raw_second["scheduled_for"],
            (self.now + timedelta(seconds=120)).isoformat(),
        )
        self.assertEqual([entry.status for entry in logged_entries], [AlertRetryStatus.RETRYING, AlertRetryStatus.SENT])

    def test_webhook_integration_uses_retry_mechanism(self) -> None:
        alert_record = self.make_alert_record()
        call_count = {"count": 0}

        def fake_send_single_alert_notification(record: AlertRecord, config: AlertNotificationConfig) -> None:
            self.assertEqual(record, alert_record)
            self.assertEqual(config.max_attempts, 3)
            call_count["count"] += 1
            if call_count["count"] < 3:
                raise RuntimeError("try again")

        with patch(
            "fresh_capital.notifications.webhook.send_single_alert_notification",
            side_effect=fake_send_single_alert_notification,
        ):
            results = send_alert_notifications(
                (alert_record,),
                AlertNotificationConfig(
                    webhook_url="http://example.invalid/webhook",
                    max_attempts=3,
                    retry_delay_seconds=300.0,
                    timeout_seconds=1.0,
                ),
            )

        self.assertTrue(results[0].is_delivered)
        self.assertEqual(call_count["count"], 3)
        self.assertEqual(results[0].final_status, AlertRetryStatus.SENT)


if __name__ == "__main__":
    unittest.main()
