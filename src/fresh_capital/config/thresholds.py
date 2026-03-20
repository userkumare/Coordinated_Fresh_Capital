"""MVP threshold configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FreshAddressThresholds:
    max_age_days: int = 30
    max_previous_tx_count: int = 20
    max_distinct_tokens_before_window: int = 10


@dataclass(frozen=True, slots=True)
class CohortThresholds:
    min_size: int = 3
    min_fresh_ratio: float = 0.5
    funding_window_min: int = 180
    buy_window_min: int = 240
    size_similarity_pct: float = 0.35


@dataclass(frozen=True, slots=True)
class AccumulationThresholds:
    min_cohort_funding_usd: float = 25000.0
    min_buyers: int = 3
    max_sync_buy_spread_min: int = 240
    min_token_concentration: float = 0.45
    min_buy_sell_ratio: float = 2.5
    max_sell_back_pct: float = 0.15
    min_liquidity_usd: float = 150000.0
    min_volume_24h_usd: float = 300000.0
    max_slippage_test: float = 0.02
    score_threshold: float = 70.0


@dataclass(frozen=True, slots=True)
class ConfirmationThresholds:
    price_confirm_pct: float = 0.08
    volume_confirm_multiple: float = 1.8
    holders_growth_pct: float = 0.05
    max_cohort_balance_drop_pct: float = 0.10
    min_conditions_required: int = 2
    min_window_hours: int = 1
    max_window_hours: int = 24


@dataclass(frozen=True, slots=True)
class DistributionThresholds:
    min_reducers_ratio: float = 0.30
    min_balance_drop_pct: float = 0.12
    min_exchange_outflow_usd: float = 20000.0
    min_sell_buy_ratio: float = 1.25
    score_threshold: float = 65.0


@dataclass(frozen=True, slots=True)
class ShortWatchThresholds:
    min_dist_score: float = 75.0


@dataclass(frozen=True, slots=True)
class MVPThresholds:
    fresh_address: FreshAddressThresholds = FreshAddressThresholds()
    cohort: CohortThresholds = CohortThresholds()
    accumulation: AccumulationThresholds = AccumulationThresholds()
    confirmation: ConfirmationThresholds = ConfirmationThresholds()
    distribution: DistributionThresholds = DistributionThresholds()
    short_watch: ShortWatchThresholds = ShortWatchThresholds()


MVP_THRESHOLDS = MVPThresholds()
