from __future__ import annotations

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.transaction_generator import SalesTransactionGenerator
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_finished_goods_inventory_update_method_returns_inventory() -> None:
    upstream, sales_data = _inventory_update_inputs()
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )

    assert isinstance(updated, pd.DataFrame)
    assert tuple(updated.columns) == tuple(upstream["FinishedGoodsInventory"].columns)


def test_sales_finished_goods_inventory_update_preserves_rows_and_identity() -> None:
    upstream, sales_data = _inventory_update_inputs()
    original = upstream["FinishedGoodsInventory"]
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )

    assert len(updated) == len(original)
    assert updated["FinishedGoodsInventoryID"].tolist() == original["FinishedGoodsInventoryID"].tolist()
    assert updated["ProductID"].tolist() == original["ProductID"].tolist()
    assert updated["PlantID"].tolist() == original["PlantID"].tolist()
    assert updated["WarehouseID"].tolist() == original["WarehouseID"].tolist()


def test_sales_finished_goods_inventory_quantities_recalculate_from_sales_activity() -> None:
    upstream, sales_data = _inventory_update_inputs()
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    ).set_index("FinishedGoodsInventoryID")

    assert updated.loc[401, "OnHandQuantity"] == pytest.approx(73.0)
    assert updated.loc[401, "ReservedQuantity"] == pytest.approx(5.0)
    assert updated.loc[401, "AvailableQuantity"] == pytest.approx(68.0)
    assert updated.loc[402, "OnHandQuantity"] == pytest.approx(41.0)
    assert updated.loc[402, "ReservedQuantity"] == pytest.approx(0.0)
    assert updated.loc[402, "AvailableQuantity"] == pytest.approx(41.0)
    assert updated.loc[403, "OnHandQuantity"] == pytest.approx(80.0)
    assert updated.loc[403, "ReservedQuantity"] == pytest.approx(10.0)
    assert updated.loc[403, "AvailableQuantity"] == pytest.approx(70.0)


def test_sales_finished_goods_inventory_only_reserved_status_counts_as_current_reserved() -> None:
    upstream, sales_data = _inventory_update_inputs()
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )
    reserved_by_inventory = updated.set_index("FinishedGoodsInventoryID")["ReservedQuantity"].to_dict()

    assert reserved_by_inventory[401] == pytest.approx(5.0)
    assert reserved_by_inventory[402] == pytest.approx(0.0)
    assert reserved_by_inventory[403] == pytest.approx(10.0)


def test_sales_finished_goods_inventory_value_status_and_date_fields_recalculate() -> None:
    upstream, sales_data = _inventory_update_inputs()
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    ).set_index("FinishedGoodsInventoryID")

    assert updated.loc[401, "OnHandValue"] == pytest.approx(146.0)
    assert updated.loc[401, "AvailableValue"] == pytest.approx(136.0)
    assert updated.loc[402, "OnHandValue"] == pytest.approx(123.0)
    assert updated.loc[402, "AvailableValue"] == pytest.approx(123.0)
    assert updated.loc[403, "OnHandValue"] == pytest.approx(320.0)
    assert updated.loc[403, "AvailableValue"] == pytest.approx(280.0)
    assert set(updated["InventoryStatus"]).issubset({"Available", "LowStock", "Hold", "OutOfStock"})
    assert updated.loc[401, "LastUpdatedDate"] == "2025-02-05"


def test_sales_finished_goods_inventory_non_negative_and_reserved_not_above_on_hand() -> None:
    upstream, sales_data = _inventory_update_inputs()
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )

    assert (updated[["OnHandQuantity", "ReservedQuantity", "AvailableQuantity"]] >= 0).all().all()
    assert (updated["ReservedQuantity"] <= updated["OnHandQuantity"]).all()


def test_sales_finished_goods_inventory_update_does_not_mutate_input_dataframes() -> None:
    upstream, sales_data = _inventory_update_inputs()
    original_inventory = upstream["FinishedGoodsInventory"].copy(deep=True)
    original_shipments = sales_data["SalesShipmentLine"].copy(deep=True)
    _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )

    pd.testing.assert_frame_equal(upstream["FinishedGoodsInventory"], original_inventory)
    pd.testing.assert_frame_equal(sales_data["SalesShipmentLine"], original_shipments)


def test_sales_finished_goods_inventory_missing_required_inputs_fail_clearly() -> None:
    upstream, sales_data = _inventory_update_inputs()
    generator = _generator(upstream)

    with pytest.raises(ValueError, match="FinishedGoodsInventory"):
        generator.update_finished_goods_inventory_after_sales(
            upstream_data={k: v for k, v in upstream.items() if k != "FinishedGoodsInventory"},
            sales_transaction_data=sales_data,
        )
    with pytest.raises(ValueError, match="FinishedGoodsReceipt"):
        generator.update_finished_goods_inventory_after_sales(
            upstream_data={k: v for k, v in upstream.items() if k != "FinishedGoodsReceipt"},
            sales_transaction_data=sales_data,
        )
    with pytest.raises(ValueError, match="SalesShipmentLine"):
        generator.update_finished_goods_inventory_after_sales(
            upstream_data=upstream,
            sales_transaction_data={k: v for k, v in sales_data.items() if k != "SalesShipmentLine"},
        )
    with pytest.raises(ValueError, match="SalesInventoryReservation"):
        generator.update_finished_goods_inventory_after_sales(
            upstream_data=upstream,
            sales_transaction_data={k: v for k, v in sales_data.items() if k != "SalesInventoryReservation"},
        )


def test_sales_finished_goods_inventory_missing_return_lines_are_treated_as_zero_restocked() -> None:
    upstream, sales_data = _inventory_update_inputs()
    updated = _generator(upstream).update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data={k: v for k, v in sales_data.items() if k not in {"SalesReturnHeader", "SalesReturnLine"}},
    ).set_index("FinishedGoodsInventoryID")

    assert updated.loc[401, "OnHandQuantity"] == pytest.approx(70.0)
    assert updated.loc[402, "OnHandQuantity"] == pytest.approx(40.0)


def test_sales_finished_goods_inventory_oversell_raises_clear_error() -> None:
    upstream, sales_data = _inventory_update_inputs()
    sales_data["SalesShipmentLine"].loc[0, "ShippedQuantity"] = 200.0

    with pytest.raises(ValueError, match="negative OnHandQuantity"):
        _generator(upstream).update_finished_goods_inventory_after_sales(
            upstream_data=upstream,
            sales_transaction_data=sales_data,
        )


def test_sales_finished_goods_inventory_update_is_deterministic() -> None:
    upstream, sales_data = _inventory_update_inputs()
    generator = _generator(upstream)
    first = generator.update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )
    second = generator.update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data=sales_data,
    )

    pd.testing.assert_frame_equal(first, second)


def _generator(upstream: dict[str, pd.DataFrame]) -> SalesTransactionGenerator:
    return SalesTransactionGenerator(
        upstream_data=upstream,
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )


def _inventory_update_inputs() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    upstream = {
        "FinishedGoodsInventory": pd.DataFrame(
            {
                "FinishedGoodsInventoryID": [401, 402, 403],
                "ProductID": [101, 102, 103],
                "PlantID": [1, 1, 1],
                "WarehouseID": [1, 1, 1],
                "OnHandQuantity": [100.0, 50.0, 80.0],
                "ReservedQuantity": [0.0, 0.0, 0.0],
                "AvailableQuantity": [100.0, 50.0, 80.0],
                "OnHandValue": [200.0, 150.0, 320.0],
                "AvailableValue": [200.0, 150.0, 320.0],
                "LastUpdatedDate": ["2025-01-01", "2025-01-01", "2025-01-01"],
                "InventoryStatus": ["Available", "Available", "Available"],
            }
        ),
        "FinishedGoodsReceipt": pd.DataFrame(
            {
                "FinishedGoodsReceiptID": [501, 502, 503],
                "ProductID": [101, 102, 103],
                "PlantID": [1, 1, 1],
                "WarehouseID": [1, 1, 1],
                "GoodQuantity": [100.0, 50.0, 80.0],
                "UnitCost": [2.0, 3.0, 4.0],
                "ReceiptValue": [200.0, 150.0, 320.0],
            }
        ),
    }
    sales_data = {
        "SalesShipmentHeader": pd.DataFrame(
            {
                "ShipmentID": [1, 2],
                "ShipmentDate": ["2025-01-15", "2025-01-20"],
            }
        ),
        "SalesShipmentLine": pd.DataFrame(
            {
                "ShipmentLineID": [1, 2],
                "ShipmentID": [1, 2],
                "FinishedGoodsInventoryID": [401, 402],
                "FinishedGoodsReceiptID": [501, 502],
                "ProductID": [101, 102],
                "ShippedQuantity": [30.0, 10.0],
                "UnitCost": [2.0, 3.0],
                "COGSValue": [60.0, 30.0],
            }
        ),
        "SalesInventoryReservation": pd.DataFrame(
            {
                "ReservationID": [1, 2, 3, 4],
                "FinishedGoodsInventoryID": [401, 401, 402, 403],
                "ProductID": [101, 101, 102, 103],
                "PlantID": [1, 1, 1, 1],
                "WarehouseID": [1, 1, 1, 1],
                "ReservedQuantity": [5.0, 20.0, 8.0, 10.0],
                "ReservationStatus": ["Reserved", "Consumed", "Released", "Reserved"],
            }
        ),
        "SalesReturnHeader": pd.DataFrame(
            {
                "SalesReturnID": [1],
                "ReturnDate": ["2025-02-05"],
            }
        ),
        "SalesReturnLine": pd.DataFrame(
            {
                "SalesReturnLineID": [1, 2],
                "SalesReturnID": [1, 1],
                "ShipmentLineID": [1, 2],
                "ProductID": [101, 102],
                "ReturnedQuantity": [5.0, 2.0],
                "RestockedQuantity": [3.0, 1.0],
                "ScrappedQuantity": [2.0, 1.0],
            }
        ),
    }
    return upstream, sales_data
