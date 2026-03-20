"""Deterministic retry scheduling and logging for alert delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fresh_capital.domain.enums import StrEnum
from fresh_capital.domain.models import AlertRecord


class AlertRetryStatus(StrEnum):
    SENT = "sent"
    RETRYING = "retrying"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AlertRetryPolicy:
    max_attempts: int = 3
    retry_delay_seconds: float = 300.0


@dataclass(frozen=True, slots=True)
class AlertRetryAttempt:
    alert_id: str
    attempt_number: int
    status: AlertRetryStatus
    scheduled_for: datetime
    executed_at: datetime
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AlertRetryResult:
    alert_id: str
    is_delivered: bool
    attempts: tuple[AlertRetryAttempt, ...]
    final_status: AlertRetryStatus
    error_message: str | None


SendOnce = Callable[[AlertRecord], None]


def execute_alert_delivery_with_retry(
    alert_records: tuple[AlertRecord, ...] | list[AlertRecord],
    policy: AlertRetryPolicy,
    send_once: SendOnce,
    *,
    log_path: str | Path | None = None,
    started_at: datetime | None = None,
) -> tuple[AlertRetryResult, ...]:
    """Retry alert delivery deterministically without sleeping."""
    if not isinstance(policy, AlertRetryPolicy):
        raise TypeError("policy must be an AlertRetryPolicy")
    if policy.max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if policy.retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must be non-negative")
    if not callable(send_once):
        raise TypeError("send_once must be callable")

    normalized_records = tuple(alert_records)
    for record in normalized_records:
        if not isinstance(record, AlertRecord):
            raise TypeError("alert_records must contain AlertRecord instances")

    base_time = started_at or datetime.now(timezone.utc)
    normalized_log_path = _normalize_optional_path(log_path)
    results: list[AlertRetryResult] = []

    for alert_record in normalized_records:
        attempts: list[AlertRetryAttempt] = []
        error_message: str | None = None
        delivered = False
        for attempt_number in range(1, policy.max_attempts + 1):
            scheduled_for = _scheduled_for(base_time, policy.retry_delay_seconds, attempt_number)
            executed_at = scheduled_for
            try:
                send_once(alert_record)
            except Exception as exc:  # noqa: BLE001 - deterministic delivery failures are part of the contract
                error_message = str(exc)
                status = (
                    AlertRetryStatus.RETRYING
                    if attempt_number < policy.max_attempts
                    else AlertRetryStatus.FAILED
                )
                attempt = AlertRetryAttempt(
                    alert_id=alert_record.alert_id,
                    attempt_number=attempt_number,
                    status=status,
                    scheduled_for=scheduled_for,
                    executed_at=executed_at,
                    error=error_message,
                )
                attempts.append(attempt)
                _append_log_entry(normalized_log_path, attempt)
                continue

            delivered = True
            attempt = AlertRetryAttempt(
                alert_id=alert_record.alert_id,
                attempt_number=attempt_number,
                status=AlertRetryStatus.SENT,
                scheduled_for=scheduled_for,
                executed_at=executed_at,
                error=None,
            )
            attempts.append(attempt)
            _append_log_entry(normalized_log_path, attempt)
            break

        results.append(
            AlertRetryResult(
                alert_id=alert_record.alert_id,
                is_delivered=delivered,
                attempts=tuple(attempts),
                final_status=AlertRetryStatus.SENT if delivered else AlertRetryStatus.FAILED,
                error_message=None if delivered else error_message,
            )
        )

    return tuple(results)


def read_alert_retry_log(log_path: str | Path) -> tuple[AlertRetryAttempt, ...]:
    """Read deterministic retry log entries from a local JSONL file."""
    path = _normalize_optional_path(log_path)
    if path is None or not path.exists():
        return ()

    entries: list[AlertRetryAttempt] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        raw = json.loads(line)
        entries.append(
            AlertRetryAttempt(
                alert_id=raw["alert_id"],
                attempt_number=int(raw["attempt_number"]),
                status=AlertRetryStatus(raw["status"]),
                scheduled_for=datetime.fromisoformat(raw["scheduled_for"]),
                executed_at=datetime.fromisoformat(raw["executed_at"]),
                error=raw["error"],
            )
        )
    return tuple(entries)


def _scheduled_for(base_time: datetime, delay_seconds: float, attempt_number: int) -> datetime:
    return base_time + timedelta(seconds=delay_seconds * (attempt_number - 1))


def _append_log_entry(log_path: Path | None, attempt: AlertRetryAttempt) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_serialize_attempt(attempt), sort_keys=True))
        handle.write("\n")


def _serialize_attempt(attempt: AlertRetryAttempt) -> dict[str, Any]:
    return {
        "alert_id": attempt.alert_id,
        "attempt_number": attempt.attempt_number,
        "error": attempt.error,
        "executed_at": attempt.executed_at.isoformat(),
        "scheduled_for": attempt.scheduled_for.isoformat(),
        "status": attempt.status.value,
    }


def _normalize_optional_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    raise TypeError("log_path must be a non-empty string, Path, or None")
