"""Alert scheduling built on the existing notification persistence layer."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fresh_capital.domain.enums import AlertType, Severity, StrEnum
from fresh_capital.domain.models import AlertRecord
from fresh_capital.notifications.prioritization import (
    AlertPriority,
    classify_alert_priority,
    log_alert_priority_assignment,
    normalize_alert_priority,
)
from fresh_capital.notifications.persistence import (
    NotificationDispatchResult,
    dispatch_due_notifications,
    _priority_rank,
    send_and_persist_notifications,
)
from fresh_capital.notifications.webhook import (
    AlertNotificationConfig,
    send_single_alert_notification,
)


class AlertScheduleKind(StrEnum):
    AT_TIME = "at_time"
    DELAY = "delay"
    INTERVAL = "interval"


class AlertScheduleStatus(StrEnum):
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"


class AlertScheduleEvent(StrEnum):
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class AlertScheduleRecord:
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
    priority: AlertPriority
    priority_assigned_at: datetime | None
    priority_reason: str | None
    schedule_kind: AlertScheduleKind
    scheduled_for: datetime
    interval_seconds: float | None
    delay_seconds: float | None
    status: AlertScheduleStatus
    trigger_count: int
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_triggered_at: datetime | None
    last_error: str | None

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
            sent=False,
        )


@dataclass(frozen=True, slots=True)
class AlertScheduleLogEntry:
    alert_id: str
    event: AlertScheduleEvent
    schedule_kind: AlertScheduleKind
    scheduled_for: datetime
    triggered_at: datetime | None
    next_run_at: datetime | None
    status: AlertScheduleStatus
    delivery_status: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class AlertScheduleProcessingResult:
    alert_id: str
    status: AlertScheduleStatus
    notification_results: tuple[NotificationDispatchResult, ...]
    next_run_at: datetime | None
    was_rescheduled: bool


NotificationSender = Callable[[AlertRecord, AlertNotificationConfig], None]


def initialize_alert_schedule_store(db_path: str | Path) -> None:
    conn = _open_database(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_schedules (
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
                priority TEXT NOT NULL,
                priority_assigned_at TEXT,
                priority_reason TEXT,
                schedule_kind TEXT NOT NULL,
                scheduled_for TEXT NOT NULL,
                interval_seconds REAL,
                delay_seconds REAL,
                status TEXT NOT NULL,
                trigger_count INTEGER NOT NULL,
                next_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_triggered_at TEXT,
                last_error TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def schedule_alert_notification(
    alert_record: AlertRecord,
    db_path: str | Path,
    *,
    scheduled_for: datetime | None = None,
    delay_seconds: float | None = None,
    interval_seconds: float | None = None,
    created_at: datetime | None = None,
    priority: AlertPriority | str | None = None,
    priority_reason: str | None = None,
    priority_assigned_at: datetime | None = None,
    priority_log_path: str | Path | None = None,
    log_path: str | Path | None = None,
) -> None:
    if not isinstance(alert_record, AlertRecord):
        raise TypeError("alert_record must be an AlertRecord")
    if delay_seconds is not None and delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    if interval_seconds is not None and interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    now = created_at or datetime.now(timezone.utc)
    normalized_priority = (
        classify_alert_priority(alert_record)
        if priority is None
        else normalize_alert_priority(priority)
    )
    assigned_at = priority_assigned_at or now
    initialized_scheduled_for = _resolve_initial_schedule_time(
        scheduled_for=scheduled_for,
        delay_seconds=delay_seconds,
        interval_seconds=interval_seconds,
        created_at=now,
    )
    schedule_kind = _resolve_schedule_kind(
        scheduled_for=scheduled_for,
        delay_seconds=delay_seconds,
        interval_seconds=interval_seconds,
    )
    record = AlertScheduleRecord(
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
        priority=normalized_priority,
        priority_assigned_at=assigned_at,
        priority_reason=priority_reason,
        schedule_kind=schedule_kind,
        scheduled_for=initialized_scheduled_for,
        interval_seconds=interval_seconds,
        delay_seconds=delay_seconds,
        status=AlertScheduleStatus.SCHEDULED,
        trigger_count=0,
        next_run_at=initialized_scheduled_for,
        created_at=now,
        updated_at=now,
        last_triggered_at=None,
        last_error=None,
    )
    initialize_alert_schedule_store(db_path)
    _upsert_schedule_record(db_path, record)
    log_alert_priority_assignment(
        alert_id=record.alert_id,
        priority=normalized_priority,
        assigned_at=assigned_at,
        reason=priority_reason or "classified",
        log_path=priority_log_path,
    )
    _append_schedule_log(
        log_path,
        AlertScheduleLogEntry(
            alert_id=record.alert_id,
            event=AlertScheduleEvent.SCHEDULED,
            schedule_kind=record.schedule_kind,
            scheduled_for=record.scheduled_for,
            triggered_at=None,
            next_run_at=record.next_run_at,
            status=record.status,
            delivery_status=None,
            error=None,
        ),
    )


def read_alert_schedules(db_path: str | Path) -> tuple[AlertScheduleRecord, ...]:
    initialize_alert_schedule_store(db_path)
    conn = _open_database(db_path)
    try:
        rows = conn.execute(
            """
            SELECT alert_id, token, chain, alert_type, severity, score, window_start, window_end,
                   dedup_key, payload_json, priority, priority_assigned_at, priority_reason,
                   schedule_kind, scheduled_for, interval_seconds, delay_seconds,
                   status, trigger_count, next_run_at, created_at, updated_at, last_triggered_at, last_error
            FROM alert_schedules
            ORDER BY
                CASE priority
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    WHEN 'low' THEN 2
                    ELSE 3
                END,
                scheduled_for,
                alert_id
            """
        ).fetchall()
    finally:
        conn.close()
    return tuple(_row_to_schedule(row) for row in rows)


def read_due_alert_schedules(
    db_path: str | Path,
    *,
    as_of: datetime | None = None,
) -> tuple[AlertScheduleRecord, ...]:
    now = as_of or datetime.now(timezone.utc)
    due: list[AlertScheduleRecord] = []
    for record in read_alert_schedules(db_path):
        if record.status not in (AlertScheduleStatus.SCHEDULED, AlertScheduleStatus.RESCHEDULED):
            continue
        if record.next_run_at is not None and record.next_run_at > now:
            continue
        due.append(record)
    due.sort(key=lambda record: (_priority_rank(record.priority), record.next_run_at or record.scheduled_for, record.alert_id))
    return tuple(due)


def process_due_alert_schedules(
    db_path: str | Path,
    notification_config: AlertNotificationConfig,
    *,
    sender: NotificationSender = send_single_alert_notification,
    as_of: datetime | None = None,
    priority_log_path: str | Path | None = None,
    log_path: str | Path | None = None,
) -> tuple[AlertScheduleProcessingResult, ...]:
    if not isinstance(notification_config, AlertNotificationConfig):
        raise TypeError("notification_config must be an AlertNotificationConfig")
    if not callable(sender):
        raise TypeError("sender must be callable")

    now = as_of or datetime.now(timezone.utc)
    due_records = read_due_alert_schedules(db_path, as_of=now)
    results: list[AlertScheduleProcessingResult] = []

    for schedule in due_records:
        delivery_results = send_and_persist_notifications(
            (schedule.to_alert_record(),),
            notification_config,
            db_path,
            sender=sender,
            started_at=now,
            priority=schedule.priority,
            priority_reason=schedule.priority_reason,
            priority_assigned_at=schedule.priority_assigned_at,
            priority_log_path=priority_log_path,
        )
        delivery_result = delivery_results[0]
        updated_schedule = _advance_schedule(
            schedule,
            triggered_at=now,
            delivery_result=delivery_result,
        )
        _upsert_schedule_record(db_path, updated_schedule)
        _append_schedule_log(
            log_path,
            AlertScheduleLogEntry(
                alert_id=schedule.alert_id,
                event=AlertScheduleEvent.TRIGGERED,
                schedule_kind=schedule.schedule_kind,
                scheduled_for=schedule.scheduled_for,
                triggered_at=now,
                next_run_at=updated_schedule.next_run_at,
                status=updated_schedule.status,
                delivery_status=delivery_result.status.value,
                error=delivery_result.error,
            ),
        )
        _append_schedule_log(
            log_path,
            AlertScheduleLogEntry(
                alert_id=schedule.alert_id,
                event=AlertScheduleEvent.RESCHEDULED if updated_schedule.status == AlertScheduleStatus.RESCHEDULED else AlertScheduleEvent.COMPLETED,
                schedule_kind=schedule.schedule_kind,
                scheduled_for=schedule.scheduled_for,
                triggered_at=now,
                next_run_at=updated_schedule.next_run_at,
                status=updated_schedule.status,
                delivery_status=delivery_result.status.value,
                error=delivery_result.error,
            ),
        )
        results.append(
            AlertScheduleProcessingResult(
                alert_id=schedule.alert_id,
                status=updated_schedule.status,
                notification_results=delivery_results,
                next_run_at=updated_schedule.next_run_at,
                was_rescheduled=updated_schedule.status == AlertScheduleStatus.RESCHEDULED,
            )
        )

    return tuple(results)


def read_alert_schedule_log(log_path: str | Path) -> tuple[AlertScheduleLogEntry, ...]:
    path = _normalize_optional_path(log_path)
    if path is None or not path.exists():
        return ()

    entries: list[AlertScheduleLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        raw = json.loads(line)
        entries.append(
            AlertScheduleLogEntry(
                alert_id=raw["alert_id"],
                event=AlertScheduleEvent(raw["event"]),
                schedule_kind=AlertScheduleKind(raw["schedule_kind"]),
                scheduled_for=datetime.fromisoformat(raw["scheduled_for"]),
                triggered_at=datetime.fromisoformat(raw["triggered_at"]) if raw["triggered_at"] is not None else None,
                next_run_at=datetime.fromisoformat(raw["next_run_at"]) if raw["next_run_at"] is not None else None,
                status=AlertScheduleStatus(raw["status"]),
                delivery_status=raw["delivery_status"],
                error=raw["error"],
            )
        )
    return tuple(entries)


def _advance_schedule(
    schedule: AlertScheduleRecord,
    *,
    triggered_at: datetime,
    delivery_result: NotificationDispatchResult,
) -> AlertScheduleRecord:
    if schedule.interval_seconds is None:
        return AlertScheduleRecord(
            alert_id=schedule.alert_id,
            token=schedule.token,
            chain=schedule.chain,
            alert_type=schedule.alert_type,
            severity=schedule.severity,
            score=schedule.score,
            window_start=schedule.window_start,
            window_end=schedule.window_end,
            dedup_key=schedule.dedup_key,
            payload_json=dict(schedule.payload_json),
            priority=schedule.priority,
            priority_assigned_at=schedule.priority_assigned_at,
            priority_reason=schedule.priority_reason,
            schedule_kind=schedule.schedule_kind,
            scheduled_for=schedule.scheduled_for,
            interval_seconds=schedule.interval_seconds,
            delay_seconds=schedule.delay_seconds,
            status=AlertScheduleStatus.COMPLETED,
            trigger_count=schedule.trigger_count + 1,
            next_run_at=None,
            created_at=schedule.created_at,
            updated_at=triggered_at,
            last_triggered_at=triggered_at,
            last_error=delivery_result.error,
        )

    next_run_at = _next_interval_run_at(
        schedule.scheduled_for if schedule.trigger_count == 0 else schedule.next_run_at or schedule.scheduled_for,
        schedule.interval_seconds,
        triggered_at,
    )
    return AlertScheduleRecord(
        alert_id=schedule.alert_id,
        token=schedule.token,
        chain=schedule.chain,
        alert_type=schedule.alert_type,
        severity=schedule.severity,
        score=schedule.score,
        window_start=schedule.window_start,
        window_end=schedule.window_end,
        dedup_key=schedule.dedup_key,
        payload_json=dict(schedule.payload_json),
        priority=schedule.priority,
        priority_assigned_at=schedule.priority_assigned_at,
        priority_reason=schedule.priority_reason,
        schedule_kind=schedule.schedule_kind,
        scheduled_for=schedule.scheduled_for,
        interval_seconds=schedule.interval_seconds,
        delay_seconds=schedule.delay_seconds,
        status=AlertScheduleStatus.RESCHEDULED,
        trigger_count=schedule.trigger_count + 1,
        next_run_at=next_run_at,
        created_at=schedule.created_at,
        updated_at=triggered_at,
        last_triggered_at=triggered_at,
        last_error=delivery_result.error,
    )


def _next_interval_run_at(base_run_at: datetime, interval_seconds: float, as_of: datetime) -> datetime:
    next_run_at = base_run_at
    interval = timedelta(seconds=interval_seconds)
    while next_run_at <= as_of:
        next_run_at = next_run_at + interval
    return next_run_at


def _resolve_schedule_kind(
    *,
    scheduled_for: datetime | None,
    delay_seconds: float | None,
    interval_seconds: float | None,
) -> AlertScheduleKind:
    if interval_seconds is not None:
        return AlertScheduleKind.INTERVAL
    if delay_seconds is not None:
        return AlertScheduleKind.DELAY
    if scheduled_for is not None:
        return AlertScheduleKind.AT_TIME
    raise ValueError("one of scheduled_for, delay_seconds, or interval_seconds must be provided")


def _resolve_initial_schedule_time(
    *,
    scheduled_for: datetime | None,
    delay_seconds: float | None,
    interval_seconds: float | None,
    created_at: datetime,
) -> datetime:
    if scheduled_for is not None:
        return scheduled_for
    if delay_seconds is not None:
        return created_at + timedelta(seconds=delay_seconds)
    if interval_seconds is not None:
        return created_at + timedelta(seconds=interval_seconds)
    raise ValueError("one of scheduled_for, delay_seconds, or interval_seconds must be provided")


def _upsert_schedule_record(db_path: str | Path, record: AlertScheduleRecord) -> None:
    initialize_alert_schedule_store(db_path)
    conn = _open_database(db_path)
    try:
        conn.execute(
            """
            INSERT INTO alert_schedules (
                alert_id, token, chain, alert_type, severity, score, window_start, window_end,
                dedup_key, payload_json, priority, priority_assigned_at, priority_reason,
                schedule_kind, scheduled_for, interval_seconds, delay_seconds,
                status, trigger_count, next_run_at, created_at, updated_at, last_triggered_at, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                priority = excluded.priority,
                priority_assigned_at = excluded.priority_assigned_at,
                priority_reason = excluded.priority_reason,
                schedule_kind = excluded.schedule_kind,
                scheduled_for = excluded.scheduled_for,
                interval_seconds = excluded.interval_seconds,
                delay_seconds = excluded.delay_seconds,
                status = excluded.status,
                trigger_count = excluded.trigger_count,
                next_run_at = excluded.next_run_at,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                last_triggered_at = excluded.last_triggered_at,
                last_error = excluded.last_error
            """,
            (
                record.alert_id,
                record.token,
                record.chain,
                record.alert_type.value,
                record.severity.value,
                record.score,
                record.window_start.isoformat(),
                record.window_end.isoformat(),
                record.dedup_key,
                json.dumps(record.payload_json, sort_keys=True),
                record.priority.value,
                record.priority_assigned_at.isoformat() if record.priority_assigned_at is not None else None,
                record.priority_reason,
                record.schedule_kind.value,
                record.scheduled_for.isoformat(),
                record.interval_seconds,
                record.delay_seconds,
                record.status.value,
                record.trigger_count,
                record.next_run_at.isoformat() if record.next_run_at is not None else None,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                record.last_triggered_at.isoformat() if record.last_triggered_at is not None else None,
                record.last_error,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_schedule(row: tuple[Any, ...]) -> AlertScheduleRecord:
    return AlertScheduleRecord(
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
        priority=normalize_alert_priority(row[10]),
        priority_assigned_at=datetime.fromisoformat(row[11]) if row[11] is not None else None,
        priority_reason=row[12],
        schedule_kind=AlertScheduleKind(row[13]),
        scheduled_for=datetime.fromisoformat(row[14]),
        interval_seconds=float(row[15]) if row[15] is not None else None,
        delay_seconds=float(row[16]) if row[16] is not None else None,
        status=AlertScheduleStatus(row[17]),
        trigger_count=int(row[18]),
        next_run_at=datetime.fromisoformat(row[19]) if row[19] is not None else None,
        created_at=datetime.fromisoformat(row[20]),
        updated_at=datetime.fromisoformat(row[21]),
        last_triggered_at=datetime.fromisoformat(row[22]) if row[22] is not None else None,
        last_error=row[23],
    )


def _append_schedule_log(log_path: str | Path | None, entry: AlertScheduleLogEntry) -> None:
    if log_path is None:
        return
    path = _normalize_optional_path(log_path)
    if path is None:
        raise TypeError("log_path must be a non-empty string, Path, or None")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_serialize_log_entry(entry), sort_keys=True))
        handle.write("\n")


def _serialize_log_entry(entry: AlertScheduleLogEntry) -> dict[str, Any]:
    return {
        "alert_id": entry.alert_id,
        "delivery_status": entry.delivery_status,
        "error": entry.error,
        "event": entry.event.value,
        "next_run_at": entry.next_run_at.isoformat() if entry.next_run_at is not None else None,
        "schedule_kind": entry.schedule_kind.value,
        "scheduled_for": entry.scheduled_for.isoformat(),
        "status": entry.status.value,
        "triggered_at": entry.triggered_at.isoformat() if entry.triggered_at is not None else None,
    }


def _normalize_optional_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    return None


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


__all__ = [
    "AlertScheduleEvent",
    "AlertScheduleKind",
    "AlertScheduleLogEntry",
    "AlertScheduleProcessingResult",
    "AlertScheduleStatus",
    "AlertScheduleRecord",
    "initialize_alert_schedule_store",
    "process_due_alert_schedules",
    "read_alert_schedule_log",
    "read_alert_schedules",
    "read_due_alert_schedules",
    "schedule_alert_notification",
]
