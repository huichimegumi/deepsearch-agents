from __future__ import annotations

import re
from decimal import Decimal


class RangeSyntaxError(ValueError):
    """Raised when a fee-rule range cannot be interpreted deterministically."""


_RANGE_PATTERN = re.compile(r"^([^\s]+)-([^\s]+)$")


def matches_capture_delay(expression: str | None, value: str) -> bool:
    if expression is None:
        return True
    if expression in {"immediate", "manual"}:
        return value == expression
    if value in {"immediate", "manual"}:
        return False
    try:
        numeric = Decimal(value)
    except Exception as exc:
        raise RangeSyntaxError(
            f"capture delay {value!r} cannot be compared with {expression!r}"
        ) from exc
    return matches_decimal_range(expression, numeric, parse_number=Decimal)


def matches_volume(expression: str | None, value: Decimal) -> bool:
    if expression is None:
        return True
    return matches_decimal_range(expression, value, parse_number=parse_scaled_number)


def matches_percentage(expression: str | None, ratio: Decimal) -> bool:
    if expression is None:
        return True
    return matches_decimal_range(expression, ratio, parse_number=parse_percentage)


def matches_decimal_range(
    expression: str,
    value: Decimal,
    *,
    parse_number,
) -> bool:
    """Match documented DABStep ranges using inclusive written intervals.

    Both ends of ``a-b`` are inclusive, following the manual's "between" wording.
    A leading ``>`` or ``<`` remains strict, matching its literal meaning.
    """

    if expression.startswith("<"):
        return value < parse_number(expression[1:])
    if expression.startswith(">"):
        return value > parse_number(expression[1:])
    match = _RANGE_PATTERN.fullmatch(expression)
    if not match:
        raise RangeSyntaxError(f"unsupported range expression: {expression!r}")
    lower = parse_number(match.group(1))
    upper = parse_number(match.group(2))
    return lower <= value <= upper


def parse_scaled_number(value: str) -> Decimal:
    normalized = value.strip().lower()
    multiplier = Decimal("1")
    if normalized.endswith("k"):
        normalized = normalized[:-1]
        multiplier = Decimal("1000")
    elif normalized.endswith("m"):
        normalized = normalized[:-1]
        multiplier = Decimal("1000000")
    try:
        return Decimal(normalized) * multiplier
    except Exception as exc:
        raise RangeSyntaxError(f"invalid scaled number: {value!r}") from exc


def parse_percentage(value: str) -> Decimal:
    normalized = value.strip()
    if not normalized.endswith("%"):
        raise RangeSyntaxError(f"percentage must end with %: {value!r}")
    try:
        return Decimal(normalized[:-1]) / Decimal("100")
    except Exception as exc:
        raise RangeSyntaxError(f"invalid percentage: {value!r}") from exc
