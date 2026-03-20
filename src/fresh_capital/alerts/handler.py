"""Local structured alert handling and audit logging."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fresh_capital.alerts.builder import AlertBuildResult
from fresh_capital.domain.enums import AlertType, Severity, StrEnum
from fresh_capital.domain.models import AlertRecord


class AlertStatus(StrEnum):
    CREATED = "created"
    PROCESSED = "processed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class AlertLogEntry:
    status: AlertStatus
    alert_id: str | None
    token: str | None
    chain: str | None
    alert_type: AlertType | None
    severity: Severity | None
    timestamp: datetime | None
    logged_at: datetime | None
    triggered_rules: tuple[str, ...]
    reject_reasons: tuple[str, ...]
    payload_json: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AlertHandlingResult:
    is_stored: bool
    reject_reasons: tuple[str, ...]
    log_entry: AlertLogEntry | None


def handle_alert_build_result(
    build_result: AlertBuildResult,
    storage_path: str | Path,
) -> AlertHandlingResult:
    """Persist a built alert or a rejection record into a local JSONL audit log."""
    if not isinstance(build_result, AlertBuildResult):
        raise TypeError("build_result must be an AlertBuildResult")

    path = _normalize_storage_path(storage_path)
    if build_result.is_alert_built:
        if build_result.alert_record is None:
            return AlertHandlingResult(
                is_stored=False,
                reject_reasons=("missing_alert_record",),
                log_entry=None,
            )
        entry = _entry_from_alert_record(
            alert_record=build_result.alert_record,
            status=AlertStatus.CREATED,
            logged_at=build_result.alert_record.created_at,
        )
    else:
        entry = AlertLogEntry(
            status=AlertStatus.REJECTED,
            alert_id=None,
            token=None,
            chain=None,
            alert_type=None,
            severity=None,
            timestamp=None,
            logged_at=None,
            triggered_rules=(),
            reject_reasons=tuple(build_result.reject_reasons),
            payload_json={},
        )

    _append_log_entry(path, entry)
    return AlertHandlingResult(
        is_stored=True,
        reject_reasons=(),
        log_entry=entry,
    )


def update_alert_status(
    alert_record: AlertRecord,
    status: AlertStatus | str,
    storage_path: str | Path,
    *,
    logged_at: datetime | None = None,
) -> AlertHandlingResult:
    """Append a new status event for an existing alert record."""
    if not isinstance(alert_record, AlertRecord):
        raise TypeError("alert_record must be an AlertRecord")

    normalized_status = _normalize_status(status)
    if normalized_status == AlertStatus.CREATED:
        return AlertHandlingResult(
            is_stored=False,
            reject_reasons=("status_transition_requires_non_created_status",),
            log_entry=None,
        )

    path = _normalize_storage_path(storage_path)
    entry = _entry_from_alert_record(
        alert_record=alert_record,
        status=normalized_status,
        logged_at=logged_at or alert_record.updated_at,
    )
    _append_log_entry(path, entry)
    return AlertHandlingResult(
        is_stored=True,
        reject_reasons=(),
        log_entry=entry,
    )


def read_alert_log(storage_path: str | Path) -> tuple[AlertLogEntry, ...]:
    """Load structured alert log entries from a local JSONL file."""
    path = _normalize_storage_path(storage_path)
    if not path.exists():
        return ()

    entries: list[AlertLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        raw = json.loads(line)
        entries.append(
            AlertLogEntry(
                status=AlertStatus(raw["status"]),
                alert_id=raw["alert_id"],
                token=raw["token"],
                chain=raw["chain"],
                alert_type=AlertType(raw["alert_type"]) if raw["alert_type"] is not None else None,
                severity=Severity(raw["severity"]) if raw["severity"] is not None else None,
                timestamp=_parse_datetime(raw["timestamp"]),
                logged_at=_parse_datetime(raw["logged_at"]),
                triggered_rules=tuple(raw["triggered_rules"]),
                reject_reasons=tuple(raw["reject_reasons"]),
                payload_json=dict(raw["payload_json"]),
            )
        )
    return tuple(entries)


def _entry_from_alert_record(
    *,
    alert_record: AlertRecord,
    status: AlertStatus,
    logged_at: datetime | None,
) -> AlertLogEntry:
    triggered_rules = tuple(_extract_triggered_rules(alert_record.payload_json))
    return AlertLogEntry(
        status=status,
        alert_id=alert_record.alert_id,
        token=alert_record.token,
        chain=alert_record.chain,
        alert_type=alert_record.alert_type,
        severity=alert_record.severity,
        timestamp=alert_record.window_end,
        logged_at=logged_at,
        triggered_rules=triggered_rules,
        reject_reasons=(),
        payload_json=dict(alert_record.payload_json),
    )


def _extract_triggered_rules(payload_json: dict[str, Any]) -> tuple[str, ...]:
    raw_rules = payload_json.get("triggered_rules", ())
    if not isinstance(raw_rules, list):
        return ()
    result: list[str] = []
    for rule in raw_rules:
        if isinstance(rule, str):
            result.append(rule)
    return tuple(result)


def _append_log_entry(path: Path, entry: AlertLogEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_serialize_log_entry(entry), sort_keys=True))
        handle.write("\n")


def _serialize_log_entry(entry: AlertLogEntry) -> dict[str, Any]:
    return {
        "alert_id": entry.alert_id,
        "alert_type": entry.alert_type.value if entry.alert_type is not None else None,
        "chain": entry.chain,
        "logged_at": entry.logged_at.isoformat() if entry.logged_at is not None else None,
        "payload_json": dict(entry.payload_json),
        "reject_reasons": list(entry.reject_reasons),
        "severity": entry.severity.value if entry.severity is not None else None,
        "status": entry.status.value,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp is not None else None,
        "token": entry.token,
        "triggered_rules": list(entry.triggered_rules),
    }


def _normalize_storage_path(storage_path: str | Path) -> Path:
    if isinstance(storage_path, Path):
        return storage_path
    if isinstance(storage_path, str) and storage_path:
        return Path(storage_path)
    raise TypeError("storage_path must be a non-empty string or Path")


def _normalize_status(status: AlertStatus | str) -> AlertStatus:
    if isinstance(status, AlertStatus):
        return status
    if isinstance(status, str):
        try:
            return AlertStatus(status)
        except ValueError as exc:
            raise ValueError("status must be a valid AlertStatus") from exc
    raise TypeError("status must be an AlertStatus or string value")


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
