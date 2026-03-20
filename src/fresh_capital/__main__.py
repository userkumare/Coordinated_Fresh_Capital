"""Final shell entrypoint for the Fresh Capital MVP."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fresh_capital.demo.runner import DEFAULT_DEMO_FIXTURE_PATH, DemoRunRequest, run_demo_end_to_end
from fresh_capital.manifest import (
    build_run_artifacts_summary,
    build_run_manifest,
    ensure_run_artifacts_complete,
    read_latest_run_manifest,
    read_run_artifacts_summary,
    read_run_manifest,
    write_run_artifacts_summary,
    write_run_manifest,
)
from fresh_capital.notifications.verification import (
    build_alert_completion_status_report,
    read_alert_completion_status_report,
)
from fresh_capital.notifications.webhook import AlertNotificationConfig


DEFAULT_OUTPUT_DIR = Path("artifacts/final_run")


def main(
    argv: list[str] | None = None,
    *,
    sender: Callable[[Any, AlertNotificationConfig], None] | None = None,
) -> int:
    """Run the final deterministic one-command pipeline."""
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "status":
        return _main_status(argv_list[1:])

    parser = _build_parser()
    args = parser.parse_args(argv_list)
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
    artifacts_summary_path = args.output_dir.resolve() / "artifacts_summary.json"
    artifacts_summary = ensure_run_artifacts_complete(
        manifest,
        status_report_path=result.demo_result.written_artifacts.summary_json_path.parent / "notification_status_report.json",
        artifacts_summary_path=artifacts_summary_path,
    )
    write_run_artifacts_summary(artifacts_summary, artifacts_summary_path)
    summary = _build_summary(result, manifest_path=manifest.manifest_path, run_id=manifest.run_id)
    _emit_progress(
        "run_completed",
        output_dir=str(args.output_dir),
        alerts_triggered=summary["alerts_triggered"],
        notifications_processed=summary["notifications_processed"],
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


def _main_status(argv: list[str] | None = None) -> int:
    parser = _build_status_parser()
    args = parser.parse_args(argv)

    try:
        if args.manifest_path is not None:
            manifest = read_run_manifest(args.manifest_path)
        else:
            manifest = read_latest_run_manifest(args.manifests_dir)
            if manifest is None:
                print(json.dumps({"error": "no manifests found"}, sort_keys=True), file=sys.stderr)
                return 1

        report_path = manifest.output_dir / "notification_status_report.json"
        if report_path.exists():
            report = read_alert_completion_status_report(report_path)
        else:
            report = build_alert_completion_status_report(
                manifest.artifacts.notification_database_path,
                checked_at=manifest.generated_at,
            )
        artifacts_summary_path = manifest.output_dir / "artifacts_summary.json"
        if artifacts_summary_path.exists():
            artifacts_summary = read_run_artifacts_summary(artifacts_summary_path)
        else:
            artifacts_summary = build_run_artifacts_summary(
                manifest,
                status_report_path=report_path,
                artifacts_summary_path=artifacts_summary_path,
            )

        payload = {
            "artifacts_summary": artifacts_summary.to_dict(),
            "artifacts_summary_path": str(artifacts_summary_path),
            "manifest_path": str(manifest.manifest_path),
            "notification_status_report_path": str(report_path),
            "output_dir": str(manifest.output_dir),
            "report": report.to_dict(),
            "run_id": manifest.run_id,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - status CLI must surface deterministic failures
        _emit_error("status_failed", exc)
        return 1


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


def _build_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fresh-capital status", description="Inspect alert completion status for a completed run.")
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Path to a run manifest JSON file. Defaults to the latest manifest in --manifests-dir.",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "manifests",
        help="Directory containing run manifests when --manifest-path is not provided.",
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
        "notification_status_report_path": str(result.demo_result.written_artifacts.summary_json_path.parent / "notification_status_report.json"),
        "artifacts_summary_path": str(result.demo_result.written_artifacts.summary_json_path.parent / "artifacts_summary.json"),
        "notification_sent_count": report.notification_summary.sent_count,
        "notification_total_alerts": report.notification_summary.total_alerts,
        "notifications_processed": notifications_processed,
        "artifacts_complete": True,
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
