"""Deterministic in-process orchestration for the Fresh Capital MVP pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fresh_capital.alerts.builder import AlertBuildResult, build_fresh_capital_alert
from fresh_capital.alerts.delivery import AlertDeliveryResult, deliver_logged_alerts
from fresh_capital.alerts.handler import AlertHandlingResult, handle_alert_build_result
from fresh_capital.builders.cohort import CohortBuildParticipant, CohortBuildResult, build_fresh_cohort
from fresh_capital.classifiers.fresh_address import FreshAddressClassification, classify_fresh_address
from fresh_capital.config.thresholds import MVP_THRESHOLDS
from fresh_capital.detectors.fresh_capital import FreshCapitalDecisionResult, detect_fresh_capital_flow
from fresh_capital.domain.enums import StrEnum
from fresh_capital.domain.models import AddressRecord, FundingEvent, TokenMarketSnapshot
from fresh_capital.extractors.token_features import TokenFeatureExtractionResult, extract_token_detection_features


class PipelineStageStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PipelineParticipantInput:
    address: AddressRecord
    funding_event: FundingEvent


@dataclass(frozen=True, slots=True)
class PipelineParticipantClassificationResult:
    participant: PipelineParticipantInput
    classification: FreshAddressClassification

    @property
    def is_fresh(self) -> bool:
        return self.classification.is_fresh


@dataclass(frozen=True, slots=True)
class PipelineStageTrace:
    stage_name: str
    stage_status: PipelineStageStatus
    stage_skipped: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class FreshCapitalPipelineRequest:
    participants: tuple[PipelineParticipantInput, ...] | list[PipelineParticipantInput]
    market_snapshot: TokenMarketSnapshot
    alert_log_path: str | Path | None = None
    delivery_database_path: str | Path | None = None
    delivery_status_log_path: str | Path | None = None
    delivery_fail_alert_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FreshCapitalPipelineResult:
    stage_traces: tuple[PipelineStageTrace, ...]
    participant_classifications: tuple[PipelineParticipantClassificationResult, ...]
    cohort_result: CohortBuildResult | None
    feature_result: TokenFeatureExtractionResult | None
    detection_result: FreshCapitalDecisionResult | None
    alert_build_result: AlertBuildResult | None
    alert_handling_result: AlertHandlingResult | None
    delivery_results: tuple[AlertDeliveryResult, ...] | None


def run_fresh_capital_pipeline(
    request: FreshCapitalPipelineRequest,
) -> FreshCapitalPipelineResult:
    """Run the deterministic MVP pipeline end to end in-process."""
    if not isinstance(request, FreshCapitalPipelineRequest):
        raise TypeError("request must be a FreshCapitalPipelineRequest")
    if not isinstance(request.market_snapshot, TokenMarketSnapshot):
        raise TypeError("market_snapshot must be a TokenMarketSnapshot")

    participants = _normalize_participants(request.participants)
    if not participants:
        raise ValueError("participants must not be empty")

    stage_traces: list[PipelineStageTrace] = []

    participant_classifications = tuple(
        PipelineParticipantClassificationResult(
            participant=participant,
            classification=classify_fresh_address(participant.address, MVP_THRESHOLDS.fresh_address),
        )
        for participant in participants
    )
    stage_traces.append(_completed_stage("participant_classification"))

    cohort_participants = tuple(
        CohortBuildParticipant(
            address=item.participant.address,
            fresh_classification=item.classification,
            funding_event=item.participant.funding_event,
        )
        for item in participant_classifications
    )
    cohort_result = build_fresh_cohort(
        request.market_snapshot.chain,
        request.market_snapshot.token_address,
        request.market_snapshot.token_symbol,
        cohort_participants,
        MVP_THRESHOLDS.cohort,
        MVP_THRESHOLDS.accumulation,
    )
    if cohort_result.is_valid_cohort:
        stage_traces.append(_completed_stage("cohort_build"))
    else:
        stage_traces.append(
            _failed_stage(
                "cohort_build",
                reason=";".join(cohort_result.reject_reasons),
            )
        )
        stage_traces.extend(
            _skipped_stages(("feature_extraction", "detection", "alert_build", "alert_handling", "delivery"))
        )
        return FreshCapitalPipelineResult(
            stage_traces=tuple(stage_traces),
            participant_classifications=participant_classifications,
            cohort_result=cohort_result,
            feature_result=None,
            detection_result=None,
            alert_build_result=None,
            alert_handling_result=None,
            delivery_results=None,
        )

    assert cohort_result.cohort is not None
    feature_result = extract_token_detection_features(cohort_result.cohort, request.market_snapshot)
    stage_traces.append(_completed_stage("feature_extraction"))

    detection_result = detect_fresh_capital_flow(
        feature_result,
        MVP_THRESHOLDS.cohort,
        MVP_THRESHOLDS.accumulation,
    )
    if detection_result.is_detected:
        stage_traces.append(_completed_stage("detection"))
    else:
        stage_traces.append(
            _failed_stage(
                "detection",
                reason=";".join(detection_result.reject_reasons) or "detection_not_positive",
            )
        )
        stage_traces.extend(_skipped_stages(("alert_build", "alert_handling", "delivery")))
        return FreshCapitalPipelineResult(
            stage_traces=tuple(stage_traces),
            participant_classifications=participant_classifications,
            cohort_result=cohort_result,
            feature_result=feature_result,
            detection_result=detection_result,
            alert_build_result=None,
            alert_handling_result=None,
            delivery_results=None,
        )

    alert_build_result = build_fresh_capital_alert(detection_result, cohort_result.cohort, feature_result)
    if alert_build_result.is_alert_built:
        stage_traces.append(_completed_stage("alert_build"))
    else:
        stage_traces.append(
            _failed_stage(
                "alert_build",
                reason=";".join(alert_build_result.reject_reasons) or "alert_build_rejected",
            )
        )
        stage_traces.extend(_skipped_stages(("alert_handling", "delivery")))
        return FreshCapitalPipelineResult(
            stage_traces=tuple(stage_traces),
            participant_classifications=participant_classifications,
            cohort_result=cohort_result,
            feature_result=feature_result,
            detection_result=detection_result,
            alert_build_result=alert_build_result,
            alert_handling_result=None,
            delivery_results=None,
        )

    alert_log_path = _normalize_optional_path(request.alert_log_path, "alert_log_path")
    if alert_log_path is None:
        stage_traces.append(_skipped_stage("alert_handling", reason="alert_log_path_not_provided"))
        stage_traces.append(_skipped_stage("delivery", reason="alert_handling_not_performed"))
        return FreshCapitalPipelineResult(
            stage_traces=tuple(stage_traces),
            participant_classifications=participant_classifications,
            cohort_result=cohort_result,
            feature_result=feature_result,
            detection_result=detection_result,
            alert_build_result=alert_build_result,
            alert_handling_result=None,
            delivery_results=None,
        )

    alert_handling_result = handle_alert_build_result(alert_build_result, alert_log_path)
    stage_traces.append(_completed_stage("alert_handling"))

    database_path = _normalize_optional_path(request.delivery_database_path, "delivery_database_path")
    status_log_path = _normalize_optional_path(request.delivery_status_log_path, "delivery_status_log_path")
    if database_path is None or status_log_path is None:
        stage_traces.append(_skipped_stage("delivery", reason="delivery_paths_not_provided"))
        return FreshCapitalPipelineResult(
            stage_traces=tuple(stage_traces),
            participant_classifications=participant_classifications,
            cohort_result=cohort_result,
            feature_result=feature_result,
            detection_result=detection_result,
            alert_build_result=alert_build_result,
            alert_handling_result=alert_handling_result,
            delivery_results=None,
        )

    delivery_results = deliver_logged_alerts(
        alert_log_path,
        database_path,
        status_log_path,
        fail_alert_ids=request.delivery_fail_alert_ids,
    )
    stage_traces.append(_completed_stage("delivery"))
    return FreshCapitalPipelineResult(
        stage_traces=tuple(stage_traces),
        participant_classifications=participant_classifications,
        cohort_result=cohort_result,
        feature_result=feature_result,
        detection_result=detection_result,
        alert_build_result=alert_build_result,
        alert_handling_result=alert_handling_result,
        delivery_results=delivery_results,
    )


def _normalize_participants(
    participants: tuple[PipelineParticipantInput, ...] | list[PipelineParticipantInput],
) -> tuple[PipelineParticipantInput, ...]:
    normalized = tuple(participants)
    for participant in normalized:
        if not isinstance(participant, PipelineParticipantInput):
            raise TypeError("participants must contain PipelineParticipantInput instances")
    return normalized


def _normalize_optional_path(value: str | Path | None, name: str) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value:
        return Path(value)
    raise TypeError(f"{name} must be a non-empty string, Path, or None")


def _completed_stage(stage_name: str) -> PipelineStageTrace:
    return PipelineStageTrace(
        stage_name=stage_name,
        stage_status=PipelineStageStatus.COMPLETED,
        stage_skipped=False,
    )


def _failed_stage(stage_name: str, *, reason: str) -> PipelineStageTrace:
    return PipelineStageTrace(
        stage_name=stage_name,
        stage_status=PipelineStageStatus.FAILED,
        stage_skipped=False,
        reason=reason,
    )


def _skipped_stage(stage_name: str, *, reason: str) -> PipelineStageTrace:
    return PipelineStageTrace(
        stage_name=stage_name,
        stage_status=PipelineStageStatus.SKIPPED,
        stage_skipped=True,
        reason=reason,
    )


def _skipped_stages(stage_names: tuple[str, ...]) -> tuple[PipelineStageTrace, ...]:
    return tuple(_skipped_stage(stage_name, reason="upstream_stage_failed") for stage_name in stage_names)
