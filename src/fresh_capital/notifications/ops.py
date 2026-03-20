"""Operator-facing notification operations CLI for the Fresh Capital MVP."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fresh_capital.domain.enums import StrEnum
from fresh_capital.notifications.persistence import (
    NotificationDispatchResult,
    NotificationStateRecord,
    NotificationStatus,
    dispatch_due_notifications,
    read_due_notification_states,
    read_notification_states,
)
from fresh_capital.notifications.scheduling import (
    AlertScheduleProcessingResult,
    AlertScheduleRecord,
    AlertScheduleStatus,
    process_due_alert_schedules,
    read_alert_schedules,
    read_due_alert_schedules,
)
from fresh_capital.notifications.verification import check_alert_notification_status
from fresh_capital.notifications.webhook import (
    AlertNotificationConfig,
    send_single_alert_notification,
)


class NotificationOpsCollection(StrEnum):
    NOTIFICATIONS = "notifications"
    SCHEDULES = "schedules"


class NotificationOpsState(StrEnum):
    ALL = "all"
    DUE = "due"
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELED = "canceled"
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"


NotificationSender = Callable[[Any, AlertNotificationConfig], None]


@dataclass(frozen=True, slots=True)
class NotificationOpsSummary:
    total_alerts: int
    pending_count: int
    sent_count: int
    failed_count: int
    canceled_count: int
    due_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "canceled_count": self.canceled_count,
            "due_count": self.due_count,
            "failed_count": self.failed_count,
            "pending_count": self.pending_count,
            "sent_count": self.sent_count,
            "total_alerts": self.total_alerts,
        }


@dataclass(frozen=True, slots=True)
class ScheduleOpsSummary:
    total_alerts: int
    scheduled_count: int
    triggered_count: int
    rescheduled_count: int
    completed_count: int
    due_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_count": self.completed_count,
            "due_count": self.due_count,
            "rescheduled_count": self.rescheduled_count,
            "scheduled_count": self.scheduled_count,
            "total_alerts": self.total_alerts,
            "triggered_count": self.triggered_count,
        }


@dataclass(frozen=True, slots=True)
class NotificationOpsReport:
    generated_at: datetime
    db_path: Path
    notification_summary: NotificationOpsSummary
    schedule_summary: ScheduleOpsSummary
    notification_states: tuple[NotificationStateRecord, ...]
    schedule_states: tuple[AlertScheduleRecord, ...]
    due_notification_states: tuple[NotificationStateRecord, ...]
    due_schedule_states: tuple[AlertScheduleRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": str(self.db_path),
            "due_notification_states": [
                _serialize_notification_state(state) for state in self.due_notification_states
            ],
            "due_schedule_states": [_serialize_schedule_state(state) for state in self.due_schedule_states],
            "generated_at": self.generated_at.isoformat(),
            "notification_states": [_serialize_notification_state(state) for state in self.notification_states],
            "notification_summary": self.notification_summary.to_dict(),
            "schedule_states": [_serialize_schedule_state(state) for state in self.schedule_states],
            "schedule_summary": self.schedule_summary.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class NotificationOpsProcessReport:
    processed_at: datetime
    schedule_results: tuple[AlertScheduleProcessingResult, ...]
    notification_results: tuple[NotificationDispatchResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "notification_results": [
                _serialize_notification_dispatch_result(result) for result in self.notification_results
            ],
            "processed_at": self.processed_at.isoformat(),
            "schedule_results": [_serialize_schedule_result(result) for result in self.schedule_results],
        }


def build_notification_ops_report(
    db_path: str | Path,
    *,
    as_of: datetime | None = None,
) -> NotificationOpsReport:
    generated_at = as_of or datetime.now(timezone.utc)
    notification_states = read_notification_states(db_path)
    schedule_states = read_alert_schedules(db_path)
    due_notification_states = read_due_notification_states(db_path, as_of=generated_at)
    due_schedule_states = read_due_alert_schedules(db_path, as_of=generated_at)
    notification_status_check = check_alert_notification_status(db_path, checked_at=generated_at)
    notification_summary = NotificationOpsSummary(
        total_alerts=notification_status_check.total_alerts,
        pending_count=notification_status_check.pending_count,
        sent_count=notification_status_check.sent_count,
        failed_count=notification_status_check.failed_count,
        canceled_count=notification_status_check.canceled_count,
        due_count=len(due_notification_states),
    )
    schedule_summary = ScheduleOpsSummary(
        total_alerts=len(schedule_states),
        scheduled_count=_count_schedule_states(schedule_states, AlertScheduleStatus.SCHEDULED),
        triggered_count=_count_schedule_states(schedule_states, AlertScheduleStatus.TRIGGERED),
        rescheduled_count=_count_schedule_states(schedule_states, AlertScheduleStatus.RESCHEDULED),
        completed_count=_count_schedule_states(schedule_states, AlertScheduleStatus.COMPLETED),
        due_count=len(due_schedule_states),
    )
    return NotificationOpsReport(
        generated_at=generated_at,
        db_path=_normalize_path(db_path),
        notification_summary=notification_summary,
        schedule_summary=schedule_summary,
        notification_states=notification_states,
        schedule_states=schedule_states,
        due_notification_states=due_notification_states,
        due_schedule_states=due_schedule_states,
    )


def list_notification_ops_entries(
    db_path: str | Path,
    *,
    collection: NotificationOpsCollection | str,
    state: NotificationOpsState | str,
    as_of: datetime | None = None,
) -> tuple[dict[str, Any], ...]:
    normalized_collection = _normalize_collection(collection)
    normalized_state = _normalize_state(state)
    generated_at = as_of or datetime.now(timezone.utc)
    _validate_collection_state(normalized_collection, normalized_state)

    if normalized_collection == NotificationOpsCollection.NOTIFICATIONS:
        if normalized_state == NotificationOpsState.DUE:
            records = read_due_notification_states(db_path, as_of=generated_at)
        else:
            records = _filter_notification_states(read_notification_states(db_path), normalized_state)
        return tuple(_serialize_notification_state(record) for record in records)

    if normalized_state == NotificationOpsState.DUE:
        records = read_due_alert_schedules(db_path, as_of=generated_at)
    else:
        records = _filter_schedule_states(read_alert_schedules(db_path), normalized_state)
    return tuple(_serialize_schedule_state(record) for record in records)


def process_due_notification_operations(
    db_path: str | Path,
    config: AlertNotificationConfig,
    *,
    sender: NotificationSender = send_single_alert_notification,
    as_of: datetime | None = None,
) -> NotificationOpsProcessReport:
    if not isinstance(config, AlertNotificationConfig):
        raise TypeError("config must be an AlertNotificationConfig")
    if not callable(sender):
        raise TypeError("sender must be callable")

    processed_at = as_of or datetime.now(timezone.utc)
    schedule_results = process_due_alert_schedules(
        db_path,
        config,
        sender=sender,
        as_of=processed_at,
    )
    notification_results = dispatch_due_notifications(
        db_path,
        config,
        sender=sender,
        as_of=processed_at,
    )
    return NotificationOpsProcessReport(
        processed_at=processed_at,
        schedule_results=schedule_results,
        notification_results=notification_results,
    )


def write_notification_ops_report(
    report: NotificationOpsReport,
    report_path: str | Path,
) -> Path:
    if not isinstance(report, NotificationOpsReport):
        raise TypeError("report must be a NotificationOpsReport")
    path = _normalize_path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(
    argv: list[str] | None = None,
    *,
    sender: NotificationSender = send_single_alert_notification,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "summary":
        report = build_notification_ops_report(args.db_path, as_of=args.as_of)
        payload = {
            "db_path": report.db_path.as_posix(),
            "generated_at": report.generated_at.isoformat(),
            "notification_summary": report.notification_summary.to_dict(),
            "schedule_summary": report.schedule_summary.to_dict(),
        }
        _write_stdout_json(payload)
        return 0

    if args.command == "list":
        try:
            entries = list_notification_ops_entries(
                args.db_path,
                collection=args.collection,
                state=args.state,
                as_of=args.as_of,
            )
        except ValueError as exc:
            parser.error(str(exc))
        payload = {
            "collection": _normalize_collection(args.collection).value,
            "db_path": _normalize_path(args.db_path).as_posix(),
            "entries": list(entries),
            "generated_at": (args.as_of or datetime.now(timezone.utc)).isoformat(),
            "state": _normalize_state(args.state).value,
        }
        _write_stdout_json(payload)
        return 0

    if args.command == "process":
        config = AlertNotificationConfig(
            webhook_url=args.webhook_url,
            max_attempts=args.max_attempts,
            retry_delay_seconds=args.retry_delay_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        result = process_due_notification_operations(
            args.db_path,
            config,
            sender=sender,
            as_of=args.as_of,
        )
        payload = {
            "db_path": _normalize_path(args.db_path).as_posix(),
            "processed_at": result.processed_at.isoformat(),
            "notification_results": [
                _serialize_notification_dispatch_result(item) for item in result.notification_results
            ],
            "schedule_results": [_serialize_schedule_result(item) for item in result.schedule_results],
        }
        _write_stdout_json(payload)
        return 0

    if args.command == "report":
        report = build_notification_ops_report(args.db_path, as_of=args.as_of)
        write_notification_ops_report(report, args.report_path)
        _write_stdout_json(
            {
                "db_path": report.db_path.as_posix(),
                "generated_at": report.generated_at.isoformat(),
                "report_path": _normalize_path(args.report_path).as_posix(),
            }
        )
        return 0

    parser.error("a command is required")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fresh-capital-notification-ops")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser("summary", help="Show notification and schedule summary counts")
    _add_db_path_argument(summary_parser)
    _add_as_of_argument(summary_parser)

    list_parser = subparsers.add_parser("list", help="List notification or schedule records")
    _add_db_path_argument(list_parser)
    _add_as_of_argument(list_parser)
    list_parser.add_argument(
        "--collection",
        choices=[item.value for item in NotificationOpsCollection],
        required=True,
    )
    list_parser.add_argument(
        "--state",
        choices=[item.value for item in NotificationOpsState],
        required=True,
    )

    process_parser = subparsers.add_parser("process", help="Manually process due schedules and notifications")
    _add_db_path_argument(process_parser)
    _add_as_of_argument(process_parser)
    process_parser.add_argument("--webhook-url", required=True)
    process_parser.add_argument("--max-attempts", type=int, default=3)
    process_parser.add_argument("--retry-delay-seconds", type=float, default=300.0)
    process_parser.add_argument("--timeout-seconds", type=float, default=5.0)

    report_parser = subparsers.add_parser("report", help="Write a JSON report of current notification state")
    _add_db_path_argument(report_parser)
    _add_as_of_argument(report_parser)
    report_parser.add_argument("--report-path", required=True)
    return parser


def _add_db_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-path", required=True)


def _add_as_of_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--as-of", type=_parse_datetime, default=None)


def _normalize_collection(collection: NotificationOpsCollection | str) -> NotificationOpsCollection:
    if isinstance(collection, NotificationOpsCollection):
        return collection
    if isinstance(collection, str):
        try:
            return NotificationOpsCollection(collection)
        except ValueError as exc:  # pragma: no cover - guarded by argparse
            raise ValueError("collection must be notifications or schedules") from exc
    raise TypeError("collection must be a NotificationOpsCollection or string")


def _normalize_state(state: NotificationOpsState | str) -> NotificationOpsState:
    if isinstance(state, NotificationOpsState):
        return state
    if isinstance(state, str):
        try:
            return NotificationOpsState(state)
        except ValueError as exc:  # pragma: no cover - guarded by argparse
            raise ValueError("state must be a valid notification ops state") from exc
    raise TypeError("state must be a NotificationOpsState or string")


def _filter_notification_states(
    states: tuple[NotificationStateRecord, ...],
    state: NotificationOpsState,
) -> tuple[NotificationStateRecord, ...]:
    if state == NotificationOpsState.ALL:
        return states
    if state == NotificationOpsState.PENDING:
        return tuple(item for item in states if item.status == NotificationStatus.PENDING)
    if state == NotificationOpsState.SENT:
        return tuple(item for item in states if item.status == NotificationStatus.SENT)
    if state == NotificationOpsState.FAILED:
        return tuple(item for item in states if item.status == NotificationStatus.FAILED)
    if state == NotificationOpsState.CANCELED:
        return tuple(item for item in states if item.status == NotificationStatus.CANCELED)
    raise ValueError("notification state must be all, due, pending, sent, failed, or canceled")


def _filter_schedule_states(
    states: tuple[AlertScheduleRecord, ...],
    state: NotificationOpsState,
) -> tuple[AlertScheduleRecord, ...]:
    if state == NotificationOpsState.ALL:
        return states
    if state == NotificationOpsState.SCHEDULED:
        return tuple(item for item in states if item.status == AlertScheduleStatus.SCHEDULED)
    if state == NotificationOpsState.TRIGGERED:
        return tuple(item for item in states if item.status == AlertScheduleStatus.TRIGGERED)
    if state == NotificationOpsState.RESCHEDULED:
        return tuple(item for item in states if item.status == AlertScheduleStatus.RESCHEDULED)
    if state == NotificationOpsState.COMPLETED:
        return tuple(item for item in states if item.status == AlertScheduleStatus.COMPLETED)
    raise ValueError("schedule state must be all, due, scheduled, triggered, rescheduled, or completed")


def _count_schedule_states(states: tuple[AlertScheduleRecord, ...], status: AlertScheduleStatus) -> int:
    return sum(1 for item in states if item.status == status)


def _validate_collection_state(collection: NotificationOpsCollection, state: NotificationOpsState) -> None:
    if collection == NotificationOpsCollection.NOTIFICATIONS and state in {
        NotificationOpsState.SCHEDULED,
        NotificationOpsState.TRIGGERED,
        NotificationOpsState.RESCHEDULED,
        NotificationOpsState.COMPLETED,
    }:
        raise ValueError("notification collection does not support schedule states")
    if collection == NotificationOpsCollection.SCHEDULES and state in {
        NotificationOpsState.PENDING,
        NotificationOpsState.SENT,
        NotificationOpsState.FAILED,
        NotificationOpsState.CANCELED,
    }:
        raise ValueError("schedule collection does not support notification states")


def _serialize_notification_state(state: NotificationStateRecord) -> dict[str, Any]:
    return {
        "alert_id": state.alert_id,
        "attempt_count": state.attempt_count,
        "canceled_at": state.canceled_at.isoformat() if state.canceled_at is not None else None,
        "chain": state.chain,
        "expiration_at": state.expiration_at.isoformat() if state.expiration_at is not None else None,
        "max_attempts": state.max_attempts,
        "next_retry_at": state.next_retry_at.isoformat() if state.next_retry_at is not None else None,
        "priority": state.priority.value,
        "sent_at": state.sent_at.isoformat() if state.sent_at is not None else None,
        "status": state.status.value,
        "token": state.token,
        "updated_at": state.updated_at.isoformat(),
    }


def _serialize_schedule_state(state: AlertScheduleRecord) -> dict[str, Any]:
    return {
        "alert_id": state.alert_id,
        "chain": state.chain,
        "next_run_at": state.next_run_at.isoformat() if state.next_run_at is not None else None,
        "priority": state.priority.value,
        "scheduled_for": state.scheduled_for.isoformat(),
        "status": state.status.value,
        "token": state.token,
        "trigger_count": state.trigger_count,
        "updated_at": state.updated_at.isoformat(),
    }


def _serialize_notification_dispatch_result(result: NotificationDispatchResult) -> dict[str, Any]:
    return {
        "alert_id": result.alert_id,
        "attempt_number": result.attempt_number,
        "error": result.error,
        "is_delivered": result.is_delivered,
        "status": result.status.value,
    }


def _serialize_schedule_result(result: AlertScheduleProcessingResult) -> dict[str, Any]:
    return {
        "alert_id": result.alert_id,
        "next_run_at": result.next_run_at.isoformat() if result.next_run_at is not None else None,
        "notification_results": [
            _serialize_notification_dispatch_result(item) for item in result.notification_results
        ],
        "status": result.status.value,
        "was_rescheduled": result.was_rescheduled,
    }


def _write_stdout_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")


def _normalize_path(path_value: str | Path) -> Path:
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    raise TypeError("path must be a non-empty string or Path")


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse validates syntax, but keep explicit failure
        raise argparse.ArgumentTypeError("as-of must be an ISO 8601 datetime") from exc


if __name__ == "__main__":
    raise SystemExit(main())
