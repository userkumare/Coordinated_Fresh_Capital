"""Minimal deterministic token detection feature extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fresh_capital.domain.models import Cohort, TokenMarketSnapshot


@dataclass(frozen=True, slots=True)
class TokenFeatureMetrics:
    fresh_participant_count: int
    total_fresh_capital_usd: float
    average_capital_per_fresh_participant_usd: float
    top_participant_share: float | None
    top_2_participant_concentration_ratio: float | None
    cohort_timing_span_minutes: float | None
    cohort_age_to_snapshot_minutes: float | None
    market_cap_relative_funding_ratio: float | None
    liquidity_relative_funding_ratio: float | None


@dataclass(frozen=True, slots=True)
class TokenFeatureExtractionResult:
    metrics: TokenFeatureMetrics
    unavailable_fields: tuple[str, ...]


def extract_token_detection_features(
    cohort: Cohort,
    market_snapshot: TokenMarketSnapshot,
) -> TokenFeatureExtractionResult:
    """Extract deterministic token-level metrics from a valid cohort and market snapshot."""
    if not isinstance(cohort, Cohort):
        raise TypeError("cohort must be a Cohort")
    if not isinstance(market_snapshot, TokenMarketSnapshot):
        raise TypeError("market_snapshot must be a TokenMarketSnapshot")
    if cohort.chain != market_snapshot.chain:
        raise ValueError("cohort chain must match market snapshot chain")
    if cohort.token_address != market_snapshot.token_address:
        raise ValueError("cohort token_address must match market snapshot token_address")

    members = tuple(sorted(cohort.members, key=lambda member: member.address))
    allocations = tuple(member.allocation_usd for member in members)
    fresh_participant_count = len(members)
    total_fresh_capital_usd = sum(allocations)
    average_capital_per_fresh_participant_usd = (
        total_fresh_capital_usd / fresh_participant_count if fresh_participant_count else 0.0
    )

    unavailable_fields: list[str] = []
    top_participant_share = _compute_share(max(allocations) if allocations else None, total_fresh_capital_usd)
    if top_participant_share is None:
        unavailable_fields.append("top_participant_share")

    top_2_participant_concentration_ratio = _compute_share(sum(sorted(allocations, reverse=True)[:2]), total_fresh_capital_usd)
    if top_2_participant_concentration_ratio is None:
        unavailable_fields.append("top_2_participant_concentration_ratio")

    cohort_timing_span_minutes = _compute_minutes_between(cohort.window_start, cohort.window_end)
    if cohort_timing_span_minutes is None:
        unavailable_fields.append("cohort_timing_span_minutes")

    cohort_age_to_snapshot_minutes = _compute_minutes_between(cohort.window_end, market_snapshot.captured_at)
    if cohort_age_to_snapshot_minutes is None:
        unavailable_fields.append("cohort_age_to_snapshot_minutes")

    market_cap_relative_funding_ratio = _compute_share(total_fresh_capital_usd, market_snapshot.market_cap_usd)
    if market_cap_relative_funding_ratio is None:
        unavailable_fields.append("market_cap_relative_funding_ratio")

    liquidity_relative_funding_ratio = _compute_share(total_fresh_capital_usd, market_snapshot.liquidity_usd)
    if liquidity_relative_funding_ratio is None:
        unavailable_fields.append("liquidity_relative_funding_ratio")

    return TokenFeatureExtractionResult(
        metrics=TokenFeatureMetrics(
            fresh_participant_count=fresh_participant_count,
            total_fresh_capital_usd=total_fresh_capital_usd,
            average_capital_per_fresh_participant_usd=average_capital_per_fresh_participant_usd,
            top_participant_share=top_participant_share,
            top_2_participant_concentration_ratio=top_2_participant_concentration_ratio,
            cohort_timing_span_minutes=cohort_timing_span_minutes,
            cohort_age_to_snapshot_minutes=cohort_age_to_snapshot_minutes,
            market_cap_relative_funding_ratio=market_cap_relative_funding_ratio,
            liquidity_relative_funding_ratio=liquidity_relative_funding_ratio,
        ),
        unavailable_fields=tuple(unavailable_fields),
    )


def _compute_share(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _compute_minutes_between(earlier: datetime | None, later: datetime | None) -> float | None:
    if earlier is None or later is None:
        return None
    return (later - earlier).total_seconds() / 60.0
