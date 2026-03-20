"""Minimal deterministic alert record builder for fresh capital detections."""

from __future__ import annotations

from dataclasses import dataclass

from fresh_capital.detectors.fresh_capital import FreshCapitalDecisionResult
from fresh_capital.domain.enums import AlertType, Severity
from fresh_capital.domain.models import AlertRecord, Cohort
from fresh_capital.extractors.token_features import TokenFeatureExtractionResult


SEVERITY_MAP = {
    Severity.LOW: Severity.LOW,
    Severity.MEDIUM: Severity.MEDIUM,
    Severity.HIGH: Severity.HIGH,
    Severity.CRITICAL: Severity.CRITICAL,
}
MAX_TRIGGERED_RULE_COUNT = 6


@dataclass(frozen=True, slots=True)
class AlertBuildSummary:
    token: str
    chain: str
    alert_type: AlertType
    severity: Severity
    score: float
    triggered_rule_count: int
    unavailable_context_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlertBuildResult:
    is_alert_built: bool
    reject_reasons: tuple[str, ...]
    alert_record: AlertRecord | None
    summary: AlertBuildSummary | None


def build_fresh_capital_alert(
    decision_result: FreshCapitalDecisionResult,
    cohort: Cohort,
    feature_result: TokenFeatureExtractionResult,
) -> AlertBuildResult:
    """Build an alert record for a positive fresh-capital detection."""
    if not isinstance(decision_result, FreshCapitalDecisionResult):
        raise TypeError("decision_result must be a FreshCapitalDecisionResult")
    if not isinstance(cohort, Cohort):
        raise TypeError("cohort must be a Cohort")
    if not isinstance(feature_result, TokenFeatureExtractionResult):
        raise TypeError("feature_result must be a TokenFeatureExtractionResult")

    reject_reasons: list[str] = []
    if not decision_result.is_detected:
        reject_reasons.append("detection_not_positive")
    if decision_result.metrics.fresh_participant_count != feature_result.metrics.fresh_participant_count:
        reject_reasons.append("feature_decision_participant_count_mismatch")
    if decision_result.metrics.total_fresh_capital_usd != feature_result.metrics.total_fresh_capital_usd:
        reject_reasons.append("feature_decision_funding_mismatch")
    if not cohort.token_address:
        reject_reasons.append("missing_token_identifier")

    if reject_reasons:
        return AlertBuildResult(
            is_alert_built=False,
            reject_reasons=tuple(reject_reasons),
            alert_record=None,
            summary=None,
        )

    alert_type = AlertType.FRESH_ACCUMULATION
    alert_severity = SEVERITY_MAP[decision_result.severity]
    score = _compute_alert_score(len(decision_result.triggered_rules))
    unavailable_context_fields = tuple(sorted(set(feature_result.unavailable_fields + decision_result.unavailable_metrics)))
    summary = AlertBuildSummary(
        token=cohort.token_address,
        chain=cohort.chain,
        alert_type=alert_type,
        severity=alert_severity,
        score=score,
        triggered_rule_count=len(decision_result.triggered_rules),
        unavailable_context_fields=unavailable_context_fields,
    )

    dedup_key = f"{cohort.chain}:{cohort.token_address}:{alert_type.value}"
    alert_record = AlertRecord(
        alert_id=f"{dedup_key}:{cohort.window_end.isoformat()}",
        token=cohort.token_address,
        chain=cohort.chain,
        alert_type=alert_type,
        severity=alert_severity,
        score=score,
        window_start=cohort.window_start,
        window_end=cohort.window_end,
        dedup_key=dedup_key,
        payload_json={
            "token_symbol": cohort.token_symbol,
            "fresh_participant_count": decision_result.metrics.fresh_participant_count,
            "total_fresh_capital_usd": decision_result.metrics.total_fresh_capital_usd,
            "top_participant_share": decision_result.metrics.top_participant_share,
            "liquidity_relative_funding_ratio": decision_result.metrics.liquidity_relative_funding_ratio,
            "market_cap_relative_funding_ratio": decision_result.metrics.market_cap_relative_funding_ratio,
            "cohort_timing_span_minutes": decision_result.metrics.cohort_timing_span_minutes,
            "triggered_rules": list(decision_result.triggered_rules),
            "skipped_rules": list(decision_result.skipped_rules),
            "unavailable_metrics": list(decision_result.unavailable_metrics),
        },
        created_at=cohort.window_end,
        updated_at=cohort.window_end,
    )
    return AlertBuildResult(
        is_alert_built=True,
        reject_reasons=(),
        alert_record=alert_record,
        summary=summary,
    )


def _compute_alert_score(triggered_rule_count: int) -> float:
    bounded_rule_count = min(max(triggered_rule_count, 0), MAX_TRIGGERED_RULE_COUNT)
    return (bounded_rule_count / MAX_TRIGGERED_RULE_COUNT) * 100.0
