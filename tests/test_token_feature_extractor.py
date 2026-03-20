"""Tests for deterministic token detection feature extraction."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.builders.cohort import CohortBuildParticipant, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import classify_fresh_address
from fresh_capital.domain.enums import ServiceType, SourceType
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.extractors.token_features import extract_token_detection_features


class TokenFeatureExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def make_participant(
        self,
        *,
        suffix: str,
        amount_usd: float,
        funded_at: datetime | None = None,
        service_type: ServiceType = ServiceType.NONE,
    ) -> CohortBuildParticipant:
        address = AddressRecord(
            address=f"0xaddr{suffix}",
            chain="ethereum",
            first_seen_at=self.now - timedelta(days=7),
            last_seen_at=self.now,
            address_age_days=7,
            previous_tx_count=5,
            distinct_tokens_before_window=3,
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
        return CohortBuildParticipant(
            address=address,
            fresh_classification=classify_fresh_address(address),
            funding_event=funding_event,
        )

    def make_snapshot(
        self,
        *,
        liquidity_usd: float = 200000.0,
        market_cap_usd: float | None = 1000000.0,
        captured_at: datetime | None = None,
    ) -> TokenMarketSnapshot:
        return TokenMarketSnapshot(
            snapshot_id="snap-1",
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            captured_at=captured_at or self.now,
            price_usd=1.25,
            liquidity_usd=liquidity_usd,
            volume_24h_usd=400000.0,
            holders_count=4200,
            market_cap_usd=market_cap_usd,
        )

    def build_valid_cohort(self):
        participants = (
            self.make_participant(suffix="1", amount_usd=10000.0, funded_at=self.now - timedelta(minutes=35)),
            self.make_participant(suffix="2", amount_usd=8000.0, funded_at=self.now - timedelta(minutes=20)),
            self.make_participant(suffix="3", amount_usd=7000.0, funded_at=self.now - timedelta(minutes=5)),
        )
        result = build_fresh_cohort("ethereum", "0xtoken", "ABC", participants)
        assert result.cohort is not None
        return result.cohort

    def test_normal_valid_feature_extraction(self) -> None:
        result = extract_token_detection_features(self.build_valid_cohort(), self.make_snapshot())

        self.assertEqual(result.metrics.fresh_participant_count, 3)
        self.assertEqual(result.metrics.total_fresh_capital_usd, 25000.0)
        self.assertAlmostEqual(result.metrics.average_capital_per_fresh_participant_usd, 25000.0 / 3.0)
        self.assertAlmostEqual(result.metrics.top_participant_share or 0.0, 0.4)
        self.assertAlmostEqual(result.metrics.top_2_participant_concentration_ratio or 0.0, 0.72)
        self.assertAlmostEqual(result.metrics.cohort_timing_span_minutes or 0.0, 30.0)
        self.assertAlmostEqual(result.metrics.cohort_age_to_snapshot_minutes or 0.0, 5.0)
        self.assertAlmostEqual(result.metrics.market_cap_relative_funding_ratio or 0.0, 0.025)
        self.assertAlmostEqual(result.metrics.liquidity_relative_funding_ratio or 0.0, 0.125)
        self.assertEqual(result.unavailable_fields, ())

    def test_missing_optional_market_inputs_are_explicit(self) -> None:
        result = extract_token_detection_features(
            self.build_valid_cohort(),
            self.make_snapshot(market_cap_usd=None, liquidity_usd=0.0),
        )

        self.assertIsNone(result.metrics.market_cap_relative_funding_ratio)
        self.assertIsNone(result.metrics.liquidity_relative_funding_ratio)
        self.assertEqual(
            result.unavailable_fields,
            (
                "market_cap_relative_funding_ratio",
                "liquidity_relative_funding_ratio",
            ),
        )

    def test_top_share_calculation_is_deterministic(self) -> None:
        result = extract_token_detection_features(self.build_valid_cohort(), self.make_snapshot())

        self.assertAlmostEqual(result.metrics.top_participant_share or 0.0, 10000.0 / 25000.0)
        self.assertAlmostEqual(result.metrics.top_2_participant_concentration_ratio or 0.0, 18000.0 / 25000.0)

    def test_average_funding_calculation(self) -> None:
        result = extract_token_detection_features(self.build_valid_cohort(), self.make_snapshot())

        self.assertAlmostEqual(result.metrics.average_capital_per_fresh_participant_usd, (10000.0 + 8000.0 + 7000.0) / 3.0)

    def test_ratio_calculations(self) -> None:
        result = extract_token_detection_features(
            self.build_valid_cohort(),
            self.make_snapshot(liquidity_usd=50000.0, market_cap_usd=250000.0),
        )

        self.assertAlmostEqual(result.metrics.market_cap_relative_funding_ratio or 0.0, 0.1)
        self.assertAlmostEqual(result.metrics.liquidity_relative_funding_ratio or 0.0, 0.5)

    def test_invalid_input_type_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            extract_token_detection_features(object(), self.make_snapshot())  # type: ignore[arg-type]

    def test_chain_mismatch_is_rejected(self) -> None:
        snapshot = TokenMarketSnapshot(
            snapshot_id="snap-2",
            chain="base",
            token_address="0xtoken",
            token_symbol="ABC",
            captured_at=self.now,
            price_usd=1.0,
            liquidity_usd=100000.0,
            volume_24h_usd=300000.0,
            holders_count=1000,
        )

        with self.assertRaises(ValueError):
            extract_token_detection_features(self.build_valid_cohort(), snapshot)

    def test_output_is_stable_for_member_order(self) -> None:
        cohort = self.build_valid_cohort()
        reordered = type(cohort)(
            cohort_id=cohort.cohort_id,
            chain=cohort.chain,
            token_address=cohort.token_address,
            token_symbol=cohort.token_symbol,
            window_start=cohort.window_start,
            window_end=cohort.window_end,
            fresh_ratio=cohort.fresh_ratio,
            funding_window_min=cohort.funding_window_min,
            buy_window_min=cohort.buy_window_min,
            members=tuple(reversed(cohort.members)),
            source_cluster=cohort.source_cluster,
        )

        original = extract_token_detection_features(cohort, self.make_snapshot())
        reordered_result = extract_token_detection_features(reordered, self.make_snapshot())

        self.assertEqual(original, reordered_result)


if __name__ == "__main__":
    unittest.main()
