"""Alert prioritization for notification scheduling and retry order."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fresh_capital.domain.enums import AlertType, Severity, StrEnum
from fresh_capital.domain.models import AlertRecord


class AlertPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertPriorityEvent(StrEnum):
    CLASSIFIED = "classified"
    CHANGED = "changed"
    PROCESSED = "processed"


@dataclass(frozen=True, slots=True)
class AlertPriorityLogEntry:
    alert_id: str
    event: AlertPriorityEvent
    priority: AlertPriority
    previous_priority: AlertPriority | None
    changed_at: datetime
    processing_order: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class AlertPriorityChangeResult:
    alert_id: str
    priority: AlertPriority
    previous_priority: AlertPriority | None
    changed_at: datetime
    reason: str | None


def classify_alert_priority(alert_record: AlertRecord) -> AlertPriority:
    if not isinstance(alert_record, AlertRecord):
        raise TypeError("alert_record must be an AlertRecord")

    if alert_record.alert_type in (
        AlertType.DISTRIBUTION_STARTED,
        AlertType.SHORT_WATCH,
    ):
        return AlertPriority.HIGH
    if alert_record.alert_type in (
        AlertType.ACCUMULATION_CONFIRMED,
        AlertType.INVALIDATION,
    ):
        return AlertPriority.MEDIUM
    if alert_record.severity in (Severity.CRITICAL,):
        return AlertPriority.HIGH
    if alert_record.severity in (Severity.HIGH,):
        return AlertPriority.MEDIUM
    return AlertPriority.LOW


def normalize_alert_priority(priority: AlertPriority | str) -> AlertPriority:
    if isinstance(priority, AlertPriority):
        return priority
    if isinstance(priority, str):
        return AlertPriority(priority)
    raise TypeError("priority must be an AlertPriority or string")


def read_alert_priority_log(log_path: str | Path) -> tuple[AlertPriorityLogEntry, ...]:
    path = _normalize_optional_path(log_path)
    if path is None or not path.exists():
        return ()

    entries: list[AlertPriorityLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        raw = json.loads(line)
        entries.append(
            AlertPriorityLogEntry(
                alert_id=raw["alert_id"],
                event=AlertPriorityEvent(raw["event"]),
                priority=AlertPriority(raw["priority"]),
                previous_priority=AlertPriority(raw["previous_priority"]) if raw["previous_priority"] is not None else None,
                changed_at=datetime.fromisoformat(raw["changed_at"]),
                processing_order=int(raw["processing_order"]) if raw["processing_order"] is not None else None,
                reason=raw["reason"],
            )
        )
    return tuple(entries)


def _append_priority_log(log_path: str | Path | None, entry: AlertPriorityLogEntry) -> None:
    if log_path is None:
        return
    path = _normalize_optional_path(log_path)
    if path is None:
        raise TypeError("log_path must be a non-empty string, Path, or None")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_serialize_log_entry(entry), sort_keys=True))
        handle.write("\n")


def log_alert_priority_assignment(
    *,
    alert_id: str,
    priority: AlertPriority | str,
    assigned_at: datetime | None = None,
    reason: str | None = None,
    log_path: str | Path | None = None,
) -> AlertPriorityLogEntry:
    normalized_priority = normalize_alert_priority(priority)
    now = assigned_at or datetime.now(timezone.utc)
    entry = AlertPriorityLogEntry(
        alert_id=alert_id,
        event=AlertPriorityEvent.CLASSIFIED,
        priority=normalized_priority,
        previous_priority=None,
        changed_at=now,
        processing_order=None,
        reason=reason,
    )
    _append_priority_log(log_path, entry)
    return entry


def log_alert_priority_change(
    *,
    alert_id: str,
    priority: AlertPriority | str,
    previous_priority: AlertPriority | str | None = None,
    changed_at: datetime | None = None,
    reason: str | None = None,
    log_path: str | Path | None = None,
) -> AlertPriorityLogEntry:
    normalized_priority = normalize_alert_priority(priority)
    normalized_previous = normalize_alert_priority(previous_priority) if previous_priority is not None else None
    now = changed_at or datetime.now(timezone.utc)
    entry = AlertPriorityLogEntry(
        alert_id=alert_id,
        event=AlertPriorityEvent.CHANGED,
        priority=normalized_priority,
        previous_priority=normalized_previous,
        changed_at=now,
        processing_order=None,
        reason=reason,
    )
    _append_priority_log(log_path, entry)
    return entry


def log_alert_processing_order(
    *,
    alert_id: str,
    priority: AlertPriority | str,
    processing_order: int,
    processed_at: datetime | None = None,
    reason: str | None = None,
    log_path: str | Path | None = None,
) -> AlertPriorityLogEntry:
    normalized_priority = normalize_alert_priority(priority)
    now = processed_at or datetime.now(timezone.utc)
    entry = AlertPriorityLogEntry(
        alert_id=alert_id,
        event=AlertPriorityEvent.PROCESSED,
        priority=normalized_priority,
        previous_priority=None,
        changed_at=now,
        processing_order=processing_order,
        reason=reason,
    )
    _append_priority_log(log_path, entry)
    return entry


def _serialize_log_entry(entry: AlertPriorityLogEntry) -> dict[str, Any]:
    return {
        "alert_id": entry.alert_id,
        "changed_at": entry.changed_at.isoformat(),
        "event": entry.event.value,
        "priority": entry.priority.value,
        "previous_priority": entry.previous_priority.value if entry.previous_priority is not None else None,
        "processing_order": entry.processing_order,
        "reason": entry.reason,
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
    "AlertPriority",
    "AlertPriorityChangeResult",
    "AlertPriorityEvent",
    "AlertPriorityLogEntry",
    "classify_alert_priority",
    "log_alert_priority_assignment",
    "log_alert_priority_change",
    "log_alert_processing_order",
    "normalize_alert_priority",
    "read_alert_priority_log",
]
