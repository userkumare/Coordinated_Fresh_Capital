"""Deterministic run manifest helpers for Fresh Capital MVP runs."""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fresh_capital.demo.runner import DemoEndToEndResult


DEFAULT_MANIFESTS_DIR = Path("artifacts/final_run/manifests")


@dataclass(frozen=True, slots=True)
class RunManifestArtifacts:
    summary_json_path: Path
    summary_pretty_json_path: Path
    alert_log_path: Path
    delivery_database_path: Path
    delivery_status_log_path: Path
    notification_database_path: Path
    notification_report_path: Path
    manifest_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_log_path": str(self.alert_log_path),
            "delivery_database_path": str(self.delivery_database_path),
            "delivery_status_log_path": str(self.delivery_status_log_path),
            "manifest_path": str(self.manifest_path),
            "notification_database_path": str(self.notification_database_path),
            "notification_report_path": str(self.notification_report_path),
            "summary_json_path": str(self.summary_json_path),
            "summary_pretty_json_path": str(self.summary_pretty_json_path),
        }


@dataclass(frozen=True, slots=True)
class RunManifestPipelineSummary:
    alert_built: bool
    detection_positive: bool
    delivery_count: int
    stage_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_built": self.alert_built,
            "delivery_count": self.delivery_count,
            "detection_positive": self.detection_positive,
            "stage_count": self.stage_count,
        }


@dataclass(frozen=True, slots=True)
class RunManifestNotificationSummary:
    notification_queued: bool
    notifications_processed: bool
    total_alerts: int
    pending_count: int
    sent_count: int
    failed_count: int
    canceled_count: int
    due_count: int
    scheduled_count: int
    triggered_count: int
    rescheduled_count: int
    completed_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "canceled_count": self.canceled_count,
            "completed_count": self.completed_count,
            "due_count": self.due_count,
            "failed_count": self.failed_count,
            "notification_queued": self.notification_queued,
            "notifications_processed": self.notifications_processed,
            "pending_count": self.pending_count,
            "rescheduled_count": self.rescheduled_count,
            "scheduled_count": self.scheduled_count,
            "sent_count": self.sent_count,
            "total_alerts": self.total_alerts,
            "triggered_count": self.triggered_count,
        }


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    generated_at: datetime
    fixture_path: Path
    output_dir: Path
    pipeline_summary: RunManifestPipelineSummary
    notification_summary: RunManifestNotificationSummary
    artifacts: RunManifestArtifacts
    manifest_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": self.artifacts.to_dict(),
            "fixture_path": str(self.fixture_path),
            "generated_at": self.generated_at.isoformat(),
            "manifest_path": str(self.manifest_path),
            "notification_summary": self.notification_summary.to_dict(),
            "output_dir": str(self.output_dir),
            "pipeline_summary": self.pipeline_summary.to_dict(),
            "run_id": self.run_id,
        }


def build_run_manifest(
    result: DemoEndToEndResult,
    *,
    manifests_dir: str | Path | None = None,
) -> RunManifest:
    if not isinstance(result, DemoEndToEndResult):
        raise TypeError("result must be a DemoEndToEndResult")

    generated_at = result.notification_report.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    else:
        generated_at = generated_at.astimezone(timezone.utc)

    fixture_path = result.demo_result.fixture_summary.fixture_path.resolve()
    output_dir = result.demo_result.written_artifacts.summary_json_path.parent.resolve()
    manifest_dir = _normalize_manifest_dir(manifests_dir, output_dir)

    alert_built = bool(
        result.demo_result.pipeline_result.alert_build_result is not None
        and result.demo_result.pipeline_result.alert_build_result.is_alert_built
    )
    notifications_processed = len(result.schedule_processing_results) > 0
    notification_queued = result.notification_report.notification_summary.total_alerts > 0

    pipeline_summary = RunManifestPipelineSummary(
        alert_built=alert_built,
        detection_positive=bool(
            result.demo_result.pipeline_result.detection_result is not None
            and result.demo_result.pipeline_result.detection_result.is_detected
        ),
        delivery_count=len(result.demo_result.pipeline_result.delivery_results or ()),
        stage_count=len(result.demo_result.pipeline_result.stage_traces),
    )
    notification_summary = RunManifestNotificationSummary(
        notification_queued=notification_queued,
        notifications_processed=notifications_processed,
        total_alerts=result.notification_report.notification_summary.total_alerts,
        pending_count=result.notification_report.notification_summary.pending_count,
        sent_count=result.notification_report.notification_summary.sent_count,
        failed_count=result.notification_report.notification_summary.failed_count,
        canceled_count=result.notification_report.notification_summary.canceled_count,
        due_count=result.notification_report.notification_summary.due_count,
        scheduled_count=result.notification_report.schedule_summary.scheduled_count,
        triggered_count=result.notification_report.schedule_summary.triggered_count,
        rescheduled_count=result.notification_report.schedule_summary.rescheduled_count,
        completed_count=result.notification_report.schedule_summary.completed_count,
    )

    run_id = _build_run_id(
        generated_at=generated_at,
        fixture_path=fixture_path,
        output_dir=output_dir,
        pipeline_summary=pipeline_summary,
        notification_summary=notification_summary,
    )
    manifest_path = manifest_dir / f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}--{run_id}.json"
    artifacts = RunManifestArtifacts(
        summary_json_path=result.demo_result.written_artifacts.summary_json_path.resolve(),
        summary_pretty_json_path=result.demo_result.written_artifacts.summary_pretty_json_path.resolve(),
        alert_log_path=result.demo_result.written_artifacts.alert_log_path.resolve(),
        delivery_database_path=result.demo_result.written_artifacts.delivery_database_path.resolve(),
        delivery_status_log_path=result.demo_result.written_artifacts.delivery_status_log_path.resolve(),
        notification_database_path=result.notification_database_path.resolve(),
        notification_report_path=result.notification_report_path.resolve(),
        manifest_path=manifest_path,
    )
    return RunManifest(
        run_id=run_id,
        generated_at=generated_at,
        fixture_path=fixture_path,
        output_dir=output_dir,
        pipeline_summary=pipeline_summary,
        notification_summary=notification_summary,
        artifacts=artifacts,
        manifest_path=manifest_path,
    )


def write_run_manifest(manifest: RunManifest) -> Path:
    if not isinstance(manifest, RunManifest):
        raise TypeError("manifest must be a RunManifest")
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest.manifest_path


def read_run_manifest(manifest_path: str | Path) -> RunManifest:
    path = _normalize_manifest_path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _manifest_from_payload(payload, manifest_path=path)


def list_run_manifests(manifests_dir: str | Path) -> tuple[RunManifest, ...]:
    directory = _normalize_manifest_dir(manifests_dir, None)
    if not directory.exists():
        return ()
    manifests = [
        read_run_manifest(path)
        for path in sorted(directory.glob("*.json"))
        if path.is_file()
    ]
    return tuple(manifests)


def read_latest_run_manifest(manifests_dir: str | Path) -> RunManifest | None:
    manifests = list_run_manifests(manifests_dir)
    if not manifests:
        return None
    return manifests[-1]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "latest":
        manifest = read_latest_run_manifest(args.manifests_dir)
        if manifest is None:
            print(json.dumps({"error": "no manifests found"}, sort_keys=True), file=sys.stderr)
            return 1
        print(json.dumps(manifest.to_dict(), sort_keys=True))
        return 0

    if args.command == "list":
        manifests = list_run_manifests(args.manifests_dir)
        payload = [
            {
                "generated_at": manifest.generated_at.isoformat(),
                "manifest_path": str(manifest.manifest_path),
                "run_id": manifest.run_id,
            }
            for manifest in manifests
        ]
        print(json.dumps(payload, sort_keys=True))
        return 0

    if args.command == "show":
        manifest = read_run_manifest(args.manifest_path)
        print(json.dumps(manifest.to_dict(), sort_keys=True))
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fresh-capital-manifest", description="Inspect Fresh Capital run manifests.")
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=DEFAULT_MANIFESTS_DIR,
        help="Directory containing run manifest JSON files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("latest", help="Print the latest manifest as JSON.")
    subparsers.add_parser("list", help="List available manifests as compact JSON.")

    show_parser = subparsers.add_parser("show", help="Print a manifest from an explicit path.")
    show_parser.add_argument("--manifest-path", type=Path, required=True)
    return parser


def _manifest_from_payload(payload: dict[str, Any], *, manifest_path: Path) -> RunManifest:
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a JSON object")

    artifacts = payload.get("artifacts")
    notification_summary = payload.get("notification_summary")
    pipeline_summary = payload.get("pipeline_summary")
    fixture_path = payload.get("fixture_path")
    generated_at = payload.get("generated_at")
    manifest_path_value = payload.get("manifest_path")
    output_dir = payload.get("output_dir")
    run_id = payload.get("run_id")

    if not isinstance(artifacts, dict):
        raise ValueError("artifacts must be a JSON object")
    if not isinstance(notification_summary, dict):
        raise ValueError("notification_summary must be a JSON object")
    if not isinstance(pipeline_summary, dict):
        raise ValueError("pipeline_summary must be a JSON object")
    if not isinstance(fixture_path, str) or not fixture_path:
        raise ValueError("fixture_path must be a non-empty string")
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError("generated_at must be a non-empty string")
    if not isinstance(manifest_path_value, str) or not manifest_path_value:
        raise ValueError("manifest_path must be a non-empty string")
    if not isinstance(output_dir, str) or not output_dir:
        raise ValueError("output_dir must be a non-empty string")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")

    return RunManifest(
        run_id=run_id,
        generated_at=datetime.fromisoformat(generated_at),
        fixture_path=Path(fixture_path),
        output_dir=Path(output_dir),
        pipeline_summary=RunManifestPipelineSummary(
            alert_built=bool(pipeline_summary["alert_built"]),
            detection_positive=bool(pipeline_summary["detection_positive"]),
            delivery_count=int(pipeline_summary["delivery_count"]),
            stage_count=int(pipeline_summary["stage_count"]),
        ),
        notification_summary=RunManifestNotificationSummary(
            notification_queued=bool(notification_summary["notification_queued"]),
            notifications_processed=bool(notification_summary["notifications_processed"]),
            total_alerts=int(notification_summary["total_alerts"]),
            pending_count=int(notification_summary["pending_count"]),
            sent_count=int(notification_summary["sent_count"]),
            failed_count=int(notification_summary["failed_count"]),
            canceled_count=int(notification_summary["canceled_count"]),
            due_count=int(notification_summary["due_count"]),
            scheduled_count=int(notification_summary["scheduled_count"]),
            triggered_count=int(notification_summary["triggered_count"]),
            rescheduled_count=int(notification_summary["rescheduled_count"]),
            completed_count=int(notification_summary["completed_count"]),
        ),
        artifacts=RunManifestArtifacts(
            summary_json_path=Path(artifacts["summary_json_path"]),
            summary_pretty_json_path=Path(artifacts["summary_pretty_json_path"]),
            alert_log_path=Path(artifacts["alert_log_path"]),
            delivery_database_path=Path(artifacts["delivery_database_path"]),
            delivery_status_log_path=Path(artifacts["delivery_status_log_path"]),
            notification_database_path=Path(artifacts["notification_database_path"]),
            notification_report_path=Path(artifacts["notification_report_path"]),
            manifest_path=Path(manifest_path_value),
        ),
        manifest_path=manifest_path,
    )


def _build_run_id(
    *,
    generated_at: datetime,
    fixture_path: Path,
    output_dir: Path,
    pipeline_summary: RunManifestPipelineSummary,
    notification_summary: RunManifestNotificationSummary,
) -> str:
    payload = {
        "fixture_path": str(fixture_path),
        "generated_at": generated_at.isoformat(),
        "notification_summary": notification_summary.to_dict(),
        "output_dir": str(output_dir),
        "pipeline_summary": pipeline_summary.to_dict(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return digest[:16]


def _normalize_manifest_dir(manifests_dir: str | Path | None, output_dir: Path | None) -> Path:
    if manifests_dir is not None:
        return _normalize_path(manifests_dir)
    if output_dir is not None:
        return output_dir / "manifests"
    return DEFAULT_MANIFESTS_DIR


def _normalize_manifest_path(manifest_path: str | Path) -> Path:
    return _normalize_path(manifest_path)


def _normalize_path(path_value: str | Path) -> Path:
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str) and path_value:
        return Path(path_value)
    raise TypeError("path must be a non-empty string or Path")


if __name__ == "__main__":
    raise SystemExit(main())
