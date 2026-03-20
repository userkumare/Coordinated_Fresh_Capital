"""Tests for deterministic run manifests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.manifest import (
    RunManifest,
    RunManifestArtifacts,
    RunManifestNotificationSummary,
    RunManifestPipelineSummary,
    build_run_artifacts_summary,
    list_run_manifests,
    main as manifest_main,
    read_run_artifacts_summary,
    read_latest_run_manifest,
    read_run_manifest,
    write_run_artifacts_summary,
    write_run_manifest,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "step10_demo_positive.json"


class RunManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_time = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def test_manifest_generation_after_successful_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            stdout = StringIO()
            with redirect_stdout(stdout):
                from fresh_capital.__main__ import main

                exit_code = main(
                    [
                        "--fixture-path",
                        str(FIXTURE_PATH),
                        "--output-dir",
                        str(output_dir),
                        "--as-of",
                        self.base_time.isoformat(),
                    ],
                    sender=lambda _record, _config: None,
                )

            summary = json.loads(stdout.getvalue())
            manifest_dir = output_dir / "manifests"
            manifest = read_latest_run_manifest(manifest_dir)
            self.assertTrue(manifest is not None and manifest.manifest_path.exists())
            self.assertTrue(manifest is not None and manifest_dir.exists())
            self.assertTrue((output_dir / "pipeline_result.json").exists())
            self.assertTrue((output_dir / "notification_report.json").exists())
            self.assertTrue((output_dir / "notification_status_report.json").exists())
            self.assertTrue((output_dir / "artifacts_summary.json").exists())
            artifacts_summary = read_run_artifacts_summary(output_dir / "artifacts_summary.json")
            self.assertTrue(artifacts_summary.all_artifacts_present)
            self.assertEqual(artifacts_summary.missing_artifacts, ())
            copy_path = output_dir / "artifacts_summary.copy.json"
            written_copy = write_run_artifacts_summary(artifacts_summary, copy_path)
            copied_summary = read_run_artifacts_summary(written_copy)
            self.assertEqual(copied_summary.to_dict(), artifacts_summary.to_dict())

        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(manifest)
        assert manifest is not None
        self.assertEqual(manifest.run_id, summary["run_id"])
        self.assertTrue(manifest.pipeline_summary.alert_built)
        self.assertTrue(manifest.notification_summary.notification_queued)
        self.assertTrue(manifest.notification_summary.notifications_processed)

    def test_no_alert_path_manifest_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            negative_fixture = Path(temp_dir) / "negative.json"
            payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            payload["market_snapshot"]["liquidity_usd"] = 200000.0
            negative_fixture.write_text(json.dumps(payload), encoding="utf-8")

            from fresh_capital.__main__ import main

            exit_code = main(
                [
                    "--fixture-path",
                    str(negative_fixture),
                    "--output-dir",
                    str(output_dir),
                    "--as-of",
                    self.base_time.isoformat(),
                ],
                sender=lambda _record, _config: None,
            )
            manifest = read_latest_run_manifest(output_dir / "manifests")
            self.assertTrue(manifest is not None and manifest.manifest_path.exists())
            artifacts_summary = build_run_artifacts_summary(
                manifest,
                status_report_path=output_dir / "notification_status_report.json",
                artifacts_summary_path=output_dir / "artifacts_summary.json",
            )

        self.assertEqual(exit_code, 0)
        assert manifest is not None
        self.assertFalse(manifest.pipeline_summary.alert_built)
        self.assertFalse(manifest.notification_summary.notification_queued)
        self.assertFalse(manifest.notification_summary.notifications_processed)
        self.assertEqual(manifest.notification_summary.total_alerts, 0)
        self.assertTrue(artifacts_summary.all_artifacts_present)

    def test_read_latest_manifest_and_specific_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir_1 = Path(temp_dir) / "out-1"
            output_dir_2 = Path(temp_dir) / "out-2"
            shared_manifest_dir = Path(temp_dir) / "manifests"
            from fresh_capital.__main__ import main

            main(
                [
                    "--fixture-path",
                    str(FIXTURE_PATH),
                    "--output-dir",
                    str(output_dir_1),
                    "--as-of",
                    self.base_time.isoformat(),
                ],
                sender=lambda _record, _config: None,
            )
            main(
                [
                    "--fixture-path",
                    str(FIXTURE_PATH),
                    "--output-dir",
                    str(output_dir_2),
                    "--as-of",
                    (self.base_time.replace(minute=30)).isoformat(),
                ],
                sender=lambda _record, _config: None,
            )

            manifest_1 = read_latest_run_manifest(output_dir_1 / "manifests")
            manifest_2 = read_latest_run_manifest(output_dir_2 / "manifests")
            assert manifest_1 is not None
            assert manifest_2 is not None

            cloned_1 = RunManifest(
                run_id=manifest_1.run_id,
                generated_at=manifest_1.generated_at,
                fixture_path=manifest_1.fixture_path,
                output_dir=manifest_1.output_dir,
                pipeline_summary=RunManifestPipelineSummary(
                    alert_built=manifest_1.pipeline_summary.alert_built,
                    detection_positive=manifest_1.pipeline_summary.detection_positive,
                    delivery_count=manifest_1.pipeline_summary.delivery_count,
                    stage_count=manifest_1.pipeline_summary.stage_count,
                ),
                notification_summary=RunManifestNotificationSummary(
                    notification_queued=manifest_1.notification_summary.notification_queued,
                    notifications_processed=manifest_1.notification_summary.notifications_processed,
                    total_alerts=manifest_1.notification_summary.total_alerts,
                    pending_count=manifest_1.notification_summary.pending_count,
                    sent_count=manifest_1.notification_summary.sent_count,
                    failed_count=manifest_1.notification_summary.failed_count,
                    canceled_count=manifest_1.notification_summary.canceled_count,
                    due_count=manifest_1.notification_summary.due_count,
                    scheduled_count=manifest_1.notification_summary.scheduled_count,
                    triggered_count=manifest_1.notification_summary.triggered_count,
                    rescheduled_count=manifest_1.notification_summary.rescheduled_count,
                    completed_count=manifest_1.notification_summary.completed_count,
                ),
                artifacts=RunManifestArtifacts(
                    summary_json_path=manifest_1.artifacts.summary_json_path,
                    summary_pretty_json_path=manifest_1.artifacts.summary_pretty_json_path,
                    alert_log_path=manifest_1.artifacts.alert_log_path,
                    delivery_database_path=manifest_1.artifacts.delivery_database_path,
                    delivery_status_log_path=manifest_1.artifacts.delivery_status_log_path,
                    notification_database_path=manifest_1.artifacts.notification_database_path,
                    notification_report_path=manifest_1.artifacts.notification_report_path,
                    manifest_path=shared_manifest_dir / f"{manifest_1.manifest_path.name}",
                ),
                manifest_path=shared_manifest_dir / f"{manifest_1.manifest_path.name}",
            )
            cloned_2 = RunManifest(
                run_id=manifest_2.run_id,
                generated_at=manifest_2.generated_at,
                fixture_path=manifest_2.fixture_path,
                output_dir=manifest_2.output_dir,
                pipeline_summary=RunManifestPipelineSummary(
                    alert_built=manifest_2.pipeline_summary.alert_built,
                    detection_positive=manifest_2.pipeline_summary.detection_positive,
                    delivery_count=manifest_2.pipeline_summary.delivery_count,
                    stage_count=manifest_2.pipeline_summary.stage_count,
                ),
                notification_summary=RunManifestNotificationSummary(
                    notification_queued=manifest_2.notification_summary.notification_queued,
                    notifications_processed=manifest_2.notification_summary.notifications_processed,
                    total_alerts=manifest_2.notification_summary.total_alerts,
                    pending_count=manifest_2.notification_summary.pending_count,
                    sent_count=manifest_2.notification_summary.sent_count,
                    failed_count=manifest_2.notification_summary.failed_count,
                    canceled_count=manifest_2.notification_summary.canceled_count,
                    due_count=manifest_2.notification_summary.due_count,
                    scheduled_count=manifest_2.notification_summary.scheduled_count,
                    triggered_count=manifest_2.notification_summary.triggered_count,
                    rescheduled_count=manifest_2.notification_summary.rescheduled_count,
                    completed_count=manifest_2.notification_summary.completed_count,
                ),
                artifacts=RunManifestArtifacts(
                    summary_json_path=manifest_2.artifacts.summary_json_path,
                    summary_pretty_json_path=manifest_2.artifacts.summary_pretty_json_path,
                    alert_log_path=manifest_2.artifacts.alert_log_path,
                    delivery_database_path=manifest_2.artifacts.delivery_database_path,
                    delivery_status_log_path=manifest_2.artifacts.delivery_status_log_path,
                    notification_database_path=manifest_2.artifacts.notification_database_path,
                    notification_report_path=manifest_2.artifacts.notification_report_path,
                    manifest_path=shared_manifest_dir / f"{manifest_2.manifest_path.name}",
                ),
                manifest_path=shared_manifest_dir / f"{manifest_2.manifest_path.name}",
            )
            write_run_manifest(cloned_1)
            write_run_manifest(cloned_2)
            artifacts_summary = build_run_artifacts_summary(
                cloned_2,
                status_report_path=output_dir_2 / "notification_status_report.json",
                artifacts_summary_path=shared_manifest_dir / "artifacts_summary.json",
            )

            manifests = list_run_manifests(shared_manifest_dir)
            latest = read_latest_run_manifest(shared_manifest_dir)
            first = read_run_manifest(manifests[0].manifest_path)

        self.assertEqual(len(manifests), 2)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.generated_at.isoformat(), "2026-03-20T12:30:00+00:00")
        self.assertEqual(first.run_id, manifests[0].run_id)
        self.assertEqual(first.manifest_path, manifests[0].manifest_path)
        self.assertFalse(artifacts_summary.missing_artifacts)

    def test_manifest_cli_paths_and_invalid_input_handling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            from fresh_capital.__main__ import main

            main(
                [
                    "--fixture-path",
                    str(FIXTURE_PATH),
                    "--output-dir",
                    str(output_dir),
                    "--as-of",
                    self.base_time.isoformat(),
                ],
                sender=lambda _record, _config: None,
            )
            manifest_dir = output_dir / "manifests"
            latest_stdout = StringIO()
            list_stdout = StringIO()
            show_stdout = StringIO()
            with redirect_stdout(latest_stdout):
                manifest_main(["--manifests-dir", str(manifest_dir), "latest"])
            with redirect_stdout(list_stdout):
                manifest_main(["--manifests-dir", str(manifest_dir), "list"])
            with redirect_stdout(show_stdout):
                manifest_main(
                    [
                        "--manifests-dir",
                        str(manifest_dir),
                        "show",
                        "--manifest-path",
                        str(next(manifest_dir.glob("*.json"))),
                    ]
                )

            latest_payload = json.loads(latest_stdout.getvalue())
            list_payload = json.loads(list_stdout.getvalue())
            show_payload = json.loads(show_stdout.getvalue())

            bad_manifest = Path(temp_dir) / "bad.json"
            bad_manifest.write_text(json.dumps({"bad": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_run_manifest(bad_manifest)
            with self.assertRaises(ValueError):
                read_run_artifacts_summary(bad_manifest)

        self.assertEqual(latest_payload["run_id"], show_payload["run_id"])
        self.assertEqual(len(list_payload), 1)


if __name__ == "__main__":
    unittest.main()
