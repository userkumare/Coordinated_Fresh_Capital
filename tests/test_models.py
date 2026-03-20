"""Tests for core domain model construction."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fresh_capital.domain.enums import AlertType, Severity, SourceType, TokenLifecycleState, TradeSide
from fresh_capital.domain.models import (
    AddressRecord,
    AlertRecord,
    Cohort,
    CohortMember,
    CohortTokenPosition,
    FundingEvent,
    TokenDetectionFeatures,
    TokenMarketSnapshot,
    TokenStateRecord,
    TokenTrade,
)


class ModelConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

    def test_models_construct_with_valid_input(self) -> None:
        address = AddressRecord(
            address="0xabc",
            chain="ethereum",
            first_seen_at=self.now - timedelta(days=7),
            last_seen_at=self.now,
            address_age_days=7,
            previous_tx_count=4,
            distinct_tokens_before_window=2,
            labels=("fresh",),
        )
        funding = FundingEvent(
            event_id="fund-1",
            address=address.address,
            chain="ethereum",
            funded_at=self.now - timedelta(hours=5),
            source_address="0xfunder",
            source_type=SourceType.EXCHANGE,
            asset_symbol="USDC",
            amount=15000.0,
            amount_usd=15000.0,
            tx_hash="0xtx1",
        )
        trade = TokenTrade(
            trade_id="trade-1",
            address=address.address,
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            side=TradeSide.BUY,
            traded_at=self.now - timedelta(hours=4),
            quantity=1000.0,
            notional_usd=14000.0,
            price_usd=14.0,
            tx_hash="0xtx2",
            dex="uniswap",
        )
        snapshot = TokenMarketSnapshot(
            snapshot_id="snap-1",
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            captured_at=self.now,
            price_usd=14.5,
            liquidity_usd=200000.0,
            volume_24h_usd=400000.0,
            holders_count=4200,
            is_shortable=True,
            short_liquidity_usd=50000.0,
        )
        member = CohortMember(
            address=address.address,
            is_fresh=True,
            allocation_usd=14000.0,
            source_type=SourceType.EXCHANGE,
            funded_at=funding.funded_at,
            first_buy_at=trade.traded_at,
            similarity_signals=("funding_window", "buy_window", "source_similarity"),
        )
        cohort = Cohort(
            cohort_id="cohort-1",
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            window_start=self.now - timedelta(hours=6),
            window_end=self.now,
            fresh_ratio=1.0,
            funding_window_min=180,
            buy_window_min=240,
            members=(member,),
        )
        position = CohortTokenPosition(
            cohort_id=cohort.cohort_id,
            address=address.address,
            chain="ethereum",
            token_address="0xtoken",
            token_symbol="ABC",
            quantity_bought=1000.0,
            quantity_sold=50.0,
            net_quantity=950.0,
            avg_entry_price_usd=14.0,
            net_usd=13300.0,
            last_updated_at=self.now,
            sell_back_pct=0.05,
        )
        features = TokenDetectionFeatures(
            token_address="0xtoken",
            token_symbol="ABC",
            chain="ethereum",
            window_start=self.now - timedelta(hours=6),
            window_end=self.now,
            state=TokenLifecycleState.IDLE,
            fresh_count=3,
            cohort_count=1,
            coordinated_buyers=3,
            funding_usd=45000.0,
            token_concentration=0.6,
            net_buy_usd=42000.0,
            buy_sell_ratio=3.5,
            sell_back_pct=0.05,
            exchange_outflow_usd=0.0,
            liquidity_usd=snapshot.liquidity_usd,
            volume_24h_usd=snapshot.volume_24h_usd,
            service_noise_score=0.1,
            sync_buy_spread_min=120,
            acc_score=75.0,
        )
        alert = AlertRecord(
            alert_id="alert-1",
            token="0xtoken",
            chain="ethereum",
            alert_type=AlertType.FRESH_ACCUMULATION,
            severity=Severity.HIGH,
            score=75.0,
            window_start=features.window_start,
            window_end=features.window_end,
            dedup_key="ethereum:0xtoken:fresh_accumulation",
            payload_json={"funding_usd": features.funding_usd},
            created_at=self.now,
            updated_at=self.now,
        )
        state = TokenStateRecord(
            token="0xtoken",
            chain="ethereum",
            state=TokenLifecycleState.FRESH_ACCUMULATION,
            first_seen_at=self.now - timedelta(hours=6),
            state_changed_at=self.now,
            active_alert_id=alert.alert_id,
            last_features_window_end=features.window_end,
            metadata_json={"latest_score": alert.score},
        )

        self.assertEqual(address.address, "0xabc")
        self.assertEqual(funding.source_type, SourceType.EXCHANGE)
        self.assertEqual(trade.side, TradeSide.BUY)
        self.assertTrue(snapshot.is_shortable)
        self.assertEqual(cohort.member_count, 1)
        self.assertAlmostEqual(position.sell_back_pct, 0.05)
        self.assertEqual(features.state, TokenLifecycleState.IDLE)
        self.assertEqual(alert.severity, Severity.HIGH)
        self.assertEqual(state.active_alert_id, "alert-1")


if __name__ == "__main__":
    unittest.main()
