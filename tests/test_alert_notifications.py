"""Tests for live webhook alert notifications."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.alerts.builder import build_fresh_capital_alert
from fresh_capital.builders.cohort import CohortBuildParticipant, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.detectors.fresh_capital import detect_fresh_capital_flow
from fresh_capital.domain.enums import ServiceType, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.notifications.webhook import (
    AlertNotificationConfig,
    AlertNotificationStatus,
    read_notification_attempt_log,
    send_alert_notifications,
)
from fresh_capital.extractors.token_features import extract_token_detection_features


class _WebhookState:
    request_count = 0
    failures_before_success = 0
    payloads: list[dict[str, object]] = []


class _WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        _WebhookState.request_count += 1
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        _WebhookState.payloads.append(json.loads(raw_body.decode("utf-8")))
        if _WebhookState.request_count <= _WebhookState.failures_before_success:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"fail")
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class NotificationHTTPServer(HTTPServer):
    request_count: int
    failures_before_success: int


class AlertNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        _WebhookState.request_count = 0
        _WebhookState.failures_before_success = 0
        _WebhookState.payloads = []

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

    def build_alert_record(self):
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )
        cohort_result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)
        assert cohort_result.cohort is not None
        feature_result = extract_token_detection_features(
            cohort_result.cohort,
            TokenMarketSnapshot(
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
            ),
        )
        decision_result = detect_fresh_capital_flow(feature_result)
        build_result = build_fresh_capital_alert(decision_result, cohort_result.cohort, feature_result)
        assert build_result.alert_record is not None
        return build_result.alert_record

    def _run_server(self, failures_before_success: int) -> tuple[NotificationHTTPServer, threading.Thread, str]:
        _WebhookState.failures_before_success = failures_before_success
        server = NotificationHTTPServer(("127.0.0.1", 0), _WebhookHandler)
        server.request_count = 0
        server.failures_before_success = failures_before_success
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_address[1]}/notify"

    def test_successful_alert_delivery(self) -> None:
        alert_record = self.build_alert_record()
        server, thread, webhook_url = self._run_server(failures_before_success=0)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                log_path = Path(temp_dir) / "notification_attempts.jsonl"
                results = send_alert_notifications(
                    (alert_record,),
                    AlertNotificationConfig(
                        webhook_url=webhook_url,
                        max_attempts=3,
                        timeout_seconds=2.0,
                        log_path=log_path,
                    ),
                )
                log_entries = read_notification_attempt_log(log_path)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertTrue(results[0].is_delivered)
        self.assertEqual(results[0].final_status, AlertNotificationStatus.SENT)
        self.assertEqual(_WebhookState.request_count, 1)
        self.assertEqual(_WebhookState.payloads[0]["alert_id"], alert_record.alert_id)
        self.assertEqual(_WebhookState.payloads[0]["alert_type"], alert_record.alert_type.value)
        self.assertEqual(len(log_entries), 1)
        self.assertEqual(log_entries[0].status, AlertNotificationStatus.SENT)
        self.assertEqual(len(results[0].attempts), 1)
        self.assertEqual(results[0].attempts[0].status, AlertNotificationStatus.SENT)

    def test_failed_delivery_with_retry_mechanism(self) -> None:
        alert_record = self.build_alert_record()
        server, thread, webhook_url = self._run_server(failures_before_success=2)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                log_path = Path(temp_dir) / "notification_attempts.jsonl"
                results = send_alert_notifications(
                    (alert_record,),
                    AlertNotificationConfig(
                        webhook_url=webhook_url,
                        max_attempts=3,
                        timeout_seconds=2.0,
                        log_path=log_path,
                    ),
                )
                log_lines = log_path.read_text(encoding="utf-8").splitlines()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertTrue(results[0].is_delivered)
        self.assertEqual(results[0].final_status, AlertNotificationStatus.SENT)
        self.assertEqual(_WebhookState.request_count, 3)
        self.assertEqual([attempt.status for attempt in results[0].attempts], [
            AlertNotificationStatus.RETRYING,
            AlertNotificationStatus.RETRYING,
            AlertNotificationStatus.SENT,
        ])
        self.assertEqual(len(log_lines), 3)
        self.assertIn('"status": "retrying"', log_lines[0])
        self.assertIn('"status": "sent"', log_lines[-1])

    def test_failed_delivery_logs_status_and_errors(self) -> None:
        alert_record = self.build_alert_record()
        server, thread, webhook_url = self._run_server(failures_before_success=99)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                log_path = Path(temp_dir) / "notification_attempts.jsonl"
                results = send_alert_notifications(
                    (alert_record,),
                    AlertNotificationConfig(
                        webhook_url=webhook_url,
                        max_attempts=2,
                        timeout_seconds=2.0,
                        log_path=log_path,
                    ),
                )
                log_lines = log_path.read_text(encoding="utf-8").splitlines()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertFalse(results[0].is_delivered)
        self.assertEqual(results[0].final_status, AlertNotificationStatus.FAILED)
        self.assertEqual(len(results[0].attempts), 2)
        self.assertEqual(results[0].attempts[-1].status, AlertNotificationStatus.FAILED)
        self.assertIsNotNone(results[0].error_message)
        self.assertEqual(len(log_lines), 2)
        self.assertIn('"status": "failed"', log_lines[-1])

    def test_invalid_input_handling(self) -> None:
        with self.assertRaises(TypeError):
            send_alert_notifications([object()], AlertNotificationConfig(webhook_url="http://example.com"))  # type: ignore[list-item]
        with self.assertRaises(TypeError):
            send_alert_notifications((self.build_alert_record(),), object())  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            send_alert_notifications((self.build_alert_record(),), AlertNotificationConfig(webhook_url=""))


if __name__ == "__main__":
    unittest.main()
