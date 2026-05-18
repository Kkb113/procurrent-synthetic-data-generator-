from __future__ import annotations

import re

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.transaction_generator import (
    SALES_PHASE4_TRANSACTION_TABLES,
    SalesTransactionGenerator,
)
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_transaction_generator_can_be_constructed_with_required_inputs() -> None:
    generator = SalesTransactionGenerator(
        sales_master_data=_sales_master_data(),
        upstream_data=_upstream_data(),
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )

    dataframes = generator.generate_transaction_data()

    assert set(dataframes) == set(SALES_PHASE4_TRANSACTION_TABLES)


def test_sales_phase4_generates_only_order_reservation_pick_and_shipment_tables() -> None:
    dataframes = _generate_phase4()

    assert tuple(dataframes) == SALES_PHASE4_TRANSACTION_TABLES
    for table_name in (
        "SalesInvoiceHeader",
        "SalesInvoiceLine",
        "CustomerPaymentReceipt",
        "SalesReturnHeader",
        "SalesReturnLine",
        "SalesShipmentTraceability",
    ):
        assert table_name not in dataframes


def test_sales_phase4_required_columns_and_primary_keys() -> None:
    dataframes = _generate_phase4()
    expected_columns = {
        "SalesOrderHdr": (
            "SalesOrderID",
            "SalesOrderNumber",
            "CustomerID",
            "BillToLocationID",
            "ShipToLocationID",
            "SalesChannelID",
            "OrderDate",
            "RequestedShipDate",
            "PromisedShipDate",
            "CurrencyCode",
            "OrderStatus",
        ),
        "SalesOrderLine": (
            "SalesOrderLineID",
            "SalesOrderID",
            "ProductID",
            "PlantID",
            "WarehouseID",
            "OrderedQuantity",
            "ReservedQuantity",
            "ShippedQuantity",
            "BackorderQuantity",
            "UOM",
            "UnitPrice",
            "DiscountPct",
            "LineAmount",
            "DiscountAmount",
            "NetLineAmount",
            "LineStatus",
        ),
        "SalesInventoryReservation": (
            "ReservationID",
            "SalesOrderLineID",
            "FinishedGoodsInventoryID",
            "ProductID",
            "PlantID",
            "WarehouseID",
            "ReservationDate",
            "ReservedQuantity",
            "ReleasedQuantity",
            "ReservationStatus",
        ),
        "SalesPickListHeader": ("PickListID", "SalesOrderID", "WarehouseID", "PickDate", "PickStatus"),
        "SalesPickListLine": (
            "PickListLineID",
            "PickListID",
            "SalesOrderLineID",
            "ReservationID",
            "ProductID",
            "PickedQuantity",
            "UOM",
            "PickLineStatus",
        ),
        "SalesShipmentHeader": (
            "ShipmentID",
            "ShipmentNumber",
            "SalesOrderID",
            "CustomerID",
            "ShipToLocationID",
            "WarehouseID",
            "ShipmentDate",
            "CarrierName",
            "TrackingNumber",
            "ShipmentStatus",
        ),
        "SalesShipmentLine": (
            "ShipmentLineID",
            "ShipmentID",
            "SalesOrderLineID",
            "PickListLineID",
            "FinishedGoodsInventoryID",
            "FinishedGoodsReceiptID",
            "ProductionBatchID",
            "ProductID",
            "ShippedQuantity",
            "UOM",
            "UnitCost",
            "COGSValue",
            "ShipmentLineStatus",
        ),
    }
    pk_columns = {
        "SalesOrderHdr": "SalesOrderID",
        "SalesOrderLine": "SalesOrderLineID",
        "SalesInventoryReservation": "ReservationID",
        "SalesPickListHeader": "PickListID",
        "SalesPickListLine": "PickListLineID",
        "SalesShipmentHeader": "ShipmentID",
        "SalesShipmentLine": "ShipmentLineID",
    }

    for table_name, columns in expected_columns.items():
        assert tuple(dataframes[table_name].columns) == columns
        assert dataframes[table_name][pk_columns[table_name]].is_unique
        assert not dataframes[table_name].empty


def test_sales_order_header_foreign_keys_are_valid() -> None:
    sales_master = _sales_master_data()
    dataframes = _generate_phase4(sales_master=sales_master)
    order_header = dataframes["SalesOrderHdr"]

    assert set(order_header["CustomerID"]).issubset(set(sales_master["CustomerMaster"]["CustomerID"]))
    assert set(order_header["BillToLocationID"]).issubset(set(sales_master["CustomerLocation"]["CustomerLocationID"]))
    assert set(order_header["ShipToLocationID"]).issubset(set(sales_master["CustomerLocation"]["CustomerLocationID"]))
    assert set(order_header["SalesChannelID"]).issubset(set(sales_master["SalesChannel"]["SalesChannelID"]))


def test_sales_phase4_line_reservation_pick_and_shipment_foreign_keys_are_valid() -> None:
    upstream = _upstream_data()
    dataframes = _generate_phase4(upstream=upstream)
    order_header = dataframes["SalesOrderHdr"]
    order_line = dataframes["SalesOrderLine"]
    reservation = dataframes["SalesInventoryReservation"]
    pick_header = dataframes["SalesPickListHeader"]
    pick_line = dataframes["SalesPickListLine"]
    shipment_header = dataframes["SalesShipmentHeader"]
    shipment_line = dataframes["SalesShipmentLine"]

    assert set(order_line["SalesOrderID"]).issubset(set(order_header["SalesOrderID"]))
    assert set(order_line["ProductID"]).issubset(set(upstream["ProductMaster"]["ProductID"]))
    assert set(reservation["SalesOrderLineID"]).issubset(set(order_line["SalesOrderLineID"]))
    assert set(reservation["FinishedGoodsInventoryID"]).issubset(set(upstream["FinishedGoodsInventory"]["FinishedGoodsInventoryID"]))
    assert set(pick_line["PickListID"]).issubset(set(pick_header["PickListID"]))
    assert set(pick_line["ReservationID"]).issubset(set(reservation["ReservationID"]))
    assert set(pick_line["SalesOrderLineID"]).issubset(set(order_line["SalesOrderLineID"]))
    assert set(shipment_line["ShipmentID"]).issubset(set(shipment_header["ShipmentID"]))
    assert set(shipment_line["SalesOrderLineID"]).issubset(set(order_line["SalesOrderLineID"]))
    assert set(shipment_line["PickListLineID"]).issubset(set(pick_line["PickListLineID"]))
    assert set(shipment_line["FinishedGoodsInventoryID"]).issubset(set(upstream["FinishedGoodsInventory"]["FinishedGoodsInventoryID"]))
    assert set(shipment_line["FinishedGoodsReceiptID"]).issubset(set(upstream["FinishedGoodsReceipt"]["FinishedGoodsReceiptID"]))
    assert set(shipment_line["ProductionBatchID"]).issubset(set(upstream["ProductionBatch"]["ProductionBatchID"]))


def test_sales_phase4_quantity_lifecycle_and_backorder_calculation() -> None:
    dataframes = _generate_phase4()
    merged = _merged_lifecycle(dataframes)

    assert (merged["OrderedQuantity"] >= merged["ReservedQuantity"]).all()
    assert (merged["ReservedQuantity"] >= merged["PickedQuantity"]).all()
    assert (merged["PickedQuantity"] >= merged["ShippedQuantity"]).all()
    assert (merged["BackorderQuantity"].round(2) == (merged["OrderedQuantity"] - merged["ShippedQuantity"]).round(2)).all()


def test_sales_phase4_does_not_oversell_finished_goods_inventory_or_receipts() -> None:
    upstream = _upstream_data()
    dataframes = _generate_phase4(upstream=upstream)
    reservation = dataframes["SalesInventoryReservation"]
    shipment_line = dataframes["SalesShipmentLine"]
    inventory_available = upstream["FinishedGoodsInventory"].set_index("FinishedGoodsInventoryID")["AvailableQuantity"]
    receipt_good_quantity = upstream["FinishedGoodsReceipt"].set_index("FinishedGoodsReceiptID")["GoodQuantity"]

    reserved_by_inventory = reservation.groupby("FinishedGoodsInventoryID")["ReservedQuantity"].sum()
    shipped_by_inventory = shipment_line.groupby("FinishedGoodsInventoryID")["ShippedQuantity"].sum()
    shipped_by_receipt = shipment_line.groupby("FinishedGoodsReceiptID")["ShippedQuantity"].sum()

    for inventory_id, reserved_quantity in reserved_by_inventory.items():
        assert reserved_quantity <= inventory_available[inventory_id]
    for inventory_id, shipped_quantity in shipped_by_inventory.items():
        assert shipped_quantity <= inventory_available[inventory_id]
    for receipt_id, shipped_quantity in shipped_by_receipt.items():
        assert shipped_quantity <= receipt_good_quantity[receipt_id]


def test_sales_phase4_cogs_and_order_line_financials_reconcile() -> None:
    dataframes = _generate_phase4()
    order_line = dataframes["SalesOrderLine"]
    shipment_line = dataframes["SalesShipmentLine"]

    expected_line_amount = (order_line["OrderedQuantity"] * order_line["UnitPrice"]).round(2)
    expected_discount_amount = (order_line["LineAmount"] * order_line["DiscountPct"] / 100).round(2)
    assert (order_line["LineAmount"].round(2) == expected_line_amount).all()
    assert (order_line["DiscountAmount"].round(2) == expected_discount_amount).all()
    assert (order_line["NetLineAmount"].round(2) == (order_line["LineAmount"] - order_line["DiscountAmount"]).round(2)).all()
    assert (shipment_line["COGSValue"].round(2) == (shipment_line["ShippedQuantity"] * shipment_line["UnitCost"]).round(2)).all()


def test_sales_phase4_statuses_are_fact_derived() -> None:
    dataframes = _generate_phase4()
    merged = _merged_lifecycle(dataframes)

    assert "Closed" in set(merged["LineStatus"])
    assert "PartiallyShipped" in set(merged["LineStatus"])
    assert "Backordered" in set(merged["LineStatus"])
    assert "Consumed" in set(merged["ReservationStatus"])
    assert "ShortPicked" in set(merged["PickLineStatus"])

    for row in merged.itertuples(index=False):
        if row.ShippedQuantity == row.OrderedQuantity:
            assert row.LineStatus == "Closed"
        elif row.ReservedQuantity < row.OrderedQuantity:
            assert row.LineStatus == "Backordered"
        elif row.ShippedQuantity < row.OrderedQuantity:
            assert row.LineStatus == "PartiallyShipped"
        if row.ShippedQuantity == row.ReservedQuantity:
            assert row.ReservationStatus == "Consumed"
        if row.PickedQuantity < row.ReservedQuantity:
            assert row.PickLineStatus == "ShortPicked"


def test_sales_phase4_generation_is_deterministic_for_same_inputs() -> None:
    first = _generate_phase4()
    second = _generate_phase4()

    for table_name in SALES_PHASE4_TRANSACTION_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])


def test_sales_phase4_missing_required_inputs_fail_clearly() -> None:
    sales_master = _sales_master_data()
    upstream = _upstream_data()

    with pytest.raises(ValueError, match="FinishedGoodsInventory"):
        _generator(sales_master_data=sales_master, upstream_data={k: v for k, v in upstream.items() if k != "FinishedGoodsInventory"}).generate_transaction_data()
    with pytest.raises(ValueError, match="FinishedGoodsReceipt"):
        _generator(sales_master_data=sales_master, upstream_data={k: v for k, v in upstream.items() if k != "FinishedGoodsReceipt"}).generate_transaction_data()
    with pytest.raises(ValueError, match="Sales master data CustomerMaster"):
        _generator(sales_master_data={}, upstream_data=upstream).generate_transaction_data()


def test_sales_phase4_food_profile_transaction_text_has_no_ev_vocabulary() -> None:
    dataframes = _generate_phase4()
    shipment_header = dataframes["SalesShipmentHeader"]

    assert _context_row_count(shipment_header, ["CarrierName"], ("FreshRoute", "SnackLine", "Food Transport")) > 0
    _assert_ev_terms_absent(shipment_header, ["CarrierName", "TrackingNumber"])


def _generator(
    sales_master_data: dict[str, pd.DataFrame] | None = None,
    upstream_data: dict[str, pd.DataFrame] | None = None,
) -> SalesTransactionGenerator:
    return SalesTransactionGenerator(
        sales_master_data=sales_master_data if sales_master_data is not None else _sales_master_data(),
        upstream_data=upstream_data if upstream_data is not None else _upstream_data(),
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )


def _generate_phase4(
    sales_master: dict[str, pd.DataFrame] | None = None,
    upstream: dict[str, pd.DataFrame] | None = None,
) -> dict[str, pd.DataFrame]:
    return _generator(sales_master_data=sales_master, upstream_data=upstream).generate_transaction_data()


def _sales_master_data() -> dict[str, pd.DataFrame]:
    return SalesMasterDataGenerator(
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    ).generate_master_data(upstream_data=_upstream_data())


def _upstream_data() -> dict[str, pd.DataFrame]:
    return {
        "ProductMaster": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "ProductName": ["Potato Chips", "Corn Snacks", "Seasoned Snack Mix"],
                "ProductCategory": ["Potato Chips", "Corn Snacks", "Seasoned Snack Mix"],
                "UOM": ["EA", "EA", "EA"],
            }
        ),
        "FinishedGoodsInventory": pd.DataFrame(
            {
                "FinishedGoodsInventoryID": [401, 402, 403],
                "ProductID": [101, 102, 103],
                "PlantID": [1, 1, 1],
                "WarehouseID": [1, 1, 1],
                "OnHandQuantity": [120.0, 100.0, 110.0],
                "ReservedQuantity": [0.0, 0.0, 0.0],
                "AvailableQuantity": [120.0, 100.0, 110.0],
            }
        ),
        "FinishedGoodsReceipt": pd.DataFrame(
            {
                "FinishedGoodsReceiptID": [501, 502, 503],
                "ProductID": [101, 102, 103],
                "PlantID": [1, 1, 1],
                "WarehouseID": [1, 1, 1],
                "ProductionBatchID": [601, 602, 603],
                "GoodQuantity": [120.0, 100.0, 110.0],
                "UnitCost": [12.0, 10.5, 13.25],
            }
        ),
        "ProductionBatch": pd.DataFrame(
            {
                "ProductionBatchID": [601, 602, 603],
                "ProductID": [101, 102, 103],
            }
        ),
        "ProductionCostSummary": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "UnitProductionCost": [12.25, 10.75, 13.5],
            }
        ),
    }


def _merged_lifecycle(dataframes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return (
        dataframes["SalesOrderLine"]
        .merge(dataframes["SalesInventoryReservation"], on="SalesOrderLineID", suffixes=("", "_reservation"))
        .merge(dataframes["SalesPickListLine"], on=["SalesOrderLineID", "ReservationID"], suffixes=("", "_pick"))
        .merge(dataframes["SalesShipmentLine"], on=["SalesOrderLineID", "PickListLineID"], suffixes=("", "_shipment"))
    )


def _context_row_count(dataframe: pd.DataFrame, columns: list[str], terms: tuple[str, ...]) -> int:
    lowered_terms = tuple(term.lower() for term in terms)
    count = 0
    for _, row in dataframe.iterrows():
        row_text = " ".join(str(row[column]) for column in columns if column in dataframe.columns).lower()
        if any(term in row_text for term in lowered_terms):
            count += 1
    return count


def _assert_ev_terms_absent(dataframe: pd.DataFrame, columns: list[str]) -> None:
    text = " ".join(str(value) for column in columns for value in dataframe[column].dropna().tolist())
    for term in ("Battery", "Automotive", "Chassis", "Drive Unit", "Power Electronics", "Dealer", "Fleet"):
        assert term.lower() not in text.lower()
    assert re.search(r"(?<![A-Za-z])EV(?![A-Za-z])", text, flags=re.IGNORECASE) is None
