from __future__ import annotations

from procurement_data_generator.modules.procurement import quantity_precision as procurement_precision
from procurement_data_generator.modules.shared import quantity_precision as shared_precision


def test_shared_quantity_precision_imports_and_procurement_wrapper_matches() -> None:
    assert procurement_precision.INTEGER_QUANTITY_UOMS is shared_precision.INTEGER_QUANTITY_UOMS
    assert procurement_precision.DECIMAL_QUANTITY_UOMS is shared_precision.DECIMAL_QUANTITY_UOMS
    assert procurement_precision.normalize_uom is shared_precision.normalize_uom
    assert procurement_precision.requires_integer_quantity is shared_precision.requires_integer_quantity
    assert procurement_precision.is_whole_quantity is shared_precision.is_whole_quantity
    assert procurement_precision.apply_quantity_precision is shared_precision.apply_quantity_precision


def test_countable_uom_quantities_round_to_whole_units() -> None:
    assert shared_precision.requires_integer_quantity("EA")
    assert shared_precision.requires_integer_quantity("BatteryPack")
    assert shared_precision.apply_quantity_precision(12.6, "EA") == 13.0
    assert shared_precision.apply_quantity_precision(12.6, "Module", rounding="floor") == 12.0
    assert shared_precision.is_whole_quantity(shared_precision.apply_quantity_precision(7.25, "PCS"))


def test_decimal_bulk_uom_quantities_keep_decimal_precision() -> None:
    assert not shared_precision.requires_integer_quantity("KG")
    assert not shared_precision.requires_integer_quantity("Liter")
    assert shared_precision.apply_quantity_precision(12.345, "KG") == 12.35
    assert shared_precision.apply_quantity_precision(7.234, "Meter") == 7.23

