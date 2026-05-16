"""Shared UOM-aware quantity precision helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any


INTEGER_QUANTITY_UOMS = {
    "assembly",
    "batterypack",
    "box",
    "controller",
    "device",
    "ea",
    "each",
    "module",
    "motor",
    "pack",
    "pcs",
    "piece",
    "sensor",
    "set",
    "unit",
}

DECIMAL_QUANTITY_UOMS = {
    "coil",
    "gallon",
    "kg",
    "kilogram",
    "liter",
    "litre",
    "liquidvolume",
    "meter",
    "metre",
    "roll",
    "sheetweight",
    "ton",
}


def normalize_uom(value: Any) -> str:
    """Normalize UOM strings for precision classification."""

    return "".join(char for char in str(value or "").strip().lower() if char.isalnum())


def requires_integer_quantity(unit_of_measure: Any) -> bool:
    """Return True when the component UOM should be counted as whole units."""

    normalized = normalize_uom(unit_of_measure)
    return normalized in INTEGER_QUANTITY_UOMS


def is_whole_quantity(value: Any, tolerance: float = 0.0001) -> bool:
    """Return True when a numeric value is effectively a whole number."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return abs(numeric - round(numeric)) <= tolerance


def apply_quantity_precision(
    quantity: Any,
    unit_of_measure: Any,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
    rounding: str = "nearest",
) -> float:
    """Apply UOM-aware precision to a generated quantity."""

    try:
        value = Decimal(str(quantity))
    except Exception:
        value = Decimal("0")

    if maximum is not None:
        value = min(value, Decimal(str(maximum)))
    value = max(value, Decimal(str(minimum)))

    if requires_integer_quantity(unit_of_measure):
        if rounding == "floor":
            whole = value.to_integral_value(rounding=ROUND_FLOOR)
        else:
            whole = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if maximum is not None:
            whole = min(whole, Decimal(str(maximum)).to_integral_value(rounding=ROUND_FLOOR))
        whole = max(whole, Decimal(str(minimum)).to_integral_value(rounding=ROUND_HALF_UP))
        return float(whole)

    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

