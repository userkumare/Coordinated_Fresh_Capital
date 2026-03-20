"""Minimal deterministic cohort construction for fresh participants."""

from __future__ import annotations

from dataclasses import dataclass

from fresh_capital.classifiers.fresh_address import FreshAddressClassification
from fresh_capital.config.thresholds import AccumulationThresholds, CohortThresholds, MVP_THRESHOLDS
from fresh_capital.domain.models import AddressRecord, Cohort, CohortMember, FundingEvent


@dataclass(frozen=True, slots=True)
class CohortBuildParticipant:
    address: AddressRecord
    fresh_classification: FreshAddressClassification
    funding_event: FundingEvent


@dataclass(frozen=True, slots=True)
class CohortBuildMetrics:
    unique_fresh_participant_count: int
    total_fresh_capital_usd: float
    minimum_cohort_size: int
    minimum_aggregate_capital_usd: float


@dataclass(frozen=True, slots=True)
class CohortBuildResult:
    is_valid_cohort: bool
    reject_reasons: tuple[str, ...]
    metrics: CohortBuildMetrics
    cohort: Cohort | None


def build_fresh_cohort(
    chain: str,
    token_address: str,
    token_symbol: str,
    participants: tuple[CohortBuildParticipant, ...] | list[CohortBuildParticipant],
    cohort_thresholds: CohortThresholds = MVP_THRESHOLDS.cohort,
    accumulation_thresholds: AccumulationThresholds = MVP_THRESHOLDS.accumulation,
) -> CohortBuildResult:
    """Build a minimal cohort from fresh-qualified participants for one token."""
    _ensure_non_empty_string("chain", chain)
    _ensure_non_empty_string("token_address", token_address)
    _ensure_non_empty_string("token_symbol", token_symbol)
    if not isinstance(cohort_thresholds, CohortThresholds):
        raise TypeError("cohort_thresholds must be a CohortThresholds instance")
    if not isinstance(accumulation_thresholds, AccumulationThresholds):
        raise TypeError("accumulation_thresholds must be an AccumulationThresholds instance")

    normalized_participants = tuple(participants)
    fresh_members = _collect_fresh_members(chain, normalized_participants)

    unique_fresh_participant_count = len(fresh_members)
    total_fresh_capital_usd = sum(member.allocation_usd for member in fresh_members)
    metrics = CohortBuildMetrics(
        unique_fresh_participant_count=unique_fresh_participant_count,
        total_fresh_capital_usd=total_fresh_capital_usd,
        minimum_cohort_size=cohort_thresholds.min_size,
        minimum_aggregate_capital_usd=accumulation_thresholds.min_cohort_funding_usd,
    )

    reject_reasons: list[str] = []
    if unique_fresh_participant_count < cohort_thresholds.min_size:
        reject_reasons.append("insufficient_fresh_participant_count")
    if total_fresh_capital_usd < accumulation_thresholds.min_cohort_funding_usd:
        reject_reasons.append("insufficient_aggregate_capital")

    if reject_reasons:
        return CohortBuildResult(
            is_valid_cohort=False,
            reject_reasons=tuple(reject_reasons),
            metrics=metrics,
            cohort=None,
        )

    members = tuple(sorted(fresh_members, key=lambda member: member.address))
    cohort = Cohort(
        cohort_id=_build_cohort_id(chain, token_address, members),
        chain=chain,
        token_address=token_address,
        token_symbol=token_symbol,
        window_start=min(member.funded_at for member in members if member.funded_at is not None),
        window_end=max(member.funded_at for member in members if member.funded_at is not None),
        fresh_ratio=1.0,
        funding_window_min=cohort_thresholds.funding_window_min,
        buy_window_min=cohort_thresholds.buy_window_min,
        members=members,
    )
    return CohortBuildResult(
        is_valid_cohort=True,
        reject_reasons=(),
        metrics=metrics,
        cohort=cohort,
    )


def _collect_fresh_members(
    chain: str,
    participants: tuple[CohortBuildParticipant, ...],
) -> tuple[CohortMember, ...]:
    participant_map: dict[str, CohortMember] = {}

    for participant in participants:
        if not isinstance(participant, CohortBuildParticipant):
            raise TypeError("participants must contain CohortBuildParticipant instances")
        _validate_participant(chain, participant)
        if not participant.fresh_classification.is_fresh:
            continue

        existing_member = participant_map.get(participant.address.address)
        if existing_member is None:
            participant_map[participant.address.address] = CohortMember(
                address=participant.address.address,
                is_fresh=True,
                allocation_usd=participant.funding_event.amount_usd,
                source_type=participant.funding_event.source_type,
                funded_at=participant.funding_event.funded_at,
            )
            continue

        earliest_funded_at = existing_member.funded_at
        if earliest_funded_at is None or participant.funding_event.funded_at < earliest_funded_at:
            earliest_funded_at = participant.funding_event.funded_at

        participant_map[participant.address.address] = CohortMember(
            address=existing_member.address,
            is_fresh=True,
            allocation_usd=existing_member.allocation_usd + participant.funding_event.amount_usd,
            source_type=existing_member.source_type,
            funded_at=earliest_funded_at,
        )

    return tuple(participant_map.values())


def _validate_participant(chain: str, participant: CohortBuildParticipant) -> None:
    if participant.address.address != participant.funding_event.address:
        raise ValueError("participant address and funding event address must match")
    if participant.address.chain != chain:
        raise ValueError("participant address chain must match cohort chain")
    if participant.funding_event.chain != chain:
        raise ValueError("participant funding event chain must match cohort chain")


def _build_cohort_id(chain: str, token_address: str, members: tuple[CohortMember, ...]) -> str:
    addresses = ",".join(member.address for member in members)
    return f"{chain}:{token_address}:{addresses}"


def _ensure_non_empty_string(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value
