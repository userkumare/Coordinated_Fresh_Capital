"""Fixture-driven demo runner for the Fresh Capital MVP pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fresh_capital.domain.models import AddressRecord, AlertRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.notifications.ops import NotificationOpsReport, build_notification_ops_report
from fresh_capital.notifications.scheduling import (
    AlertScheduleProcessingResult,
    process_due_alert_schedules,
    schedule_alert_notification,
)
from fresh_capital.domain.enums import ServiceType, SourceType
from fresh_capital.notifications.webhook import AlertNotificationConfig
from fresh_capital.notifications.verification import (
    build_alert_completion_status_report,
    write_alert_completion_status_report,
)
from fresh_capital.pipeline.orchestrator import (
    FreshCapitalPipelineRequest,
    FreshCapitalPipelineResult,
    PipelineParticipantInput,
    run_fresh_capital_pipeline,
)


DEFAULT_DEMO_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "step10_demo_positive.json"


@dataclass(frozen=True, slots=True)
class DemoFixtureSummary:
    chain: str
    token_address: str
    token_symbol: str
    participant_count: int
    fixture_path: Path


@dataclass(frozen=True, slots=True)
class DemoRunRequest:
    fixture_path: str | Path
    output_dir: str | Path


@dataclass(frozen=True, slots=True)
class DemoWrittenArtifacts:
    summary_json_path: Path
    summary_pretty_json_path: Path
    alert_log_path: Path
    delivery_database_path: Path
    delivery_status_log_path: Path


@dataclass(frozen=True, slots=True)
class DemoRunResult:
    fixture_summary: DemoFixtureSummary
    pipeline_result: FreshCapitalPipelineResult
    written_artifacts: DemoWrittenArtifacts


@dataclass(frozen=True, slots=True)
class DemoEndToEndResult:
    demo_result: DemoRunResult
    notification_database_path: Path
    notification_report_path: Path
    notification_report: NotificationOpsReport
    schedule_processing_results: tuple[AlertScheduleProcessingResult, ...]


def load_demo_fixture(fixture_path: str | Path) -> tuple[DemoFixtureSummary, FreshCapitalPipelineRequest]:
    """Load a local JSON fixture and convert it into a pipeline request."""
    path = _normalize_path(fixture_path, "fixture_path")
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        raise ValueError("fixture root must be a JSON object")

    chain = _require_string(payload, "chain")
    token = _require_mapping(payload, "token")
    token_address = _require_string(token, "address")
    token_symbol = _require_string(token, "symbol")
    market_snapshot_payload = _require_mapping(payload, "market_snapshot")
    participants_payload = _require_list(payload, "participants")
    if not participants_payload:
        raise ValueError("participants must not be empty")

    market_snapshot = _build_market_snapshot(
        market_snapshot_payload,
        chain=chain,
        token_address=token_address,
        token_symbol=token_symbol,
    )
    participants = tuple(
        _build_participant(participant_payload, chain=chain, token_address=token_address)
        for participant_payload in participants_payload
    )

    fixture_summary = DemoFixtureSummary(
        chain=chain,
        token_address=token_address,
        token_symbol=token_symbol,
        participant_count=len(participants),
        fixture_path=path,
    )
    request = FreshCapitalPipelineRequest(
        participants=participants,
        market_snapshot=market_snapshot,
    )
    return fixture_summary, request


def run_demo_fixture(request: DemoRunRequest) -> DemoRunResult:
    """Load a fixture, run the pipeline once, and write deterministic local artifacts."""
    if not isinstance(request, DemoRunRequest):
        raise TypeError("request must be a DemoRunRequest")

    fixture_summary, pipeline_request = load_demo_fixture(request.fixture_path)
    output_dir = _normalize_path(request.output_dir, "output_dir")
    output_dir.mkdir(parents=True, exist_ok=True)

    alert_log_path = output_dir / "alerts.jsonl"
    delivery_database_path = output_dir / "deliveries.sqlite"
    delivery_status_log_path = output_dir / "delivery_status.jsonl"
    summary_json_path = output_dir / "pipeline_result.json"
    summary_pretty_json_path = output_dir / "pipeline_result.pretty.json"

    pipeline_result = run_fresh_capital_pipeline(
        FreshCapitalPipelineRequest(
            participants=pipeline_request.participants,
            market_snapshot=pipeline_request.market_snapshot,
            alert_log_path=alert_log_path,
            delivery_database_path=delivery_database_path,
            delivery_status_log_path=delivery_status_log_path,
        )
    )

    written_artifacts = DemoWrittenArtifacts(
        summary_json_path=summary_json_path,
        summary_pretty_json_path=summary_pretty_json_path,
        alert_log_path=alert_log_path,
        delivery_database_path=delivery_database_path,
        delivery_status_log_path=delivery_status_log_path,
    )
    summary_payload = _build_summary_payload(fixture_summary, pipeline_result, written_artifacts)
    _write_json(summary_json_path, summary_payload, indent=None)
    _write_json(summary_pretty_json_path, summary_payload, indent=2)
    return DemoRunResult(
        fixture_summary=fixture_summary,
        pipeline_result=pipeline_result,
        written_artifacts=written_artifacts,
    )


def run_demo_end_to_end(
    request: DemoRunRequest,
    *,
    sender: Callable[[AlertRecord, AlertNotificationConfig], None] | None = None,
    as_of: datetime | None = None,
    process_notifications: bool = True,
) -> DemoEndToEndResult:
    """Run the fixture demo and optionally process the resulting notification state."""
    if not isinstance(request, DemoRunRequest):
        raise TypeError("request must be a DemoRunRequest")

    demo_result = run_demo_fixture(request)
    output_dir = _normalize_path(request.output_dir, "output_dir")
    notification_database_path = output_dir / "notification_state.sqlite"
    notification_report_path = output_dir / "notification_report.json"
    notification_status_report_path = output_dir / "notification_status_report.json"
    processed_at = as_of or _infer_processed_at(demo_result)
    schedule_processing_results: tuple[AlertScheduleProcessingResult, ...] = ()

    if process_notifications and demo_result.pipeline_result.alert_build_result is not None:
        alert_record = demo_result.pipeline_result.alert_build_result.alert_record
        if alert_record is not None:
            _ensure_notification_schedule(
                alert_record,
                notification_database_path,
                scheduled_for=processed_at,
            )
            schedule_processing_results = process_due_alert_schedules(
                notification_database_path,
                AlertNotificationConfig(webhook_url="http://example.invalid"),
                sender=sender or _noop_notification_sender,
                as_of=processed_at,
            )

    notification_report = build_notification_ops_report(notification_database_path, as_of=processed_at)
    _write_json(notification_report_path, notification_report.to_dict(), indent=None)
    status_report = build_alert_completion_status_report(notification_database_path, checked_at=processed_at)
    write_alert_completion_status_report(status_report, notification_status_report_path)
    return DemoEndToEndResult(
        demo_result=demo_result,
        notification_database_path=notification_database_path,
        notification_report_path=notification_report_path,
        notification_report=notification_report,
        schedule_processing_results=schedule_processing_results,
    )


def main(
    argv: list[str] | None = None,
    *,
    sender: Callable[[AlertRecord, AlertNotificationConfig], None] | None = None,
) -> int:
    """Run the deterministic demo from the shell."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    request = DemoRunRequest(
        fixture_path=args.fixture_path,
        output_dir=args.output_dir,
    )
    result = run_demo_end_to_end(
        request,
        sender=sender,
        as_of=args.as_of,
        process_notifications=not args.skip_notification_processing,
    )
    print(json.dumps(_build_shell_summary(result), sort_keys=True))
    return 0


def _build_market_snapshot(
    payload: dict[str, Any],
    *,
    chain: str,
    token_address: str,
    token_symbol: str,
) -> TokenMarketSnapshot:
    snapshot_payload = dict(payload)
    market_snapshot = TokenMarketSnapshot(
        snapshot_id=_require_string(snapshot_payload, "snapshot_id"),
        chain=_require_string(snapshot_payload, "chain"),
        token_address=_require_string(snapshot_payload, "token_address"),
        token_symbol=_require_string(snapshot_payload, "token_symbol"),
        captured_at=_parse_datetime(_require_string(snapshot_payload, "captured_at")),
        price_usd=_require_number(snapshot_payload, "price_usd"),
        liquidity_usd=_require_number(snapshot_payload, "liquidity_usd"),
        volume_24h_usd=_require_number(snapshot_payload, "volume_24h_usd"),
        holders_count=int(_require_number(snapshot_payload, "holders_count")),
        market_cap_usd=_optional_number(snapshot_payload, "market_cap_usd"),
        is_shortable=bool(snapshot_payload.get("is_shortable", False)),
        short_liquidity_usd=_optional_number(snapshot_payload, "short_liquidity_usd"),
    )
    if market_snapshot.chain != chain:
        raise ValueError("market snapshot chain must match fixture chain")
    if market_snapshot.token_address != token_address:
        raise ValueError("market snapshot token address must match fixture token address")
    if market_snapshot.token_symbol != token_symbol:
        raise ValueError("market snapshot token symbol must match fixture token symbol")
    return market_snapshot


def _build_participant(
    payload: dict[str, Any],
    *,
    chain: str,
    token_address: str,
) -> PipelineParticipantInput:
    participant_payload = dict(payload)
    address_payload = _require_mapping(participant_payload, "address")
    funding_event_payload = _require_mapping(participant_payload, "funding_event")
    address = AddressRecord(
        address=_require_string(address_payload, "address"),
        chain=_require_string(address_payload, "chain"),
        first_seen_at=_parse_datetime(_require_string(address_payload, "first_seen_at")),
        last_seen_at=_parse_datetime(_require_string(address_payload, "last_seen_at")),
        address_age_days=int(_require_number(address_payload, "address_age_days")),
        previous_tx_count=int(_require_number(address_payload, "previous_tx_count")),
        distinct_tokens_before_window=int(_require_number(address_payload, "distinct_tokens_before_window")),
        service_type=ServiceType(address_payload.get("service_type", ServiceType.NONE.value)),
        is_contract=bool(address_payload.get("is_contract", False)),
        labels=tuple(_require_list(address_payload, "labels")) if "labels" in address_payload else (),
    )
    funding_event = FundingEvent(
        event_id=_require_string(funding_event_payload, "event_id"),
        address=_require_string(funding_event_payload, "address"),
        chain=_require_string(funding_event_payload, "chain"),
        funded_at=_parse_datetime(_require_string(funding_event_payload, "funded_at")),
        source_address=_require_string(funding_event_payload, "source_address"),
        source_type=SourceType(funding_event_payload.get("source_type", SourceType.UNKNOWN.value)),
        asset_symbol=_require_string(funding_event_payload, "asset_symbol"),
        amount=_require_number(funding_event_payload, "amount"),
        amount_usd=_require_number(funding_event_payload, "amount_usd"),
        tx_hash=_require_string(funding_event_payload, "tx_hash"),
        asset_address=_optional_string(funding_event_payload, "asset_address"),
        block_number=_optional_int(funding_event_payload, "block_number"),
    )

    if address.chain != chain:
        raise ValueError("participant address chain must match fixture chain")
    if address.address != funding_event.address:
        raise ValueError("participant address must match funding event address")
    if funding_event.chain != chain:
        raise ValueError("participant funding event chain must match fixture chain")
    if not token_address:
        raise ValueError("token_address must not be empty")

    return PipelineParticipantInput(address=address, funding_event=funding_event)


def _build_summary_payload(
    fixture_summary: DemoFixtureSummary,
    pipeline_result: FreshCapitalPipelineResult,
    written_artifacts: DemoWrittenArtifacts,
) -> dict[str, Any]:
    return {
        "artifacts": {
            "alert_log_path": str(written_artifacts.alert_log_path),
            "delivery_database_path": str(written_artifacts.delivery_database_path),
            "delivery_status_log_path": str(written_artifacts.delivery_status_log_path),
            "summary_json_path": str(written_artifacts.summary_json_path),
            "summary_pretty_json_path": str(written_artifacts.summary_pretty_json_path),
        },
        "fixture": {
            "chain": fixture_summary.chain,
            "fixture_path": str(fixture_summary.fixture_path),
            "participant_count": fixture_summary.participant_count,
            "token_address": fixture_summary.token_address,
            "token_symbol": fixture_summary.token_symbol,
        },
        "pipeline": {
            "alert_built": pipeline_result.alert_build_result.is_alert_built if pipeline_result.alert_build_result else False,
            "alert_handled": pipeline_result.alert_handling_result.is_stored if pipeline_result.alert_handling_result else False,
            "delivery_count": len(pipeline_result.delivery_results or ()),
            "detection_positive": pipeline_result.detection_result.is_detected if pipeline_result.detection_result else False,
            "fresh_participant_count": len(pipeline_result.participant_classifications),
            "stage_statuses": [
                {
                    "name": trace.stage_name,
                    "reason": trace.reason,
                    "skipped": trace.stage_skipped,
                    "status": trace.stage_status.value,
                }
                for trace in pipeline_result.stage_traces
            ],
        },
    }


def _write_json(path: Path, payload: dict[str, Any], *, indent: int | None) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=indent) + "\n", encoding="utf-8")


def _read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_path(path_value: str | Path, name: str) -> Path:
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    raise TypeError(f"{name} must be a non-empty string or Path")


def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array")
    return value


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _optional_number(payload: dict[str, Any], key: str) -> float | None:
    if key not in payload or payload[key] is None:
        return None
    return _require_number(payload, key)


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload or payload[key] is None:
        return None
    return int(_require_number(payload, key))


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload or payload[key] is None:
        return None
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid datetime value: {value}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic Fresh Capital demo.")
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=DEFAULT_DEMO_FIXTURE_PATH,
        help="Path to a demo fixture JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where deterministic artifacts will be written.",
    )
    parser.add_argument(
        "--as-of",
        type=_parse_datetime,
        default=None,
        help="Optional ISO-8601 processing timestamp.",
    )
    parser.add_argument(
        "--skip-notification-processing",
        action="store_true",
        help="Load and run the demo without scheduling or processing notification state.",
    )
    return parser


def _build_shell_summary(result: DemoEndToEndResult) -> dict[str, Any]:
    pipeline_result = result.demo_result.pipeline_result
    notification_summary = result.notification_report.notification_summary
    schedule_summary = result.notification_report.schedule_summary
    return {
        "fixture_path": str(result.demo_result.fixture_summary.fixture_path),
        "notification_report_path": str(result.notification_report_path),
        "output_dir": str(result.demo_result.written_artifacts.summary_json_path.parent),
        "pipeline_result_path": str(result.demo_result.written_artifacts.summary_json_path),
        "pipeline_alert_built": bool(
            pipeline_result.alert_build_result is not None and pipeline_result.alert_build_result.is_alert_built
        ),
        "notification_failed_count": notification_summary.failed_count,
        "notification_processed": bool(result.schedule_processing_results or notification_summary.total_alerts > 0),
        "notification_sent_count": notification_summary.sent_count,
        "notification_total_alerts": notification_summary.total_alerts,
        "schedule_completed_count": schedule_summary.completed_count,
        "schedule_total_alerts": schedule_summary.total_alerts,
    }


def _ensure_notification_schedule(
    alert_record: AlertRecord,
    db_path: str | Path,
    *,
    scheduled_for: datetime,
) -> None:
    schedule_alert_notification(
        alert_record,
        db_path,
        scheduled_for=scheduled_for,
        created_at=scheduled_for,
    )


def _noop_notification_sender(_alert_record: AlertRecord, _config: AlertNotificationConfig) -> None:
    return None


def _infer_processed_at(demo_result: DemoRunResult) -> datetime:
    pipeline_result = demo_result.pipeline_result
    if pipeline_result.alert_build_result is not None and pipeline_result.alert_build_result.alert_record is not None:
        return pipeline_result.alert_build_result.alert_record.window_end
    if pipeline_result.feature_result is not None:
        return pipeline_result.feature_result.window_end
    if pipeline_result.cohort_result is not None and pipeline_result.cohort_result.cohort is not None:
        return pipeline_result.cohort_result.cohort.window_end
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
