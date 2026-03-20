"""Tests for the fixture-driven demo runner."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.demo.runner import DemoRunRequest, load_demo_fixture, run_demo_fixture
from fresh_capital.demo.runner import main, run_demo_end_to_end


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "step10_demo_positive.json"


class DemoRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def test_valid_fixture_load_and_successful_pipeline_execution(self) -> None:
        fixture_summary, pipeline_request = load_demo_fixture(FIXTURE_PATH)

        self.assertEqual(fixture_summary.chain, "ethereum")
        self.assertEqual(fixture_summary.token_address, "0xtoken")
        self.assertEqual(fixture_summary.participant_count, 3)
        self.assertEqual(pipeline_request.market_snapshot.token_symbol, "ABC")
        self.assertEqual(len(tuple(pipeline_request.participants)), 3)

    def test_invalid_fixture_structure_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_fixture = Path(temp_dir) / "bad.json"
            bad_fixture.write_text(json.dumps({"chain": "ethereum"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_demo_fixture(bad_fixture)

    def test_deterministic_output_file_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_1, tempfile.TemporaryDirectory() as temp_dir_2:
            result_1 = run_demo_fixture(
                DemoRunRequest(
                    fixture_path=FIXTURE_PATH,
                    output_dir=Path(temp_dir_1),
                )
            )
            result_2 = run_demo_fixture(
                DemoRunRequest(
                    fixture_path=FIXTURE_PATH,
                    output_dir=Path(temp_dir_2),
                )
            )

            summary_1 = json.loads(result_1.written_artifacts.summary_json_path.read_text(encoding="utf-8"))
            summary_2 = json.loads(result_2.written_artifacts.summary_json_path.read_text(encoding="utf-8"))
            self.assertTrue(result_1.written_artifacts.summary_json_path.exists())
            self.assertTrue(result_1.written_artifacts.summary_pretty_json_path.exists())
            self.assertTrue(result_1.written_artifacts.alert_log_path.exists())
            self.assertTrue(result_1.written_artifacts.delivery_database_path.exists())
            self.assertTrue(result_1.written_artifacts.delivery_status_log_path.exists())

        self.assertEqual(summary_1["fixture"], summary_2["fixture"])
        self.assertEqual(summary_1["pipeline"], summary_2["pipeline"])

    def test_positive_path_with_alert_output_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_demo_fixture(
                DemoRunRequest(
                    fixture_path=FIXTURE_PATH,
                    output_dir=Path(temp_dir),
                )
            )

            alert_log = result.written_artifacts.alert_log_path.read_text(encoding="utf-8")
            summary = json.loads(result.written_artifacts.summary_json_path.read_text(encoding="utf-8"))

        self.assertTrue(result.pipeline_result.alert_build_result.is_alert_built if result.pipeline_result.alert_build_result else False)
        self.assertIn('"status": "created"', alert_log)
        self.assertEqual(summary["pipeline"]["alert_built"], True)
        self.assertGreaterEqual(summary["pipeline"]["delivery_count"], 1)

    def test_negative_path_stops_before_alert_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_fixture = Path(temp_dir) / "negative.json"
            payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            payload["market_snapshot"]["liquidity_usd"] = 200000.0
            bad_fixture.write_text(json.dumps(payload), encoding="utf-8")

            result = run_demo_fixture(
                DemoRunRequest(
                    fixture_path=bad_fixture,
                    output_dir=Path(temp_dir) / "out",
                )
            )

            self.assertTrue(result.written_artifacts.summary_json_path.exists())
            self.assertFalse(result.written_artifacts.alert_log_path.exists())

        self.assertIsNotNone(result.pipeline_result.detection_result)
        self.assertFalse(result.pipeline_result.detection_result.is_detected if result.pipeline_result.detection_result else True)
        self.assertIsNone(result.pipeline_result.alert_build_result)

    def test_stable_output_shape_and_key_presence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_demo_fixture(
                DemoRunRequest(
                    fixture_path=FIXTURE_PATH,
                    output_dir=Path(temp_dir),
                )
            )
            summary = json.loads(result.written_artifacts.summary_json_path.read_text(encoding="utf-8"))

        self.assertEqual(set(summary.keys()), {"artifacts", "fixture", "pipeline"})
        self.assertEqual(set(summary["artifacts"].keys()), {
            "alert_log_path",
            "delivery_database_path",
            "delivery_status_log_path",
            "summary_json_path",
            "summary_pretty_json_path",
        })
        self.assertEqual(set(summary["fixture"].keys()), {
            "chain",
            "fixture_path",
            "participant_count",
            "token_address",
            "token_symbol",
        })
        self.assertIn("stage_statuses", summary["pipeline"])
        self.assertIsInstance(summary["pipeline"]["stage_statuses"], list)

    def test_end_to_end_demo_execution_from_fixture_writes_notification_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = run_demo_end_to_end(
                DemoRunRequest(
                    fixture_path=FIXTURE_PATH,
                    output_dir=output_dir,
                ),
                as_of=self.now,
                sender=lambda _record, _config: None,
            )

            pipeline_summary = json.loads(result.demo_result.written_artifacts.summary_json_path.read_text(encoding="utf-8"))
            notification_report = json.loads(result.notification_report_path.read_text(encoding="utf-8"))
            status_report_path = output_dir / "notification_status_report.json"
            status_report = json.loads(status_report_path.read_text(encoding="utf-8"))
            self.assertTrue(result.demo_result.written_artifacts.summary_json_path.exists())
            self.assertTrue(result.notification_database_path.exists())
            self.assertTrue(result.notification_report_path.exists())
            self.assertTrue(status_report_path.exists())

        self.assertEqual(pipeline_summary["pipeline"]["alert_built"], True)
        self.assertEqual(notification_report["notification_summary"]["total_alerts"], 1)
        self.assertEqual(notification_report["notification_summary"]["sent_count"], 1)
        self.assertEqual(notification_report["schedule_summary"]["completed_count"], 1)
        self.assertEqual(status_report["processed_successfully_count"], 1)
        self.assertEqual(status_report["pending_count"], 0)
        self.assertEqual(status_report["failed_count"], 0)
        self.assertTrue(status_report["final_notification_outcome_summary"]["all_processed"])

    def test_no_alert_path_writes_empty_notification_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            negative_fixture = Path(temp_dir) / "negative.json"
            payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            payload["market_snapshot"]["liquidity_usd"] = 200000.0
            negative_fixture.write_text(json.dumps(payload), encoding="utf-8")
            output_dir = Path(temp_dir) / "out"

            result = run_demo_end_to_end(
                DemoRunRequest(
                    fixture_path=negative_fixture,
                    output_dir=output_dir,
                ),
                as_of=self.now,
                sender=lambda _record, _config: None,
            )

            notification_report = json.loads(result.notification_report_path.read_text(encoding="utf-8"))
            status_report_path = output_dir / "notification_status_report.json"
            status_report = json.loads(status_report_path.read_text(encoding="utf-8"))

        self.assertIsNone(result.demo_result.pipeline_result.alert_build_result)
        self.assertEqual(notification_report["notification_summary"]["total_alerts"], 0)
        self.assertEqual(notification_report["schedule_summary"]["total_alerts"], 0)
        self.assertEqual(result.schedule_processing_results, ())
        self.assertEqual(status_report["processed_successfully_count"], 0)
        self.assertEqual(status_report["pending_count"], 0)
        self.assertEqual(status_report["failed_count"], 0)

    def test_cli_uses_default_fixture_and_prints_shell_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--output-dir",
                        str(Path(temp_dir)),
                    ],
                    sender=lambda _record, _config: None,
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["fixture_path"], str(FIXTURE_PATH))
        self.assertTrue(payload["pipeline_alert_built"])
        self.assertEqual(payload["notification_sent_count"], 1)
        self.assertEqual(payload["schedule_completed_count"], 1)

    def test_invalid_cli_argument_handling(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as exc_info:
                main(["--unknown-option"])

        self.assertEqual(exc_info.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
