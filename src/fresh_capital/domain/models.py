"""Core domain models for the Fresh Capital Flow Strategy MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fresh_capital.domain.enums import (
    AlertType,
    ServiceType,
    Severity,
    SourceType,
    TokenLifecycleState,
    TradeSide,
)
from fresh_capital.domain.validation import (
    ensure_enum_member,
    ensure_non_negative_number,
    ensure_percentage,
    ensure_timestamp_order,
)


def _ensure_tuple_strings(name: str, values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) or not value for value in result):
        raise ValueError(f"{name} must contain non-empty strings")
    return result


@dataclass(frozen=True, slots=True)
class AddressRecord:
    address: str
    chain: str
    first_seen_at: datetime
    last_seen_at: datetime
    address_age_days: int
    previous_tx_count: int
    distinct_tokens_before_window: int
    service_type: ServiceType = ServiceType.NONE
    is_contract: bool = False
    labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ensure_timestamp_order("first_seen_at", self.first_seen_at, "last_seen_at", self.last_seen_at)
        ensure_non_negative_number("address_age_days", self.address_age_days)
        ensure_non_negative_number("previous_tx_count", self.previous_tx_count)
        ensure_non_negative_number(
            "distinct_tokens_before_window",
            self.distinct_tokens_before_window,
        )
        object.__setattr__(self, "service_type", ensure_enum_member("service_type", self.service_type, ServiceType))
        object.__setattr__(self, "labels", _ensure_tuple_strings("labels", self.labels))


@dataclass(frozen=True, slots=True)
class FundingEvent:
    event_id: str
    address: str
    chain: str
    funded_at: datetime
    source_address: str
    source_type: SourceType
    asset_symbol: str
    amount: float
    amount_usd: float
    tx_hash: str
    asset_address: str | None = None
    block_number: int | None = None

    def __post_init__(self) -> None:
        ensure_non_negative_number("amount", self.amount)
        ensure_non_negative_number("amount_usd", self.amount_usd)
        object.__setattr__(self, "source_type", ensure_enum_member("source_type", self.source_type, SourceType))
        if self.block_number is not None:
            ensure_non_negative_number("block_number", self.block_number)


@dataclass(frozen=True, slots=True)
class TokenTrade:
    trade_id: str
    address: str
    chain: str
    token_address: str
    token_symbol: str
    side: TradeSide
    traded_at: datetime
    quantity: float
    notional_usd: float
    price_usd: float
    tx_hash: str
    dex: str
    router_family: str | None = None
    counterparty_address: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", ensure_enum_member("side", self.side, TradeSide))
        ensure_non_negative_number("quantity", self.quantity)
        ensure_non_negative_number("notional_usd", self.notional_usd)
        ensure_non_negative_number("price_usd", self.price_usd)


@dataclass(frozen=True, slots=True)
class TokenMarketSnapshot:
    snapshot_id: str
    chain: str
    token_address: str
    token_symbol: str
    captured_at: datetime
    price_usd: float
    liquidity_usd: float
    volume_24h_usd: float
    holders_count: int
    market_cap_usd: float | None = None
    is_shortable: bool = False
    short_liquidity_usd: float | None = None

    def __post_init__(self) -> None:
        ensure_non_negative_number("price_usd", self.price_usd)
        ensure_non_negative_number("liquidity_usd", self.liquidity_usd)
        ensure_non_negative_number("volume_24h_usd", self.volume_24h_usd)
        ensure_non_negative_number("holders_count", self.holders_count)
        if self.market_cap_usd is not None:
            ensure_non_negative_number("market_cap_usd", self.market_cap_usd)
        if self.short_liquidity_usd is not None:
            ensure_non_negative_number("short_liquidity_usd", self.short_liquidity_usd)


@dataclass(frozen=True, slots=True)
class CohortMember:
    address: str
    is_fresh: bool
    allocation_usd: float
    source_type: SourceType = SourceType.UNKNOWN
    funded_at: datetime | None = None
    first_buy_at: datetime | None = None
    similarity_signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ensure_non_negative_number("allocation_usd", self.allocation_usd)
        object.__setattr__(self, "source_type", ensure_enum_member("source_type", self.source_type, SourceType))
        object.__setattr__(
            self,
            "similarity_signals",
            _ensure_tuple_strings("similarity_signals", self.similarity_signals),
        )
        if self.funded_at is not None and self.first_buy_at is not None:
            ensure_timestamp_order("funded_at", self.funded_at, "first_buy_at", self.first_buy_at)


@dataclass(frozen=True, slots=True)
class Cohort:
    cohort_id: str
    chain: str
    token_address: str
    token_symbol: str
    window_start: datetime
    window_end: datetime
    fresh_ratio: float
    funding_window_min: int
    buy_window_min: int
    members: tuple[CohortMember, ...] = field(default_factory=tuple)
    source_cluster: str | None = None

    def __post_init__(self) -> None:
        ensure_timestamp_order("window_start", self.window_start, "window_end", self.window_end)
        ensure_percentage("fresh_ratio", self.fresh_ratio)
        ensure_non_negative_number("funding_window_min", self.funding_window_min)
        ensure_non_negative_number("buy_window_min", self.buy_window_min)
        members = tuple(self.members)
        if not members:
            raise ValueError("members must not be empty")
        object.__setattr__(self, "members", members)

    @property
    def member_count(self) -> int:
        return len(self.members)


@dataclass(frozen=True, slots=True)
class CohortTokenPosition:
    cohort_id: str
    address: str
    chain: str
    token_address: str
    token_symbol: str
    quantity_bought: float
    quantity_sold: float
    net_quantity: float
    avg_entry_price_usd: float
    net_usd: float
    last_updated_at: datetime
    avg_exit_price_usd: float | None = None
    sell_back_pct: float = 0.0

    def __post_init__(self) -> None:
        ensure_non_negative_number("quantity_bought", self.quantity_bought)
        ensure_non_negative_number("quantity_sold", self.quantity_sold)
        ensure_non_negative_number("avg_entry_price_usd", self.avg_entry_price_usd)
        ensure_non_negative_number("net_usd", self.net_usd)
        ensure_percentage("sell_back_pct", self.sell_back_pct)
        if self.avg_exit_price_usd is not None:
            ensure_non_negative_number("avg_exit_price_usd", self.avg_exit_price_usd)


@dataclass(frozen=True, slots=True)
class TokenDetectionFeatures:
    token_address: str
    token_symbol: str
    chain: str
    window_start: datetime
    window_end: datetime
    state: TokenLifecycleState
    fresh_count: int
    cohort_count: int
    coordinated_buyers: int
    funding_usd: float
    token_concentration: float
    net_buy_usd: float
    buy_sell_ratio: float
    sell_back_pct: float
    exchange_outflow_usd: float
    liquidity_usd: float
    volume_24h_usd: float
    service_noise_score: float
    sync_buy_spread_min: int
    acc_score: float | None = None
    price_change_pct: float | None = None
    volume_multiple: float | None = None
    holders_growth_pct: float | None = None
    cohort_balance_drop_pct: float | None = None
    reducers_ratio: float | None = None
    aggregate_balance_drop_pct: float | None = None
    sell_buy_ratio: float | None = None
    weak_price_context: bool | None = None
    dist_score: float | None = None
    anti_noise_blocked: bool = False

    def __post_init__(self) -> None:
        ensure_timestamp_order("window_start", self.window_start, "window_end", self.window_end)
        object.__setattr__(self, "state", ensure_enum_member("state", self.state, TokenLifecycleState))
        ensure_non_negative_number("fresh_count", self.fresh_count)
        ensure_non_negative_number("cohort_count", self.cohort_count)
        ensure_non_negative_number("coordinated_buyers", self.coordinated_buyers)
        ensure_non_negative_number("funding_usd", self.funding_usd)
        ensure_percentage("token_concentration", self.token_concentration)
        ensure_non_negative_number("net_buy_usd", self.net_buy_usd)
        ensure_non_negative_number("buy_sell_ratio", self.buy_sell_ratio)
        ensure_percentage("sell_back_pct", self.sell_back_pct)
        ensure_non_negative_number("exchange_outflow_usd", self.exchange_outflow_usd)
        ensure_non_negative_number("liquidity_usd", self.liquidity_usd)
        ensure_non_negative_number("volume_24h_usd", self.volume_24h_usd)
        ensure_percentage("service_noise_score", self.service_noise_score)
        ensure_non_negative_number("sync_buy_spread_min", self.sync_buy_spread_min)
        if self.acc_score is not None:
            ensure_non_negative_number("acc_score", self.acc_score)
        if self.price_change_pct is not None:
            ensure_percentage("price_change_pct", self.price_change_pct)
        if self.volume_multiple is not None:
            ensure_non_negative_number("volume_multiple", self.volume_multiple)
        if self.holders_growth_pct is not None:
            ensure_percentage("holders_growth_pct", self.holders_growth_pct)
        if self.cohort_balance_drop_pct is not None:
            ensure_percentage("cohort_balance_drop_pct", self.cohort_balance_drop_pct)
        if self.reducers_ratio is not None:
            ensure_percentage("reducers_ratio", self.reducers_ratio)
        if self.aggregate_balance_drop_pct is not None:
            ensure_percentage("aggregate_balance_drop_pct", self.aggregate_balance_drop_pct)
        if self.sell_buy_ratio is not None:
            ensure_non_negative_number("sell_buy_ratio", self.sell_buy_ratio)
        if self.dist_score is not None:
            ensure_non_negative_number("dist_score", self.dist_score)


@dataclass(frozen=True, slots=True)
class AlertRecord:
    alert_id: str
    token: str
    chain: str
    alert_type: AlertType
    severity: Severity
    score: float
    window_start: datetime
    window_end: datetime
    dedup_key: str
    payload_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    sent: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "alert_type", ensure_enum_member("alert_type", self.alert_type, AlertType))
        object.__setattr__(self, "severity", ensure_enum_member("severity", self.severity, Severity))
        ensure_non_negative_number("score", self.score)
        ensure_timestamp_order("window_start", self.window_start, "window_end", self.window_end)
        ensure_timestamp_order("created_at", self.created_at, "updated_at", self.updated_at)
        object.__setattr__(self, "payload_json", dict(self.payload_json))


@dataclass(frozen=True, slots=True)
class TokenStateRecord:
    token: str
    chain: str
    state: TokenLifecycleState
    first_seen_at: datetime
    state_changed_at: datetime
    active_alert_id: str | None = None
    invalidated_at: datetime | None = None
    last_features_window_end: datetime | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", ensure_enum_member("state", self.state, TokenLifecycleState))
        ensure_timestamp_order("first_seen_at", self.first_seen_at, "state_changed_at", self.state_changed_at)
        if self.last_features_window_end is not None:
            ensure_timestamp_order(
                "first_seen_at",
                self.first_seen_at,
                "last_features_window_end",
                self.last_features_window_end,
            )
        if self.invalidated_at is not None:
            ensure_timestamp_order("state_changed_at", self.state_changed_at, "invalidated_at", self.invalidated_at)
        object.__setattr__(self, "metadata_json", dict(self.metadata_json))
