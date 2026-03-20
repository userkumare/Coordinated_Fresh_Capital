"""Expiration and cancellation for undelivered alerts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fresh_capital.notifications.persistence import (
    NotificationStateRecord,
    NotificationStatus,
    _upsert_state_record,
    read_notification_states,
)
from fresh_capital.domain.enums import StrEnum


class AlertExpirationEvent(StrEnum):
    EXPIRED = "expired"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class AlertExpirationLogEntry:
    alert_id: str
    event: AlertExpirationEvent
    expiration_at: datetime
    canceled_at: datetime | None
    status: NotificationStatus
    reason: str | None


@dataclass(frozen=True, slots=True)
class NotificationExpirationResult:
    alert_id: str
    status: NotificationStatus
    expiration_at: datetime
    canceled_at: datetime
    was_canceled: bool
    reason: str


def cancel_expired_notifications(
    db_path: str | Path,
    *,
    as_of: datetime | None = None,
    log_path: str | Path | None = None,
) -> tuple[NotificationExpirationResult, ...]:
    """Cancel pending notifications that have passed their expiration time."""
    now = as_of or datetime.now(timezone.utc)
    states = read_notification_states(db_path)
    results: list[NotificationExpirationResult] = []

    for state in states:
        if state.status != NotificationStatus.PENDING:
            continue
        if state.expiration_at is None or state.expiration_at > now:
            continue

        canceled_state = NotificationStateRecord(
            alert_id=state.alert_id,
            token=state.token,
            chain=state.chain,
            alert_type=state.alert_type,
            severity=state.severity,
            score=state.score,
            window_start=state.window_start,
            window_end=state.window_end,
            dedup_key=state.dedup_key,
            payload_json=dict(state.payload_json),
            status=NotificationStatus.CANCELED,
            attempt_count=state.attempt_count,
            max_attempts=state.max_attempts,
            retry_delay_seconds=state.retry_delay_seconds,
            next_retry_at=None,
            last_error="expired",
            created_at=state.created_at,
            updated_at=now,
            sent_at=state.sent_at,
            expiration_at=state.expiration_at,
            canceled_at=now,
            cancellation_reason="expired",
        )
        _upsert_state_record(db_path, canceled_state)
        _append_log(
            log_path,
            AlertExpirationLogEntry(
                alert_id=state.alert_id,
                event=AlertExpirationEvent.EXPIRED,
                expiration_at=state.expiration_at,
                canceled_at=now,
                status=NotificationStatus.CANCELED,
                reason="expired",
            ),
        )
        _append_log(
            log_path,
            AlertExpirationLogEntry(
                alert_id=state.alert_id,
                event=AlertExpirationEvent.CANCELED,
                expiration_at=state.expiration_at,
                canceled_at=now,
                status=NotificationStatus.CANCELED,
                reason="expired",
            ),
        )
        results.append(
            NotificationExpirationResult(
                alert_id=state.alert_id,
                status=NotificationStatus.CANCELED,
                expiration_at=state.expiration_at,
                canceled_at=now,
                was_canceled=True,
                reason="expired",
            )
        )

    return tuple(results)


def read_alert_expiration_log(log_path: str | Path) -> tuple[AlertExpirationLogEntry, ...]:
    path = _normalize_optional_path(log_path)
    if path is None or not path.exists():
        return ()

    entries: list[AlertExpirationLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        raw = json.loads(line)
        entries.append(
            AlertExpirationLogEntry(
                alert_id=raw["alert_id"],
                event=AlertExpirationEvent(raw["event"]),
                expiration_at=datetime.fromisoformat(raw["expiration_at"]),
                canceled_at=datetime.fromisoformat(raw["canceled_at"]) if raw["canceled_at"] is not None else None,
                status=NotificationStatus(raw["status"]),
                reason=raw["reason"],
            )
        )
    return tuple(entries)


def _append_log(log_path: str | Path | None, entry: AlertExpirationLogEntry) -> None:
    if log_path is None:
        return
    path = _normalize_optional_path(log_path)
    if path is None:
        raise TypeError("log_path must be a non-empty string, Path, or None")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_serialize_log_entry(entry), sort_keys=True))
        handle.write("\n")


def _serialize_log_entry(entry: AlertExpirationLogEntry) -> dict[str, Any]:
    return {
        "alert_id": entry.alert_id,
        "canceled_at": entry.canceled_at.isoformat() if entry.canceled_at is not None else None,
        "event": entry.event.value,
        "expiration_at": entry.expiration_at.isoformat(),
        "reason": entry.reason,
        "status": entry.status.value,
    }


def _normalize_optional_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    return None


__all__ = [
    "AlertExpirationEvent",
    "AlertExpirationLogEntry",
    "NotificationExpirationResult",
    "cancel_expired_notifications",
    "read_alert_expiration_log",
]
