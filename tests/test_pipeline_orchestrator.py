"""Tests for the deterministic end-to-end Fresh Capital pipeline orchestration."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.alerts.delivery import read_delivered_alerts
from fresh_capital.domain.enums import ServiceType, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.pipeline.orchestrator import (
    FreshCapitalPipelineRequest,
    PipelineParticipantInput,
    PipelineStageStatus,
    run_fresh_capital_pipeline,
)


class PipelineOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_participant(
        self,
        *,
        suffix: str,
        amount_usd: float,
        funded_at: datetime | None = None,
        service_type: ServiceType = ServiceType.NONE,
        address_age_days: int = 7,
        previous_tx_count: int = 5,
        distinct_tokens_before_window: int = 3,
    ) -> PipelineParticipantInput:
        address = AddressRecord(
            address=f"0xaddr{suffix}",
            chain="ethereum",
            first_seen_at=self.now - timedelta(days=max(address_age_days, 1)),
            last_seen_at=self.now,
            address_age_days=address_age_days,
            previous_tx_count=previous_tx_count,
            distinct_tokens_before_window=distinct_tokens_before_window,
            service_type=service_type,
            labels=("normalized",),
        )
        funding_event = FundingEvent(
            event_id=f"fund-{suffix}",
            address=address.address,
            chain="ethereum",
            funded_at=funded_at or (self.now - timedelta(minutes=int(suffix) * 10)),
            source_address=f"0xfunder{suffix}",
            source_type=SourceType.EXCHANGE,
            asset_symbol="USDC",
            amount=amount_usd,
            amount_usd=amount_usd,
            tx_hash=f"0xtx{suffix}",
        )
        return PipelineParticipantInput(address=address, funding_event=funding_event)

    def make_snapshot(self) -> TokenMarketSnapshot:
        return TokenMarketSnapshot(
            snapshot_id="snap-1",
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            captured_at=self.now,
            price_usd=1.0,
            liquidity_usd=150000.0,
            volume_24h_usd=400000.0,
            holders_count=4200,
            market_cap_usd=1000000.0,
            is_shortable=True,
            short_liquidity_usd=50000.0,
        )

    def test_full_positive_end_to_end_path(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            alert_log_path = Path(temp_dir) / "alerts.jsonl"
            database_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            result = run_fresh_capital_pipeline(
                FreshCapitalPipelineRequest(
                    participants=participants,
                    market_snapshot=self.make_snapshot(),
                    alert_log_path=alert_log_path,
                    delivery_database_path=database_path,
                    delivery_status_log_path=status_log_path,
                )
            )
            delivered_rows = read_delivered_alerts(database_path)

        self.assertEqual(
            [trace.stage_name for trace in result.stage_traces],
            [
                "participant_classification",
                "cohort_build",
                "feature_extraction",
                "detection",
                "alert_build",
                "alert_handling",
                "delivery",
            ],
        )
        self.assertTrue(all(trace.stage_status == PipelineStageStatus.COMPLETED for trace in result.stage_traces))
        self.assertTrue(all(not trace.stage_skipped for trace in result.stage_traces))
        self.assertIsNotNone(result.cohort_result)
        self.assertTrue(result.cohort_result.is_valid_cohort if result.cohort_result else False)
        self.assertIsNotNone(result.feature_result)
        self.assertIsNotNone(result.detection_result)
        self.assertTrue(result.detection_result.is_detected if result.detection_result else False)
        self.assertIsNotNone(result.alert_build_result)
        self.assertTrue(result.alert_build_result.is_alert_built if result.alert_build_result else False)
        self.assertIsNotNone(result.alert_handling_result)
        self.assertTrue(result.alert_handling_result.is_stored if result.alert_handling_result else False)
        self.assertIsNotNone(result.delivery_results)
        self.assertEqual(len(result.delivery_results or ()), 1)
        self.assertTrue(result.delivery_results[0].is_delivered if result.delivery_results else False)
        self.assertEqual(len(delivered_rows), 1)
        self.assertEqual(delivered_rows[0]["status"], "delivered")

    def test_stops_at_fresh_address_cohort_gate_failure(self) -> None:
        participants = (
            self.make_participant(
                suffix="1",
                amount_usd=10000.0,
                funded_at=self.now - timedelta(minutes=35),
                service_type=ServiceType.EXCHANGE,
            ),
            self.make_participant(
                suffix="2",
                amount_usd=8000.0,
                funded_at=self.now - timedelta(minutes=20),
                service_type=ServiceType.EXCHANGE,
            ),
            self.make_participant(
                suffix="3",
                amount_usd=7000.0,
                funded_at=self.now - timedelta(minutes=5),
                service_type=ServiceType.EXCHANGE,
            ),
        )

        result = run_fresh_capital_pipeline(
            FreshCapitalPipelineRequest(
                participants=participants,
                market_snapshot=self.make_snapshot(),
            )
        )

        self.assertEqual(
            [trace.stage_name for trace in result.stage_traces],
            [
                "participant_classification",
                "cohort_build",
                "feature_extraction",
                "detection",
                "alert_build",
                "alert_handling",
                "delivery",
            ],
        )
        self.assertEqual(result.stage_traces[1].stage_status, PipelineStageStatus.FAILED)
        self.assertTrue(all(trace.stage_skipped for trace in result.stage_traces[2:]))
        self.assertIsNotNone(result.cohort_result)
        self.assertFalse(result.cohort_result.is_valid_cohort if result.cohort_result else True)
        self.assertIsNone(result.feature_result)
        self.assertIsNone(result.detection_result)
        self.assertIsNone(result.alert_build_result)
        self.assertIsNone(result.alert_handling_result)
        self.assertIsNone(result.delivery_results)

    def test_stops_at_detector_failure_without_building_alert(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=20000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=3000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=2000.0, funded_at=self.now - timedelta(minutes=5)),
        )

        result = run_fresh_capital_pipeline(
            FreshCapitalPipelineRequest(
                participants=participants,
                market_snapshot=self.make_snapshot(),
            )
        )

        self.assertEqual(result.stage_traces[3].stage_status, PipelineStageStatus.FAILED)
        self.assertTrue(all(trace.stage_skipped for trace in result.stage_traces[4:]))
        self.assertIsNotNone(result.cohort_result)
        self.assertIsNotNone(result.feature_result)
        self.assertIsNotNone(result.detection_result)
        self.assertFalse(result.detection_result.is_detected if result.detection_result else True)
        self.assertIsNone(result.alert_build_result)
        self.assertIsNone(result.alert_handling_result)
        self.assertIsNone(result.delivery_results)

    def test_positive_path_can_return_handler_and_delivery_outputs(self) -> None:
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            alert_log_path = Path(temp_dir) / "alerts.jsonl"
            database_path = Path(temp_dir) / "alerts.sqlite"
            status_log_path = Path(temp_dir) / "alerts_status.jsonl"
            result = run_fresh_capital_pipeline(
                FreshCapitalPipelineRequest(
                    participants=participants,
                    market_snapshot=self.make_snapshot(),
                    alert_log_path=alert_log_path,
                    delivery_database_path=database_path,
                    delivery_status_log_path=status_log_path,
                )
            )

        self.assertIsNotNone(result.alert_handling_result)
        self.assertTrue(result.alert_handling_result.is_stored if result.alert_handling_result else False)
        self.assertIsNotNone(result.delivery_results)
        self.assertEqual(result.delivery_results[0].status.value, "delivered")

    def test_stage_ordering_and_invalid_input_handling(self) -> None:
        with self.assertRaises(TypeError):
            run_fresh_capital_pipeline(object())  # type: ignore[arg-type]

        with self.assertRaises(ValueError):
            run_fresh_capital_pipeline(
                FreshCapitalPipelineRequest(
                    participants=(),
                    market_snapshot=self.make_snapshot(),
                )
            )

        result = run_fresh_capital_pipeline(
            FreshCapitalPipelineRequest(
                participants=(
                    self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
                    self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
                    self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
                ),
                market_snapshot=self.make_snapshot(),
            )
        )

        self.assertEqual(
            [trace.stage_name for trace in result.stage_traces],
            [
                "participant_classification",
                "cohort_build",
                "feature_extraction",
                "detection",
                "alert_build",
                "alert_handling",
                "delivery",
            ],
        )
        self.assertEqual(
            [trace.stage_status for trace in result.stage_traces],
            [
                PipelineStageStatus.COMPLETED,
                PipelineStageStatus.COMPLETED,
                PipelineStageStatus.COMPLETED,
                PipelineStageStatus.COMPLETED,
                PipelineStageStatus.COMPLETED,
                PipelineStageStatus.SKIPPED,
                PipelineStageStatus.SKIPPED,
            ],
        )


if __name__ == "__main__":
    unittest.main()
