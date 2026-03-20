"""Final alert processing verification and reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.persistence import (
    NotificationAttemptRecord,
    NotificationDispatchResult,
    NotificationStateRecord,
    NotificationStatus,
    dispatch_due_notifications,
    read_due_notification_states,
    read_notification_attempts,
    read_notification_states,
)
from fresh_capital.notifications.webhook import (
    AlertNotificationConfig,
    send_single_alert_notification,
)


NotificationSender = Callable[[AlertRecord, AlertNotificationConfig], None]


@dataclass(frozen=True, slots=True)
class AlertNotificationStatusCheck:
    checked_at: datetime
    total_alerts: int
    pending_count: int
    sent_count: int
    failed_count: int
    canceled_count: int
    pending_alert_ids: tuple[str, ...]
    sent_alert_ids: tuple[str, ...]
    failed_alert_ids: tuple[str, ...]
    canceled_alert_ids: tuple[str, ...]
    all_processed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_processed": self.all_processed,
            "checked_at": self.checked_at.isoformat(),
            "canceled_alert_ids": list(self.canceled_alert_ids),
            "canceled_count": self.canceled_count,
            "failed_alert_ids": list(self.failed_alert_ids),
            "failed_count": self.failed_count,
            "pending_alert_ids": list(self.pending_alert_ids),
            "pending_count": self.pending_count,
            "sent_alert_ids": list(self.sent_alert_ids),
            "sent_count": self.sent_count,
            "total_alerts": self.total_alerts,
        }


@dataclass(frozen=True, slots=True)
class AlertNotificationVerificationReport:
    started_at: datetime
    completed_at: datetime
    retry_rounds: int
    status_check: AlertNotificationStatusCheck
    dispatch_results: tuple[NotificationDispatchResult, ...]
    states: tuple[NotificationStateRecord, ...]
    attempts: tuple[NotificationAttemptRecord, ...]
    all_processed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_processed": self.all_processed,
            "attempts": [_serialize_attempt(attempt) for attempt in self.attempts],
            "completed_at": self.completed_at.isoformat(),
            "dispatch_results": [_serialize_dispatch_result(result) for result in self.dispatch_results],
            "retry_rounds": self.retry_rounds,
            "started_at": self.started_at.isoformat(),
            "states": [_serialize_state(state) for state in self.states],
            "status_check": self.status_check.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AlertCompletionStatusReport:
    generated_at: datetime
    db_path: Path
    status_check: AlertNotificationStatusCheck
    processed_successfully_count: int
    pending_count: int
    failed_count: int
    canceled_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "canceled_count": self.canceled_count,
            "db_path": str(self.db_path),
            "failed_count": self.failed_count,
            "final_notification_outcome_summary": {
                "all_processed": self.status_check.all_processed,
                "canceled_count": self.canceled_count,
                "failed_count": self.failed_count,
                "pending_count": self.pending_count,
                "processed_successfully_count": self.processed_successfully_count,
                "sent_count": self.status_check.sent_count,
                "total_alerts": self.status_check.total_alerts,
            },
            "generated_at": self.generated_at.isoformat(),
            "pending_count": self.pending_count,
            "processed_successfully_count": self.processed_successfully_count,
            "status_check": self.status_check.to_dict(),
        }


def check_alert_notification_status(
    db_path: str | Path,
    *,
    checked_at: datetime | None = None,
) -> AlertNotificationStatusCheck:
    """Inspect stored notification states without changing them."""
    now = checked_at or datetime.now(timezone.utc)
    states = read_notification_states(db_path)
    pending_ids: list[str] = []
    sent_ids: list[str] = []
    failed_ids: list[str] = []
    canceled_ids: list[str] = []
    for state in states:
        if state.status == NotificationStatus.PENDING:
            pending_ids.append(state.alert_id)
        elif state.status == NotificationStatus.SENT:
            sent_ids.append(state.alert_id)
        elif state.status == NotificationStatus.CANCELED:
            canceled_ids.append(state.alert_id)
        else:
            failed_ids.append(state.alert_id)

    return AlertNotificationStatusCheck(
        checked_at=now,
        total_alerts=len(states),
        pending_count=len(pending_ids),
        sent_count=len(sent_ids),
        failed_count=len(failed_ids),
        canceled_count=len(canceled_ids),
        pending_alert_ids=tuple(pending_ids),
        sent_alert_ids=tuple(sent_ids),
        failed_alert_ids=tuple(failed_ids),
        canceled_alert_ids=tuple(canceled_ids),
        all_processed=not pending_ids,
    )


def build_alert_completion_status_report(
    db_path: str | Path,
    *,
    checked_at: datetime | None = None,
) -> AlertCompletionStatusReport:
    generated_at = checked_at or datetime.now(timezone.utc)
    normalized_db_path = _normalize_optional_path(db_path)
    if normalized_db_path is None:
        raise TypeError("db_path must be a non-empty string or Path")
    status_check = check_alert_notification_status(db_path, checked_at=generated_at)
    return AlertCompletionStatusReport(
        generated_at=generated_at,
        db_path=normalized_db_path,
        status_check=status_check,
        processed_successfully_count=status_check.sent_count,
        pending_count=status_check.pending_count,
        failed_count=status_check.failed_count,
        canceled_count=status_check.canceled_count,
    )


def verify_alert_notification_processing(
    db_path: str | Path,
    config: AlertNotificationConfig,
    *,
    sender: NotificationSender = send_single_alert_notification,
    started_at: datetime | None = None,
    report_path: str | Path | None = None,
) -> AlertNotificationVerificationReport:
    """Retry due alerts until they are processed or exhausted, then build a final report."""
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")
    if not callable(sender):
        raise TypeError("sender must be callable")

    initial_time = started_at or datetime.now(timezone.utc)
    current_time = initial_time
    initial_states = read_notification_states(db_path)
    max_rounds = max(1, len(initial_states) * max((state.max_attempts for state in initial_states), default=1))
    dispatch_results: list[NotificationDispatchResult] = []
    retry_rounds = 0

    while retry_rounds < max_rounds:
        due_states = read_due_notification_states(db_path, as_of=current_time)
        if not due_states:
            next_retry_at = _next_retry_time(db_path, after=current_time)
            if next_retry_at is None:
                break
            current_time = next_retry_at
            continue

        results = dispatch_due_notifications(db_path, config, sender=sender, as_of=current_time)
        dispatch_results.extend(results)
        retry_rounds += 1

        current_states = read_notification_states(db_path)
        if all(state.status != NotificationStatus.PENDING for state in current_states):
            break

        next_retry_at = _next_retry_time(db_path, after=current_time)
        if next_retry_at is None or next_retry_at <= current_time:
            break
        current_time = next_retry_at

    completed_at = current_time
    status_check = check_alert_notification_status(db_path, checked_at=completed_at)
    attempts = read_notification_attempts(db_path)
    states = read_notification_states(db_path)
    report = AlertNotificationVerificationReport(
        started_at=initial_time,
        completed_at=completed_at,
        retry_rounds=retry_rounds,
        status_check=status_check,
        dispatch_results=tuple(dispatch_results),
        states=states,
        attempts=attempts,
        all_processed=status_check.all_processed,
    )
    if report_path is not None:
        write_alert_notification_verification_report(report, report_path)
    return report


def write_alert_notification_verification_report(
    report: AlertNotificationVerificationReport,
    report_path: str | Path,
) -> Path:
    """Write a deterministic JSON report for the final verification state."""
    if not isinstance(report, AlertNotificationVerificationReport):
        raise TypeError("report must be an AlertNotificationVerificationReport")
    path = _normalize_optional_path(report_path)
    if path is None:
        raise TypeError("report_path must be a non-empty string or Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_alert_completion_status_report(
    report: AlertCompletionStatusReport,
    report_path: str | Path,
) -> Path:
    if not isinstance(report, AlertCompletionStatusReport):
        raise TypeError("report must be an AlertCompletionStatusReport")
    path = _normalize_optional_path(report_path)
    if path is None:
        raise TypeError("report_path must be a non-empty string or Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_alert_completion_status_report(report_path: str | Path) -> AlertCompletionStatusReport:
    path = _normalize_optional_path(report_path)
    if path is None:
        raise TypeError("report_path must be a non-empty string or Path")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("status report root must be a JSON object")
    status_check_payload = payload.get("status_check")
    if not isinstance(status_check_payload, dict):
        raise ValueError("status_check must be a JSON object")
    return AlertCompletionStatusReport(
        generated_at=datetime.fromisoformat(payload["generated_at"]),
        db_path=Path(payload["db_path"]),
        status_check=AlertNotificationStatusCheck(
            checked_at=datetime.fromisoformat(status_check_payload["checked_at"]),
            total_alerts=int(status_check_payload["total_alerts"]),
            pending_count=int(status_check_payload["pending_count"]),
            sent_count=int(status_check_payload["sent_count"]),
            failed_count=int(status_check_payload["failed_count"]),
            canceled_count=int(status_check_payload["canceled_count"]),
            pending_alert_ids=tuple(status_check_payload["pending_alert_ids"]),
            sent_alert_ids=tuple(status_check_payload["sent_alert_ids"]),
            failed_alert_ids=tuple(status_check_payload["failed_alert_ids"]),
            canceled_alert_ids=tuple(status_check_payload["canceled_alert_ids"]),
            all_processed=bool(status_check_payload["all_processed"]),
        ),
        processed_successfully_count=int(payload["processed_successfully_count"]),
        pending_count=int(payload["pending_count"]),
        failed_count=int(payload["failed_count"]),
        canceled_count=int(payload["canceled_count"]),
    )


def _next_retry_time(db_path: str | Path, *, after: datetime) -> datetime | None:
    future_times = [
        state.next_retry_at
        for state in read_notification_states(db_path)
        if state.status == NotificationStatus.PENDING
        and state.attempt_count < state.max_attempts
        and state.next_retry_at is not None
        and state.next_retry_at > after
    ]
    if not future_times:
        return None
    return min(future_times)


def _serialize_state(state: NotificationStateRecord) -> dict[str, Any]:
    return {
        "alert_id": state.alert_id,
        "attempt_count": state.attempt_count,
        "chain": state.chain,
        "created_at": state.created_at.isoformat(),
        "dedup_key": state.dedup_key,
        "last_error": state.last_error,
        "max_attempts": state.max_attempts,
        "next_retry_at": state.next_retry_at.isoformat() if state.next_retry_at is not None else None,
        "payload_json": dict(state.payload_json),
        "retry_delay_seconds": state.retry_delay_seconds,
        "score": state.score,
        "sent_at": state.sent_at.isoformat() if state.sent_at is not None else None,
        "severity": state.severity.value,
        "status": state.status.value,
        "token": state.token,
        "updated_at": state.updated_at.isoformat(),
        "window_end": state.window_end.isoformat(),
        "window_start": state.window_start.isoformat(),
    }


def _serialize_attempt(attempt: NotificationAttemptRecord) -> dict[str, Any]:
    return {
        "alert_id": attempt.alert_id,
        "attempted_at": attempt.attempted_at.isoformat(),
        "attempt_number": attempt.attempt_number,
        "error": attempt.error,
        "next_retry_at": attempt.next_retry_at.isoformat() if attempt.next_retry_at is not None else None,
        "status": attempt.status.value,
    }


def _serialize_dispatch_result(result: NotificationDispatchResult) -> dict[str, Any]:
    return {
        "alert_id": result.alert_id,
        "attempt_number": result.attempt_number,
        "error": result.error,
        "is_delivered": result.is_delivered,
        "status": result.status.value,
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
    "AlertCompletionStatusReport",
    "AlertNotificationStatusCheck",
    "AlertNotificationVerificationReport",
    "build_alert_completion_status_report",
    "check_alert_notification_status",
    "read_alert_completion_status_report",
    "verify_alert_notification_processing",
    "write_alert_completion_status_report",
    "write_alert_notification_verification_report",
]
