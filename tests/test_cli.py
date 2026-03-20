"""Tests for the final operator-facing Fresh Capital shell command."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.__main__ import main


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "step10_demo_positive.json"


class FinalCliTests(unittest.TestCase):
    def test_default_fixture_no_args_executes_end_to_end(self) -> None:
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main([], sender=lambda _record, _config: None)
            finally:
                os.chdir(previous_cwd)

            output_dir = Path(temp_dir) / "artifacts" / "final_run"
            summary = json.loads(stdout.getvalue())
            stderr_lines = [json.loads(line) for line in stderr.getvalue().splitlines() if line]
            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["alerts_triggered"], 1)
            self.assertEqual(summary["notifications_processed"], 1)
            self.assertIn("manifest_path", summary)
            self.assertIn("run_id", summary)
            self.assertIn("artifacts_summary_path", summary)
            self.assertIn("validation_report_path", summary)
            self.assertTrue(summary["validation_passed"])
            self.assertTrue((output_dir / "pipeline_result.json").exists())
            self.assertTrue((output_dir / "notification_report.json").exists())
            self.assertTrue((output_dir / "artifacts_summary.json").exists())
            self.assertTrue((output_dir / "final_validation_report.json").exists())
            self.assertTrue(Path(summary["manifest_path"]).exists())
            self.assertTrue((output_dir / "manifests").exists())
            self.assertEqual(stderr_lines[0]["event"], "run_started")
            self.assertEqual(stderr_lines[1]["event"], "manifest_written")
            self.assertEqual(stderr_lines[-1]["event"], "run_completed")

    def test_provided_fixture_argument_executes_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "--fixture-path",
                        str(FIXTURE_PATH),
                        "--output-dir",
                        str(Path(temp_dir)),
                    ],
                    sender=lambda _record, _config: None,
                )

            summary = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["fixture_path"], str(FIXTURE_PATH))
            self.assertEqual(summary["alerts_triggered"], 1)
            self.assertEqual(summary["notification_sent_count"], 1)
            self.assertIn("manifest_path", summary)
            self.assertIn("artifacts_summary_path", summary)
            self.assertIn("validation_report_path", summary)
            self.assertTrue((Path(temp_dir) / "pipeline_result.json").exists())

    def test_status_command_retrieves_latest_completed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--fixture-path",
                        str(FIXTURE_PATH),
                        "--output-dir",
                        str(Path(temp_dir)),
                    ],
                    sender=lambda _record, _config: None,
                )

            summary = json.loads(stdout.getvalue())
            status_stdout = StringIO()
            status_stderr = StringIO()
            with redirect_stdout(status_stdout), redirect_stderr(status_stderr):
                status_exit_code = main(
                    [
                        "status",
                        "--manifests-dir",
                        str(Path(temp_dir) / "manifests"),
                    ]
                )

            status_payload = json.loads(status_stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(status_exit_code, 0)
        self.assertEqual(status_payload["run_id"], summary["run_id"])
        self.assertTrue(status_payload["artifacts_summary"]["all_artifacts_present"])
        self.assertTrue(status_payload["validation_report"]["validation_passed"])
        self.assertEqual(status_payload["report"]["processed_successfully_count"], 1)
        self.assertEqual(status_payload["report"]["pending_count"], 0)
        self.assertEqual(status_payload["report"]["failed_count"], 0)
        self.assertTrue(status_payload["report"]["final_notification_outcome_summary"]["all_processed"])
        self.assertEqual(status_stderr.getvalue(), "")

    def test_invalid_status_request_returns_deterministic_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            status_stdout = StringIO()
            status_stderr = StringIO()
            with redirect_stdout(status_stdout), redirect_stderr(status_stderr):
                exit_code = main(
                    [
                        "status",
                        "--manifest-path",
                        str(Path(temp_dir) / "missing-manifest.json"),
                    ]
                )

            stderr_lines = [json.loads(line) for line in status_stderr.getvalue().splitlines() if line]

        self.assertEqual(exit_code, 1)
        self.assertEqual(status_stdout.getvalue(), "")
        self.assertEqual(stderr_lines[-1]["event"], "status_failed")
        self.assertEqual(stderr_lines[-1]["error_type"], "FileNotFoundError")

    def test_invalid_cli_argument_handling(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as exc_info:
                main(["--definitely-invalid"])

        self.assertEqual(exc_info.exception.code, 2)

    def test_processing_failure_is_logged_and_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "--fixture-path",
                        str(Path(temp_dir) / "missing-fixture.json"),
                        "--output-dir",
                        str(Path(temp_dir)),
                    ],
                )

            stdout_payload = stdout.getvalue().strip()
            stderr_lines = [json.loads(line) for line in stderr.getvalue().splitlines() if line]

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_payload, "")
        self.assertEqual(stderr_lines[-1]["event"], "run_failed")
        self.assertEqual(stderr_lines[-1]["error_type"], "FileNotFoundError")
        self.assertIn("missing-fixture.json", stderr_lines[-1]["message"])

    def test_validation_report_captures_pending_notifications(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()

            def sender(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("always failing")

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "--fixture-path",
                        str(FIXTURE_PATH),
                        "--output-dir",
                        str(Path(temp_dir)),
                    ],
                    sender=sender,
                )

            summary = json.loads(stdout.getvalue())
            validation_report = json.loads((Path(temp_dir) / "final_validation_report.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertFalse(summary["validation_passed"])
        self.assertFalse(validation_report["validation_passed"])
        self.assertEqual(validation_report["notification_status_report"]["status_check"]["pending_count"], 1)
        self.assertEqual(validation_report["notification_status_report"]["status_check"]["failed_count"], 0)
        self.assertEqual(validation_report["notification_status_report"]["status_check"]["all_processed"], False)


if __name__ == "__main__":
    unittest.main()
