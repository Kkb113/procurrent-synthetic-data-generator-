"""Compatibility wrapper for shared UOM-aware quantity precision helpers."""

from __future__ import annotations

from procurement_data_generator.modules.shared.quantity_precision import (
    DECIMAL_QUANTITY_UOMS,
    INTEGER_QUANTITY_UOMS,
    apply_quantity_precision,
    is_whole_quantity,
    normalize_uom,
    requires_integer_quantity,
)

__all__ = [
    "DECIMAL_QUANTITY_UOMS",
    "INTEGER_QUANTITY_UOMS",
    "apply_quantity_precision",
    "is_whole_quantity",
    "normalize_uom",
    "requires_integer_quantity",
]

