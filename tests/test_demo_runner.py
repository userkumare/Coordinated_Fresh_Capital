"""Tests for the fixture-driven demo runner."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.demo.runner import DemoRunRequest, load_demo_fixture, run_demo_fixture


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "step10_demo_positive.json"


class DemoRunnerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
