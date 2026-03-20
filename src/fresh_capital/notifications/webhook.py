"""Deterministic webhook-based alert notification delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.retry import (
    AlertRetryAttempt as AlertNotificationAttempt,
    AlertRetryPolicy,
    AlertRetryResult as AlertNotificationResult,
    AlertRetryStatus as AlertNotificationStatus,
    execute_alert_delivery_with_retry,
    read_alert_retry_log as read_notification_attempt_log,
)


@dataclass(frozen=True, slots=True)
class AlertNotificationConfig:
    webhook_url: str
    max_attempts: int = 3
    retry_delay_seconds: float = 300.0
    timeout_seconds: float = 5.0
    log_path: str | Path | None = None


def send_alert_notifications(
    alert_records: tuple[AlertRecord, ...] | list[AlertRecord],
    config: AlertNotificationConfig,
) -> tuple[AlertNotificationResult, ...]:
    """Send alert records to a webhook endpoint with deterministic retries."""
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")
    if not isinstance(config.webhook_url, str) or not config.webhook_url:
        raise ValueError("webhook_url must be a non-empty string")
    if config.max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if config.retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must be non-negative")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    return execute_alert_delivery_with_retry(
        alert_records,
        AlertRetryPolicy(
            max_attempts=config.max_attempts,
            retry_delay_seconds=config.retry_delay_seconds,
        ),
        lambda alert_record: send_single_alert_notification(alert_record, config),
        log_path=config.log_path,
    )


def send_single_alert_notification(
    alert_record: AlertRecord,
    config: AlertNotificationConfig,
) -> None:
    """Send a single alert payload to the configured webhook endpoint."""
    if not isinstance(alert_record, AlertRecord):
        raise TypeError("alert_record must be an AlertRecord")
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")

    payload = {
        "alert_id": alert_record.alert_id,
        "alert_type": alert_record.alert_type.value,
        "chain": alert_record.chain,
        "dedup_key": alert_record.dedup_key,
        "payload_json": dict(alert_record.payload_json),
        "score": alert_record.score,
        "severity": alert_record.severity.value,
        "status": "sent",
        "token": alert_record.token,
        "window_end": alert_record.window_end.isoformat(),
        "window_start": alert_record.window_start.isoformat(),
    }
    request = Request(
        config.webhook_url,
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=config.timeout_seconds) as response:
        if getattr(response, "status", 200) >= 400:
            raise RuntimeError(f"webhook returned HTTP {response.status}")


__all__ = [
    "AlertNotificationAttempt",
    "AlertNotificationConfig",
    "AlertNotificationResult",
    "AlertNotificationStatus",
    "read_notification_attempt_log",
    "send_alert_notifications",
    "send_single_alert_notification",
]
