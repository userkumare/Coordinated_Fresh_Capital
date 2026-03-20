"""Enum definitions for the Fresh Capital Flow Strategy MVP."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """A small string enum base compatible with Python 3.10+."""


class AlertType(StrEnum):
    FRESH_ACCUMULATION = "FRESH_ACCUMULATION"
    ACCUMULATION_CONFIRMED = "ACCUMULATION_CONFIRMED"
    DISTRIBUTION_STARTED = "DISTRIBUTION_STARTED"
    SHORT_WATCH = "SHORT_WATCH"
    INVALIDATION = "INVALIDATION"


class TokenLifecycleState(StrEnum):
    IDLE = "idle"
    FRESH_ACCUMULATION = "fresh_accumulation"
    ACCUMULATION_CONFIRMED = "accumulation_confirmed"
    DISTRIBUTION_STARTED = "distribution_started"
    SHORT_WATCH = "short_watch"
    INVALIDATED = "invalidated"


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class ServiceType(StrEnum):
    NONE = "none"
    EXCHANGE = "exchange"
    ROUTER = "router"
    BRIDGE = "bridge"
    TREASURY = "treasury"
    SERVICE = "service"


class SourceType(StrEnum):
    UNKNOWN = "unknown"
    EXCHANGE = "exchange"
    BRIDGE = "bridge"
    TREASURY = "treasury"
    WALLET = "wallet"
    AIRDROP = "airdrop"
    CONTRACT = "contract"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
