"""Fresh address classification using deterministic MVP rules."""

from __future__ import annotations

from dataclasses import dataclass

from fresh_capital.config.thresholds import FreshAddressThresholds, MVP_THRESHOLDS
from fresh_capital.domain.enums import ServiceType
from fresh_capital.domain.models import AddressRecord


BLOCKED_SERVICE_TYPES = frozenset(
    {
        ServiceType.EXCHANGE,
        ServiceType.BRIDGE,
        ServiceType.ROUTER,
        ServiceType.TREASURY,
        ServiceType.SERVICE,
    }
)


@dataclass(frozen=True, slots=True)
class FreshAddressMetrics:
    address_age_days: int
    previous_tx_count: int
    distinct_tokens_before_window: int
    service_type: ServiceType


@dataclass(frozen=True, slots=True)
class FreshAddressClassification:
    is_fresh: bool
    reject_reasons: tuple[str, ...]
    metrics: FreshAddressMetrics


def classify_fresh_address(
    address: AddressRecord,
    thresholds: FreshAddressThresholds = MVP_THRESHOLDS.fresh_address,
) -> FreshAddressClassification:
    """Classify an address record using explicit MVP freshness rules."""
    if not isinstance(address, AddressRecord):
        raise TypeError("address must be an AddressRecord")
    if not isinstance(thresholds, FreshAddressThresholds):
        raise TypeError("thresholds must be a FreshAddressThresholds instance")

    metrics = FreshAddressMetrics(
        address_age_days=address.address_age_days,
        previous_tx_count=address.previous_tx_count,
        distinct_tokens_before_window=address.distinct_tokens_before_window,
        service_type=address.service_type,
    )

    reject_reasons: list[str] = []
    if metrics.address_age_days > thresholds.max_age_days:
        reject_reasons.append("address_age_days_exceeds_max")
    if metrics.previous_tx_count > thresholds.max_previous_tx_count:
        reject_reasons.append("previous_tx_count_exceeds_max")
    if metrics.distinct_tokens_before_window > thresholds.max_distinct_tokens_before_window:
        reject_reasons.append("distinct_tokens_before_window_exceeds_max")
    if metrics.service_type in BLOCKED_SERVICE_TYPES:
        reject_reasons.append("service_type_blocked")

    return FreshAddressClassification(
        is_fresh=not reject_reasons,
        reject_reasons=tuple(reject_reasons),
        metrics=metrics,
    )
