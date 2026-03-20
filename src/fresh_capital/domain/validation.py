"""Validation helpers shared by domain models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from numbers import Real
from typing import TypeVar


EnumType = TypeVar("EnumType", bound=Enum)


def ensure_non_negative_number(name: str, value: Real) -> Real:
    """Validate that a numeric value is not negative."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def ensure_percentage(name: str, value: Real) -> float:
    """Validate a decimal percentage in the inclusive range 0..1."""
    ensure_non_negative_number(name, value)
    if value > 1:
        raise ValueError(f"{name} must be between 0 and 1 inclusive")
    return float(value)


def ensure_timestamp_order(
    earlier_name: str,
    earlier_value: datetime,
    later_name: str,
    later_value: datetime,
) -> None:
    """Validate that the earlier timestamp is not after the later timestamp."""
    if earlier_value > later_value:
        raise ValueError(f"{earlier_name} must be less than or equal to {later_name}")


def ensure_enum_member(name: str, value: object, enum_cls: type[EnumType]) -> EnumType:
    """Validate that a value is a member of the provided enum class."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be a valid {enum_cls.__name__}") from exc
    raise TypeError(f"{name} must be a {enum_cls.__name__} or string value")
