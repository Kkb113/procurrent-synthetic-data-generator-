from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.transaction_generator import (
    TRANSACTION_ROLE_ORDER,
    ProcurementTransactionGenerator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = PROJECT_ROOT / "input" / "sample_procurement_metadata_phase9.xlsx"
PLAN_PATH = PROJECT_ROOT / "input" / "sample_generation_plan_phase9.json"


@pytest.fixture(scope="module")
def generated_data():
    schema_result = load_metadata_schema(METADATA_PATH)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None

    plan_result = load_llm_plan_json(PLAN_PATH)
    assert plan_result.report.is_valid
    assert plan_result.plan is not None

    master_data, master_report = ProcurementMasterDataGenerator().generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
    )
    assert master_report.is_valid

    transaction_data, transaction_report = ProcurementTransactionGenerator().generate_transaction_data(
        schema_result.schema,
        plan_result.plan,
        master_data,
        seed=42,
    )
    assert transaction_report.is_valid
    return schema_result.schema, plan_result.plan, master_data, transaction_data, transaction_report


def test_generates_all_12_transaction_table_roles(generated_data) -> None:
    schema, _, _, transaction_data, _ = generated_data
    table_by_role = {table.table_role: table.table_name for table in schema.tables.values()}

    expected_tables = {table_by_role[role] for role in TRANSACTION_ROLE_ORDER}

    assert set(transaction_data) == expected_tables


def test_transaction_row_counts_match_targets_where_feasible(generated_data) -> None:
    schema, _, _, transaction_data, _ = generated_data
    for table in _transaction_tables(schema):
        dataframe = transaction_data[table.table_name]
        if table.table_role == "inventory_balance":
            assert len(dataframe) > 0
        else:
            assert len(dataframe) == table.target_rows


def test_transaction_primary_keys_are_unique_and_non_null(generated_data) -> None:
    schema, _, _, transaction_data, _ = generated_data
    for table in _transaction_tables(schema):
        pk = _pk_column(table)
        series = transaction_data[table.table_name][pk]
        assert series.notna().all()
        assert series.is_unique


def test_all_transaction_foreign_keys_reference_valid_parent_keys(generated_data) -> None:
    schema, _, master_data, transaction_data, _ = generated_data
    all_data = {**master_data, **transaction_data}
    for table in _transaction_tables(schema):
        dataframe = transaction_data[table.table_name]
        for column in table.columns:
            if column.key_type != "FK":
                continue
            parent_df = all_data[column.related_table]
            assert set(dataframe[column.column_name]).issubset(set(parent_df[column.related_column]))


def test_requisition_line_references_requisition_header(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["PurchaseRequisitionLine"]["RequisitionID"]).issubset(set(data["PurchaseRequisitionHeader"]["RequisitionID"]))


def test_purchase_order_line_references_purchase_order_header(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["PurchaseOrderLine"]["PurchaseOrderID"]).issubset(set(data["PurchaseOrderHeader"]["PurchaseOrderID"]))


def test_shipment_line_references_purchase_order_line(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["ShipmentLine"]["PurchaseOrderLineID"]).issubset(set(data["PurchaseOrderLine"]["PurchaseOrderLineID"]))


def test_goods_receipt_line_references_shipment_line(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["GoodsReceiptLine"]["ShipmentLineID"]).issubset(set(data["ShipmentLine"]["ShipmentLineID"]))


def test_quality_inspection_header_references_goods_receipt_line(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["QualityInspectionHeader"]["GoodsReceiptLineID"]).issubset(set(data["GoodsReceiptLine"]["GoodsReceiptLineID"]))


def test_quality_inspection_line_references_quality_inspection_header(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["QualityInspectionLine"]["InspectionID"]).issubset(set(data["QualityInspectionHeader"]["InspectionID"]))


def test_inventory_transaction_references_quality_inspection_line(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert set(data["InventoryTransaction"]["InspectionLineID"]).issubset(set(data["QualityInspectionLine"]["InspectionLineID"]))


def test_purchase_order_plant_matches_linked_requisition_plant(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = data["PurchaseOrderHeader"].merge(
        data["PurchaseRequisitionHeader"][["RequisitionID", "PlantID"]],
        on="RequisitionID",
        suffixes=("_po", "_req"),
    )

    assert (merged["PlantID_po"] == merged["PlantID_req"]).all()


def test_goods_receipt_plant_matches_linked_po_requisition_plant(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = (
        data["GoodsReceiptHeader"]
        .merge(data["ShipmentHeader"][["ShipmentID", "PurchaseOrderID"]], on="ShipmentID")
        .merge(data["PurchaseOrderHeader"][["PurchaseOrderID", "PlantID"]], on="PurchaseOrderID", suffixes=("_receipt", "_po"))
    )

    assert (merged["PlantID_receipt"] == merged["PlantID_po"]).all()


def test_goods_receipt_warehouse_belongs_to_receipt_plant(generated_data) -> None:
    _, _, master_data, data, _ = generated_data
    merged = data["GoodsReceiptHeader"].merge(
        master_data["Warehouse"][["WarehouseID", "PlantID"]],
        on="WarehouseID",
        suffixes=("_receipt", "_warehouse"),
    )

    assert (merged["PlantID_receipt"] == merged["PlantID_warehouse"]).all()


def test_inventory_transaction_plant_and_warehouse_match_receipt_lineage(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = (
        data["InventoryTransaction"]
        .merge(data["QualityInspectionLine"][["InspectionLineID", "InspectionID"]], on="InspectionLineID")
        .merge(data["QualityInspectionHeader"][["InspectionID", "GoodsReceiptLineID"]], on="InspectionID")
        .merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "GoodsReceiptID"]], on="GoodsReceiptLineID")
        .merge(
            data["GoodsReceiptHeader"][["GoodsReceiptID", "PlantID", "WarehouseID"]],
            on="GoodsReceiptID",
            suffixes=("_txn", "_receipt"),
        )
    )

    assert (merged["PlantID_txn"] == merged["PlantID_receipt"]).all()
    assert (merged["WarehouseID_txn"] == merged["WarehouseID_receipt"]).all()


def test_date_lifecycle_is_valid(generated_data) -> None:
    _, _, _, data, _ = generated_data

    po_dates = data["PurchaseOrderHeader"].merge(
        data["PurchaseRequisitionHeader"][["RequisitionID", "RequisitionDate"]],
        on="RequisitionID",
    )
    assert (_as_datetime(po_dates["OrderDate"]) >= _as_datetime(po_dates["RequisitionDate"])).all()

    shipment_dates = data["ShipmentHeader"].merge(
        data["PurchaseOrderHeader"][["PurchaseOrderID", "OrderDate"]],
        on="PurchaseOrderID",
    )
    assert (_as_datetime(shipment_dates["ShipmentDate"]) >= _as_datetime(shipment_dates["OrderDate"])).all()

    receipt_dates = data["GoodsReceiptHeader"].merge(
        data["ShipmentHeader"][["ShipmentID", "ShipmentDate"]],
        on="ShipmentID",
    )
    assert (_as_datetime(receipt_dates["ReceiptDate"]) >= _as_datetime(receipt_dates["ShipmentDate"])).all()

    inspection_dates = (
        data["QualityInspectionHeader"]
        .merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "GoodsReceiptID"]], on="GoodsReceiptLineID")
        .merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ReceiptDate"]], on="GoodsReceiptID")
    )
    assert (_as_datetime(inspection_dates["InspectionDate"]) >= _as_datetime(inspection_dates["ReceiptDate"])).all()

    inventory_dates = (
        data["InventoryTransaction"]
        .merge(data["QualityInspectionLine"][["InspectionLineID", "InspectionID"]], on="InspectionLineID")
        .merge(data["QualityInspectionHeader"][["InspectionID", "InspectionDate"]], on="InspectionID")
    )
    assert (_as_datetime(inventory_dates["TransactionDate"]) >= _as_datetime(inventory_dates["InspectionDate"])).all()


def test_shipped_quantity_does_not_exceed_ordered_quantity(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = data["ShipmentLine"].merge(
        data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]],
        on="PurchaseOrderLineID",
    )
    assert (merged["ShippedQuantity"] <= merged["OrderedQuantity"]).all()


def test_received_quantity_does_not_exceed_shipped_quantity(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = data["GoodsReceiptLine"].merge(
        data["ShipmentLine"][["ShipmentLineID", "ShippedQuantity"]].rename(columns={"ShippedQuantity": "ShipmentLineShippedQuantity"}),
        on="ShipmentLineID",
    )
    assert (merged["ReceivedQuantity"] <= merged["ShipmentLineShippedQuantity"]).all()


def test_accepted_plus_rejected_equals_inspected(generated_data) -> None:
    _, _, _, data, _ = generated_data
    lines = data["QualityInspectionLine"]
    assert ((lines["AcceptedQuantity"] + lines["RejectedQuantity"]) == lines["InspectedQuantity"]).all()


def test_inventory_transaction_quantity_equals_accepted_quantity(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = data["InventoryTransaction"].merge(
        data["QualityInspectionLine"][["InspectionLineID", "AcceptedQuantity"]],
        on="InspectionLineID",
    )
    assert (merged["TransactionQuantity"] == merged["AcceptedQuantity"]).all()


def test_inventory_balance_matches_grouped_inventory_transactions(generated_data) -> None:
    _, _, _, data, _ = generated_data
    keys = ["RawMaterialID", "PlantID", "WarehouseID"]
    grouped = data["InventoryTransaction"].groupby(keys, as_index=False)["TransactionQuantity"].sum()
    grouped = grouped.rename(columns={"TransactionQuantity": "ExpectedOnHandQuantity"})
    merged = data["InventoryBalance"].merge(grouped, on=keys)

    assert len(merged) == len(data["InventoryBalance"])
    assert (merged["OnHandQuantity"] == merged["ExpectedOnHandQuantity"]).all()
    assert set(map(tuple, data["InventoryBalance"][keys].to_numpy())).issubset(set(map(tuple, grouped[keys].to_numpy())))


def test_some_partial_deliveries_exist(generated_data) -> None:
    _, _, _, data, _ = generated_data
    merged = data["ShipmentLine"].merge(
        data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]],
        on="PurchaseOrderLineID",
    )
    assert (merged["ShippedQuantity"] < merged["OrderedQuantity"]).any()


def test_some_supplier_delays_exist(generated_data) -> None:
    _, _, _, data, _ = generated_data
    shipment_header = data["ShipmentHeader"].merge(
        data["PurchaseOrderHeader"][["PurchaseOrderID", "ExpectedDeliveryDate"]],
        on="PurchaseOrderID",
    )
    assert (_as_datetime(shipment_header["ShipmentDate"]) > _as_datetime(shipment_header["ExpectedDeliveryDate"])).any()


def test_some_short_receipts_exist(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert (data["GoodsReceiptLine"]["ShortQuantity"] > 0).any()


def test_some_quality_rejections_exist(generated_data) -> None:
    _, _, _, data, _ = generated_data
    assert (data["QualityInspectionLine"]["RejectedQuantity"] > 0).any()


def test_status_values_are_within_allowed_values(generated_data) -> None:
    schema, _, _, data, _ = generated_data
    for table in _transaction_tables(schema):
        dataframe = data[table.table_name]
        for column in table.columns:
            if column.allowed_values:
                assert set(dataframe[column.column_name].dropna()).issubset(set(column.allowed_values))


def test_nullable_no_transaction_columns_contain_no_nulls(generated_data) -> None:
    schema, _, _, data, _ = generated_data
    for table in _transaction_tables(schema):
        dataframe = data[table.table_name]
        for column in table.columns:
            if column.nullable == "No":
                assert dataframe[column.column_name].notna().all()


def test_same_seed_produces_same_transaction_data(generated_data) -> None:
    schema, plan, master_data, _, _ = generated_data
    first, first_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master_data, seed=42)
    second, second_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master_data, seed=42)

    assert first_report.is_valid
    assert second_report.is_valid
    for table_name in first:
        pdt.assert_frame_equal(first[table_name], second[table_name])


def test_different_seed_changes_some_transaction_values(generated_data) -> None:
    schema, plan, master_data, _, _ = generated_data
    first, first_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master_data, seed=42)
    second, second_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master_data, seed=99)

    assert first_report.is_valid
    assert second_report.is_valid
    assert not first["PurchaseOrderLine"].equals(second["PurchaseOrderLine"])


def _transaction_tables(schema):
    by_role = {table.table_role: table for table in schema.tables.values()}
    return [by_role[role] for role in TRANSACTION_ROLE_ORDER]


def _pk_column(table) -> str:
    return next(column.column_name for column in table.columns if column.key_type == "PK")


def _as_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series)
