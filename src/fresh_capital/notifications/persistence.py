"""SQLite persistence for alert notification status and retry attempts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fresh_capital.domain.enums import AlertType, Severity, StrEnum
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.retry import AlertRetryStatus
from fresh_capital.notifications.webhook import (
    AlertNotificationConfig,
    send_single_alert_notification,
)


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class NotificationAttemptRecord:
    alert_id: str
    attempt_number: int
    status: AlertRetryStatus
    attempted_at: datetime
    next_retry_at: datetime | None
    error: str | None


@dataclass(frozen=True, slots=True)
class NotificationStateRecord:
    alert_id: str
    token: str
    chain: str
    alert_type: AlertType
    severity: Severity
    score: float
    window_start: datetime
    window_end: datetime
    dedup_key: str
    payload_json: dict[str, Any]
    status: NotificationStatus
    attempt_count: int
    max_attempts: int
    retry_delay_seconds: float
    next_retry_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
    expiration_at: datetime | None = None
    canceled_at: datetime | None = None
    cancellation_reason: str | None = None

    def to_alert_record(self) -> AlertRecord:
        return AlertRecord(
            alert_id=self.alert_id,
            token=self.token,
            chain=self.chain,
            alert_type=self.alert_type,
            severity=self.severity,
            score=self.score,
            window_start=self.window_start,
            window_end=self.window_end,
            dedup_key=self.dedup_key,
            payload_json=dict(self.payload_json),
            created_at=self.created_at,
            updated_at=self.updated_at,
            sent=self.status == NotificationStatus.SENT,
        )


@dataclass(frozen=True, slots=True)
class NotificationDispatchResult:
    alert_id: str
    status: NotificationStatus
    attempt_number: int
    is_delivered: bool
    error: str | None


NotificationSender = Callable[[AlertRecord, AlertNotificationConfig], None]


def initialize_notification_store(db_path: str | Path) -> None:
    conn = _open_database(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_alerts (
                alert_id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                chain TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                score REAL NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                dedup_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                retry_delay_seconds REAL NOT NULL,
                next_retry_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sent_at TEXT,
                expiration_at TEXT,
                canceled_at TEXT,
                cancellation_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                next_retry_at TEXT,
                error TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def queue_notification_alert(
    alert_record: AlertRecord,
    db_path: str | Path,
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 300.0,
    expiration_at: datetime | None = None,
    expiration_seconds: float = 3600.0,
    queued_at: datetime | None = None,
) -> None:
    if not isinstance(alert_record, AlertRecord):
        raise TypeError("alert_record must be an AlertRecord")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must be non-negative")
    if expiration_at is not None and not isinstance(expiration_at, datetime):
        raise TypeError("expiration_at must be a datetime or None")
    if expiration_seconds <= 0:
        raise ValueError("expiration_seconds must be positive")

    initialize_notification_store(db_path)
    now = queued_at or datetime.now(timezone.utc)
    resolved_expiration_at = expiration_at or (now + _delay_as_timedelta(expiration_seconds))
    state = NotificationStateRecord(
        alert_id=alert_record.alert_id,
        token=alert_record.token,
        chain=alert_record.chain,
        alert_type=alert_record.alert_type,
        severity=alert_record.severity,
        score=alert_record.score,
        window_start=alert_record.window_start,
        window_end=alert_record.window_end,
        dedup_key=alert_record.dedup_key,
        payload_json=dict(alert_record.payload_json),
        status=NotificationStatus.PENDING,
        attempt_count=0,
        max_attempts=max_attempts,
        retry_delay_seconds=retry_delay_seconds,
        next_retry_at=now,
        last_error=None,
        created_at=now,
        updated_at=now,
        sent_at=None,
        expiration_at=resolved_expiration_at,
        canceled_at=None,
        cancellation_reason=None,
    )
    _upsert_state_record(db_path, state)


def send_and_persist_notifications(
    alert_records: tuple[AlertRecord, ...] | list[AlertRecord],
    config: AlertNotificationConfig,
    db_path: str | Path,
    *,
    sender: NotificationSender = send_single_alert_notification,
    started_at: datetime | None = None,
    expiration_at: datetime | None = None,
    expiration_seconds: float = 3600.0,
    expiration_log_path: str | Path | None = None,
) -> tuple[NotificationDispatchResult, ...]:
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")
    if not callable(sender):
        raise TypeError("sender must be callable")

    normalized_records = tuple(alert_records)
    for alert_record in normalized_records:
        queue_notification_alert(
            alert_record,
            db_path,
            max_attempts=config.max_attempts,
            retry_delay_seconds=config.retry_delay_seconds,
            expiration_at=expiration_at,
            expiration_seconds=expiration_seconds,
            queued_at=started_at,
        )
    return dispatch_due_notifications(
        db_path,
        config,
        sender=sender,
        as_of=started_at,
        expiration_log_path=expiration_log_path,
    )


def dispatch_due_notifications(
    db_path: str | Path,
    config: AlertNotificationConfig,
    *,
    sender: NotificationSender = send_single_alert_notification,
    as_of: datetime | None = None,
    expiration_log_path: str | Path | None = None,
) -> tuple[NotificationDispatchResult, ...]:
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")
    if not callable(sender):
        raise TypeError("sender must be callable")

    now = as_of or datetime.now(timezone.utc)
    from fresh_capital.notifications.expiration import cancel_expired_notifications

    cancel_expired_notifications(db_path, as_of=now, log_path=expiration_log_path)
    states = read_due_notification_states(db_path, as_of=now)
    results: list[NotificationDispatchResult] = []
    for state in states:
        alert_record = state.to_alert_record()
        attempt_number = state.attempt_count + 1
        try:
            sender(alert_record, config)
        except Exception as exc:  # noqa: BLE001 - local delivery failure is part of the contract
            status = NotificationStatus.FAILED if attempt_number >= state.max_attempts else NotificationStatus.PENDING
            next_retry_at = None
            if status == NotificationStatus.PENDING:
                next_retry_at = now + _delay_as_timedelta(state.retry_delay_seconds)
            _append_attempt(
                db_path,
                NotificationAttemptRecord(
                    alert_id=state.alert_id,
                    attempt_number=attempt_number,
                    status=AlertRetryStatus.FAILED if status == NotificationStatus.FAILED else AlertRetryStatus.RETRYING,
                    attempted_at=now,
                    next_retry_at=next_retry_at,
                    error=str(exc),
                ),
            )
            _upsert_state_record(
                db_path,
                _updated_state_after_attempt(
                    state,
                    attempt_number=attempt_number,
                    status=status,
                    next_retry_at=next_retry_at,
                    error=str(exc),
                    updated_at=now,
                ),
            )
            results.append(
                NotificationDispatchResult(
                    alert_id=state.alert_id,
                    status=status,
                    attempt_number=attempt_number,
                    is_delivered=False,
                    error=str(exc),
                )
            )
            continue

        _append_attempt(
            db_path,
            NotificationAttemptRecord(
                alert_id=state.alert_id,
                attempt_number=attempt_number,
                status=AlertRetryStatus.SENT,
                attempted_at=now,
                next_retry_at=None,
                error=None,
            ),
        )
        _upsert_state_record(
            db_path,
            _updated_state_after_attempt(
                state,
                attempt_number=attempt_number,
                status=NotificationStatus.SENT,
                next_retry_at=None,
                error=None,
                updated_at=now,
                sent_at=now,
            ),
        )
        results.append(
            NotificationDispatchResult(
                alert_id=state.alert_id,
                status=NotificationStatus.SENT,
                attempt_number=attempt_number,
                is_delivered=True,
                error=None,
            )
        )
    return tuple(results)


def read_notification_states(db_path: str | Path) -> tuple[NotificationStateRecord, ...]:
    initialize_notification_store(db_path)
    conn = _open_database(db_path)
    try:
        rows = conn.execute(
            """
            SELECT alert_id, token, chain, alert_type, severity, score, window_start, window_end,
                   dedup_key, payload_json, status, attempt_count, max_attempts, retry_delay_seconds,
                   next_retry_at, last_error, created_at, updated_at, sent_at,
                   expiration_at, canceled_at, cancellation_reason
            FROM notification_alerts
            ORDER BY updated_at, alert_id
            """
        ).fetchall()
    finally:
        conn.close()

    return tuple(_row_to_state(row) for row in rows)


def read_notification_attempts(
    db_path: str | Path,
    *,
    alert_id: str | None = None,
) -> tuple[NotificationAttemptRecord, ...]:
    initialize_notification_store(db_path)
    conn = _open_database(db_path)
    try:
        if alert_id is None:
            rows = conn.execute(
                """
                SELECT alert_id, attempt_number, status, attempted_at, next_retry_at, error
                FROM notification_attempts
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT alert_id, attempt_number, status, attempted_at, next_retry_at, error
                FROM notification_attempts
                WHERE alert_id = ?
                ORDER BY id
                """,
                (alert_id,),
            ).fetchall()
    finally:
        conn.close()

    return tuple(_row_to_attempt(row) for row in rows)


def read_due_notification_states(
    db_path: str | Path,
    *,
    as_of: datetime | None = None,
) -> tuple[NotificationStateRecord, ...]:
    now = as_of or datetime.now(timezone.utc)
    states = read_notification_states(db_path)
    due_states: list[NotificationStateRecord] = []
    for state in states:
        if state.status == NotificationStatus.SENT:
            continue
        if state.status == NotificationStatus.CANCELED:
            continue
        if state.expiration_at is not None and state.expiration_at <= now:
            continue
        if state.attempt_count >= state.max_attempts:
            continue
        if state.next_retry_at is not None and state.next_retry_at > now:
            continue
        due_states.append(state)
    return tuple(due_states)


def resend_undelivered_notifications(
    db_path: str | Path,
    config: AlertNotificationConfig,
    *,
    sender: NotificationSender = send_single_alert_notification,
    as_of: datetime | None = None,
    expiration_log_path: str | Path | None = None,
) -> tuple[NotificationDispatchResult, ...]:
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")
    if not callable(sender):
        raise TypeError("sender must be callable")
    return dispatch_due_notifications(
        db_path,
        config,
        sender=sender,
        as_of=as_of,
        expiration_log_path=expiration_log_path,
    )


def _updated_state_after_attempt(
    state: NotificationStateRecord,
    *,
    attempt_number: int,
    status: NotificationStatus,
    next_retry_at: datetime | None,
    error: str | None,
    updated_at: datetime,
    sent_at: datetime | None = None,
) -> NotificationStateRecord:
    return NotificationStateRecord(
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
        status=status,
        attempt_count=attempt_number,
        max_attempts=state.max_attempts,
        retry_delay_seconds=state.retry_delay_seconds,
        next_retry_at=next_retry_at,
        last_error=error,
        created_at=state.created_at,
        updated_at=updated_at,
        sent_at=sent_at if sent_at is not None else state.sent_at,
        expiration_at=state.expiration_at,
        canceled_at=state.canceled_at,
        cancellation_reason=state.cancellation_reason,
    )


def _upsert_state_record(db_path: str | Path, state: NotificationStateRecord) -> None:
    initialize_notification_store(db_path)
    conn = _open_database(db_path)
    try:
        conn.execute(
            """
            INSERT INTO notification_alerts (
                alert_id, token, chain, alert_type, severity, score, window_start, window_end,
                dedup_key, payload_json, status, attempt_count, max_attempts, retry_delay_seconds,
                next_retry_at, last_error, created_at, updated_at, sent_at,
                expiration_at, canceled_at, cancellation_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_id) DO UPDATE SET
                token = excluded.token,
                chain = excluded.chain,
                alert_type = excluded.alert_type,
                severity = excluded.severity,
                score = excluded.score,
                window_start = excluded.window_start,
                window_end = excluded.window_end,
                dedup_key = excluded.dedup_key,
                payload_json = excluded.payload_json,
                status = excluded.status,
                attempt_count = excluded.attempt_count,
                max_attempts = excluded.max_attempts,
                retry_delay_seconds = excluded.retry_delay_seconds,
                next_retry_at = excluded.next_retry_at,
                last_error = excluded.last_error,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                sent_at = excluded.sent_at,
                expiration_at = excluded.expiration_at,
                canceled_at = excluded.canceled_at,
                cancellation_reason = excluded.cancellation_reason
            """,
            (
                state.alert_id,
                state.token,
                state.chain,
                state.alert_type.value,
                state.severity.value,
                state.score,
                state.window_start.isoformat(),
                state.window_end.isoformat(),
                state.dedup_key,
                json.dumps(state.payload_json, sort_keys=True),
                state.status.value,
                state.attempt_count,
                state.max_attempts,
                state.retry_delay_seconds,
                state.next_retry_at.isoformat() if state.next_retry_at is not None else None,
                state.last_error,
                state.created_at.isoformat(),
                state.updated_at.isoformat(),
                state.sent_at.isoformat() if state.sent_at is not None else None,
                state.expiration_at.isoformat() if state.expiration_at is not None else None,
                state.canceled_at.isoformat() if state.canceled_at is not None else None,
                state.cancellation_reason,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _append_attempt(db_path: str | Path, attempt: NotificationAttemptRecord) -> None:
    initialize_notification_store(db_path)
    conn = _open_database(db_path)
    try:
        conn.execute(
            """
            INSERT INTO notification_attempts (
                alert_id, attempt_number, status, attempted_at, next_retry_at, error
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.alert_id,
                attempt.attempt_number,
                attempt.status.value,
                attempt.attempted_at.isoformat(),
                attempt.next_retry_at.isoformat() if attempt.next_retry_at is not None else None,
                attempt.error,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_state(row: tuple[Any, ...]) -> NotificationStateRecord:
    return NotificationStateRecord(
        alert_id=row[0],
        token=row[1],
        chain=row[2],
        alert_type=AlertType(row[3]),
        severity=Severity(row[4]),
        score=row[5],
        window_start=datetime.fromisoformat(row[6]),
        window_end=datetime.fromisoformat(row[7]),
        dedup_key=row[8],
        payload_json=json.loads(row[9]),
        status=NotificationStatus(row[10]),
        attempt_count=int(row[11]),
        max_attempts=int(row[12]),
        retry_delay_seconds=float(row[13]),
        next_retry_at=datetime.fromisoformat(row[14]) if row[14] is not None else None,
        last_error=row[15],
        created_at=datetime.fromisoformat(row[16]),
        updated_at=datetime.fromisoformat(row[17]),
        sent_at=datetime.fromisoformat(row[18]) if row[18] is not None else None,
        expiration_at=datetime.fromisoformat(row[19]) if len(row) > 19 and row[19] is not None else None,
        canceled_at=datetime.fromisoformat(row[20]) if len(row) > 20 and row[20] is not None else None,
        cancellation_reason=row[21] if len(row) > 21 else None,
    )


def _row_to_attempt(row: tuple[Any, ...]) -> NotificationAttemptRecord:
    return NotificationAttemptRecord(
        alert_id=row[0],
        attempt_number=int(row[1]),
        status=AlertRetryStatus(row[2]),
        attempted_at=datetime.fromisoformat(row[3]),
        next_retry_at=datetime.fromisoformat(row[4]) if row[4] is not None else None,
        error=row[5],
    )


def _open_database(db_path: str | Path) -> sqlite3.Connection:
    path = _normalize_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def _normalize_path(path_value: str | Path) -> Path:
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    raise TypeError("db_path must be a non-empty string or Path")


def _delay_as_timedelta(delay_seconds: float) -> Any:
    from datetime import timedelta

    return timedelta(seconds=delay_seconds)
