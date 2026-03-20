"""Final shell entrypoint for the Fresh Capital MVP."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fresh_capital.demo.runner import DEFAULT_DEMO_FIXTURE_PATH, DemoRunRequest, run_demo_end_to_end
from fresh_capital.manifest import build_run_manifest, write_run_manifest
from fresh_capital.notifications.webhook import AlertNotificationConfig


DEFAULT_OUTPUT_DIR = Path("artifacts/final_run")


def main(
    argv: list[str] | None = None,
    *,
    sender: Callable[[Any, AlertNotificationConfig], None] | None = None,
) -> int:
    """Run the final deterministic one-command pipeline."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    request = DemoRunRequest(
        fixture_path=args.fixture_path,
        output_dir=args.output_dir,
    )

    _emit_progress(
        "run_started",
        fixture_path=str(args.fixture_path),
        output_dir=str(args.output_dir),
        process_notifications=not args.skip_notification_processing,
    )

    try:
        result = run_demo_end_to_end(
            request,
            sender=sender,
            as_of=args.as_of,
            process_notifications=not args.skip_notification_processing,
        )
    except Exception as exc:  # noqa: BLE001 - final CLI must surface deterministic failures
        _emit_error("run_failed", exc)
        return 1

    manifest_root = args.output_dir.resolve() / "manifests"
    manifest = build_run_manifest(result, manifests_dir=manifest_root)
    write_run_manifest(manifest)
    _emit_progress("manifest_written", manifest_path=str(manifest.manifest_path), run_id=manifest.run_id)
    summary = _build_summary(result, manifest_path=manifest.manifest_path, run_id=manifest.run_id)
    _emit_progress(
        "run_completed",
        output_dir=str(args.output_dir),
        alerts_triggered=summary["alerts_triggered"],
        notifications_processed=summary["notifications_processed"],
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fresh-capital", description="Run the full Fresh Capital MVP pipeline.")
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=DEFAULT_DEMO_FIXTURE_PATH,
        help="Path to a fixture JSON file. Defaults to the bundled demo fixture.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where compact artifacts will be written.",
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
        help="Run the pipeline and build artifacts without processing notification state.",
    )
    return parser


def _build_summary(result: Any, *, manifest_path: Path, run_id: str) -> dict[str, Any]:
    pipeline_result = result.demo_result.pipeline_result
    report = result.notification_report
    alerts_triggered = 1 if pipeline_result.alert_build_result and pipeline_result.alert_build_result.is_alert_built else 0
    notifications_processed = len(result.schedule_processing_results)
    return {
        "alerts_triggered": alerts_triggered,
        "fixture_path": str(result.demo_result.fixture_summary.fixture_path),
        "notification_database_path": str(result.notification_database_path),
        "notification_failed_count": report.notification_summary.failed_count,
        "notification_report_path": str(result.notification_report_path),
        "notification_sent_count": report.notification_summary.sent_count,
        "notification_total_alerts": report.notification_summary.total_alerts,
        "notifications_processed": notifications_processed,
        "manifest_path": str(manifest_path),
        "output_dir": str(result.demo_result.written_artifacts.summary_json_path.parent),
        "pipeline_result_path": str(result.demo_result.written_artifacts.summary_json_path),
        "run_id": run_id,
        "schedule_total_alerts": report.schedule_summary.total_alerts,
    }


def _emit_progress(event: str, **fields: Any) -> None:
    payload = {"event": event, "kind": "progress", **fields}
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def _emit_error(event: str, exc: Exception) -> None:
    payload = {
        "event": event,
        "error_type": exc.__class__.__name__,
        "kind": "error",
        "message": str(exc),
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse validates syntax, but keep explicit failure
        raise argparse.ArgumentTypeError("as-of must be an ISO 8601 datetime") from exc


if __name__ == "__main__":
    raise SystemExit(main())
