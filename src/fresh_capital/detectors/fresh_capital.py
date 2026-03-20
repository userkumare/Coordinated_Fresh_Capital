"""Minimal deterministic decision engine for fresh capital detection."""

from __future__ import annotations

from dataclasses import dataclass

from fresh_capital.config.thresholds import AccumulationThresholds, CohortThresholds, MVP_THRESHOLDS
from fresh_capital.domain.enums import Severity
from fresh_capital.extractors.token_features import TokenFeatureExtractionResult


@dataclass(frozen=True, slots=True)
class FreshCapitalDecisionMetrics:
    fresh_participant_count: int
    total_fresh_capital_usd: float
    top_participant_share: float | None
    liquidity_relative_funding_ratio: float | None
    market_cap_relative_funding_ratio: float | None
    cohort_timing_span_minutes: float | None
    min_required_participants: int
    min_required_fresh_capital_usd: float
    max_allowed_top_participant_share: float
    min_required_liquidity_relative_funding_ratio: float
    max_allowed_cohort_timing_span_minutes: int


@dataclass(frozen=True, slots=True)
class FreshCapitalDecisionResult:
    is_detected: bool
    reject_reasons: tuple[str, ...]
    triggered_rules: tuple[str, ...]
    severity: Severity
    metrics: FreshCapitalDecisionMetrics
    unavailable_metrics: tuple[str, ...]
    skipped_rules: tuple[str, ...]


def detect_fresh_capital_flow(
    feature_result: TokenFeatureExtractionResult,
    cohort_thresholds: CohortThresholds = MVP_THRESHOLDS.cohort,
    accumulation_thresholds: AccumulationThresholds = MVP_THRESHOLDS.accumulation,
) -> FreshCapitalDecisionResult:
    """Evaluate minimal deterministic fresh-capital detection rules."""
    if not isinstance(feature_result, TokenFeatureExtractionResult):
        raise TypeError("feature_result must be a TokenFeatureExtractionResult")
    if not isinstance(cohort_thresholds, CohortThresholds):
        raise TypeError("cohort_thresholds must be a CohortThresholds instance")
    if not isinstance(accumulation_thresholds, AccumulationThresholds):
        raise TypeError("accumulation_thresholds must be an AccumulationThresholds instance")

    liquidity_ratio_threshold = (
        accumulation_thresholds.min_cohort_funding_usd / accumulation_thresholds.min_liquidity_usd
    )
    metrics = FreshCapitalDecisionMetrics(
        fresh_participant_count=feature_result.metrics.fresh_participant_count,
        total_fresh_capital_usd=feature_result.metrics.total_fresh_capital_usd,
        top_participant_share=feature_result.metrics.top_participant_share,
        liquidity_relative_funding_ratio=feature_result.metrics.liquidity_relative_funding_ratio,
        market_cap_relative_funding_ratio=feature_result.metrics.market_cap_relative_funding_ratio,
        cohort_timing_span_minutes=feature_result.metrics.cohort_timing_span_minutes,
        min_required_participants=cohort_thresholds.min_size,
        min_required_fresh_capital_usd=accumulation_thresholds.min_cohort_funding_usd,
        max_allowed_top_participant_share=accumulation_thresholds.max_top_participant_share,
        min_required_liquidity_relative_funding_ratio=liquidity_ratio_threshold,
        max_allowed_cohort_timing_span_minutes=accumulation_thresholds.max_sync_buy_spread_min,
    )

    unavailable_metrics = tuple(sorted(set(feature_result.unavailable_fields)))
    skipped_rules: list[str] = []
    triggered_rules: list[str] = []
    reject_reasons: list[str] = []

    if metrics.fresh_participant_count >= cohort_thresholds.min_size:
        triggered_rules.append("valid_cohort_present")
        triggered_rules.append("minimum_participant_count_passed")
    else:
        reject_reasons.append("insufficient_fresh_participant_count")

    if metrics.total_fresh_capital_usd >= accumulation_thresholds.min_cohort_funding_usd:
        triggered_rules.append("minimum_aggregate_fresh_capital_passed")
    else:
        reject_reasons.append("insufficient_aggregate_fresh_capital")

    if metrics.top_participant_share is None:
        skipped_rules.append("top_participant_concentration_unavailable")
    elif metrics.top_participant_share <= accumulation_thresholds.max_top_participant_share:
        triggered_rules.append("concentration_guardrail_passed")
    else:
        reject_reasons.append("excessive_top_participant_concentration")

    if metrics.liquidity_relative_funding_ratio is None:
        skipped_rules.append("liquidity_relative_funding_ratio_unavailable")
    elif metrics.liquidity_relative_funding_ratio >= liquidity_ratio_threshold:
        triggered_rules.append("liquidity_relative_funding_ratio_passed")
    else:
        reject_reasons.append("insufficient_liquidity_relative_funding_ratio")

    if metrics.market_cap_relative_funding_ratio is None:
        skipped_rules.append("market_cap_relative_funding_ratio_unavailable_or_unsupported")
    else:
        skipped_rules.append("market_cap_relative_funding_ratio_threshold_unsupported")

    if metrics.cohort_timing_span_minutes is None:
        skipped_rules.append("cohort_timing_span_unavailable")
    elif metrics.cohort_timing_span_minutes <= accumulation_thresholds.max_sync_buy_spread_min:
        triggered_rules.append("cohort_timing_span_passed")
    else:
        reject_reasons.append("excessive_cohort_timing_span")

    is_detected = not reject_reasons
    return FreshCapitalDecisionResult(
        is_detected=is_detected,
        reject_reasons=tuple(reject_reasons),
        triggered_rules=tuple(triggered_rules),
        severity=_determine_severity(is_detected, triggered_rules),
        metrics=metrics,
        unavailable_metrics=unavailable_metrics,
        skipped_rules=tuple(skipped_rules),
    )


def _determine_severity(is_detected: bool, triggered_rules: list[str]) -> Severity:
    if not is_detected:
        return Severity.LOW
    if len(triggered_rules) >= 5:
        return Severity.HIGH
    return Severity.MEDIUM
