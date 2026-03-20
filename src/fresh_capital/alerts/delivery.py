"""Local mock delivery for alert log entries."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fresh_capital.alerts.handler import AlertLogEntry, AlertStatus, read_alert_log
from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord


@dataclass(frozen=True, slots=True)
class AlertDeliveryResult:
    is_delivered: bool
    reject_reasons: tuple[str, ...]
    status: AlertStatus
    alert_id: str | None


def deliver_logged_alerts(
    log_path: str | Path,
    database_path: str | Path,
    status_log_path: str | Path,
    *,
    fail_alert_ids: tuple[str, ...] = (),
) -> tuple[AlertDeliveryResult, ...]:
    """Deliver created alert log entries into a local SQLite sink and append delivery statuses."""
    entries = read_alert_log(log_path)
    conn = _open_database(database_path)
    try:
        _ensure_alerts_table(conn)
        results: list[AlertDeliveryResult] = []
        for entry in entries:
            if entry.status != AlertStatus.CREATED:
                continue

            result = _deliver_entry(
                entry=entry,
                conn=conn,
                status_log_path=status_log_path,
                fail_alert_ids=fail_alert_ids,
            )
            results.append(result)
        return tuple(results)
    finally:
        conn.close()


def read_delivered_alerts(database_path: str | Path) -> tuple[dict[str, object], ...]:
    """Read delivered alerts from the local SQLite sink."""
    path = _normalize_path(database_path)
    if not path.exists():
        return ()

    conn = sqlite3.connect(path)
    try:
        _ensure_alerts_table(conn)
        rows = conn.execute(
            """
            SELECT alert_id, alert_type, chain, severity, status, timestamp, payload_json
            FROM delivered_alerts
            ORDER BY rowid
            """
        ).fetchall()
    finally:
        conn.close()

    return tuple(
        {
            "alert_id": row[0],
            "alert_type": row[1],
            "chain": row[2],
            "severity": row[3],
            "status": row[4],
            "timestamp": row[5],
            "payload_json": json.loads(row[6]),
        }
        for row in rows
    )


def _deliver_entry(
    *,
    entry: AlertLogEntry,
    conn: sqlite3.Connection,
    status_log_path: str | Path,
    fail_alert_ids: tuple[str, ...],
) -> AlertDeliveryResult:
    if entry.alert_id is None:
        _append_status_log(
            status_log_path,
            _status_entry_from_log_entry(entry, AlertStatus.FAILED, logged_at=entry.logged_at),
        )
        return AlertDeliveryResult(
            is_delivered=False,
            reject_reasons=("missing_alert_id",),
            status=AlertStatus.FAILED,
            alert_id=None,
        )

    if entry.alert_id in fail_alert_ids:
        _append_status_log(
            status_log_path,
            _status_entry_from_log_entry(entry, AlertStatus.FAILED, logged_at=entry.logged_at),
        )
        return AlertDeliveryResult(
            is_delivered=False,
            reject_reasons=("mock_delivery_failed",),
            status=AlertStatus.FAILED,
            alert_id=entry.alert_id,
        )

    conn.execute(
        """
        INSERT INTO delivered_alerts (
            alert_id,
            alert_type,
            chain,
            severity,
            status,
            timestamp,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.alert_id,
            entry.alert_type.value if entry.alert_type is not None else None,
            entry.chain,
            entry.severity.value if entry.severity is not None else None,
            AlertStatus.DELIVERED.value,
            entry.timestamp.isoformat() if entry.timestamp is not None else None,
            json.dumps(entry.payload_json, sort_keys=True),
        ),
    )
    conn.commit()

    _append_status_log(
        status_log_path,
        _status_entry_from_log_entry(entry, AlertStatus.DELIVERED, logged_at=entry.logged_at),
    )
    return AlertDeliveryResult(
        is_delivered=True,
        reject_reasons=(),
        status=AlertStatus.DELIVERED,
        alert_id=entry.alert_id,
    )


def _open_database(database_path: str | Path) -> sqlite3.Connection:
    path = _normalize_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def _ensure_alerts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS delivered_alerts (
            alert_id TEXT PRIMARY KEY,
            alert_type TEXT,
            chain TEXT,
            severity TEXT,
            status TEXT,
            timestamp TEXT,
            payload_json TEXT
        )
        """
    )
    conn.commit()


def _status_entry_from_log_entry(
    entry: AlertLogEntry,
    status: AlertStatus,
    *,
    logged_at: datetime | None,
) -> AlertLogEntry:
    return AlertLogEntry(
        status=status,
        alert_id=entry.alert_id,
        token=entry.token,
        chain=entry.chain,
        alert_type=entry.alert_type if isinstance(entry.alert_type, AlertType) else None,
        severity=entry.severity if isinstance(entry.severity, Severity) else None,
        timestamp=entry.timestamp,
        logged_at=logged_at,
        triggered_rules=entry.triggered_rules,
        reject_reasons=(),
        payload_json=dict(entry.payload_json),
    )


def _append_status_log(status_log_path: str | Path, entry: AlertLogEntry) -> None:
    path = _normalize_path(status_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_serialize_entry(entry), sort_keys=True))
        handle.write("\n")


def _serialize_entry(entry: AlertLogEntry) -> dict[str, object]:
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


def _normalize_path(path_value: str | Path) -> Path:
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    raise TypeError("path must be a non-empty string or Path")
