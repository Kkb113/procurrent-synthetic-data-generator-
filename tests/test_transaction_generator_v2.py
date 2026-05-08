from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "input" / "procurement_v2_metadata.xlsx"
PLAN_PATH = ROOT / "input" / "sample_generation_plan_v2_valid.json"

EXPECTED_TABLES = {
    "PurchaseRequisition",
    "PurchaseReqLine",
    "RFQHeader",
    "RFQLine",
    "SupplierQuotation",
    "SupplierQuotationLn",
    "PurchaseOrderHdr",
    "PurchaseOrderLine",
    "POSchedule",
    "ShipmentHdr",
    "ShipmentLine",
    "GoodsReceiptHeader",
    "GoodsReceiptLine",
    "IncomingInspection",
    "InspectionResult",
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
}


@pytest.fixture(scope="module")
def generated_v2_transactions():
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
        model_version="v2",
    )
    assert master_report.is_valid
    transaction_data, transaction_report = ProcurementTransactionGenerator().generate_transaction_data(
        schema_result.schema,
        plan_result.plan,
        master_data,
        seed=42,
        model_version="v2",
    )
    assert transaction_report.is_valid, [issue.message for issue in transaction_report.errors]
    return schema_result.schema, plan_result.plan, master_data, transaction_data


def test_v2_transaction_generator_creates_inventory_and_process_tables(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    assert set(data) == EXPECTED_TABLES
    assert "Inventory" in data
    assert "InventoryBalance" not in data


def test_v2_transaction_row_counts_match_metadata_targets(generated_v2_transactions) -> None:
    schema, _, _, data = generated_v2_transactions
    lifecycle_derived_tables = {
        "PurchaseOrderLine",
        "POSchedule",
        "ShipmentLine",
        "GoodsReceiptLine",
        "IncomingInspection",
        "InspectionResult",
        "InventoryTransaction",
        "Inventory",
    }
    for table_name in EXPECTED_TABLES:
        if table_name in lifecycle_derived_tables:
            assert 0 < len(data[table_name]) <= schema.tables[table_name].target_rows
            continue
        assert len(data[table_name]) == schema.tables[table_name].target_rows


def test_v2_transaction_primary_keys_unique_and_non_null(generated_v2_transactions) -> None:
    schema, _, _, data = generated_v2_transactions
    for table_name in EXPECTED_TABLES:
        pk = next(column.column_name for column in schema.tables[table_name].columns if column.key_type == "PK")
        assert data[table_name][pk].notna().all()
        assert data[table_name][pk].is_unique


def test_v2_all_foreign_keys_reference_valid_parent_keys(generated_v2_transactions) -> None:
    schema, _, master, data = generated_v2_transactions
    all_data = {**master, **data}
    for table_name in EXPECTED_TABLES:
        dataframe = data[table_name]
        for column in schema.tables[table_name].columns:
            if column.key_type != "FK":
                continue
            parent = all_data[column.related_table]
            assert set(dataframe[column.column_name]).issubset(set(parent[column.related_column]))


def test_supplier_quotation_supplier_is_eligible_for_quoted_component(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    eligible = set(map(tuple, master["SupplierComponent"][["SupplierID", "ComponentID"]].to_numpy()))
    quoted = data["SupplierQuotationLn"].merge(data["SupplierQuotation"][["QuotationID", "SupplierID"]], on="QuotationID")
    by_quote = quoted.groupby("QuotationID").apply(lambda rows: any((row.SupplierID, row.ComponentID) in eligible for row in rows.itertuples()))
    assert by_quote.all()


def test_supplier_quotation_line_component_matches_rfq_line(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["SupplierQuotationLn"].merge(data["RFQLine"][["RFQLineID", "ComponentID"]], on="RFQLineID", suffixes=("_quote", "_rfq"))
    assert (merged["ComponentID_quote"] == merged["ComponentID_rfq"]).all()


def test_rfq_due_date_is_on_or_after_rfq_date_and_within_2025(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    rfq = data["RFQHeader"]
    assert (_dt(rfq["RFQDueDate"]) >= _dt(rfq["RFQDate"])).all()
    assert (_dt(rfq["RFQDate"]) >= pd.Timestamp("2025-01-01")).all()
    assert (_dt(rfq["RFQDueDate"]) <= pd.Timestamp("2025-12-31")).all()


def test_at_most_one_awarded_quote_per_rfq_line(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    awarded_counts = data["SupplierQuotationLn"].groupby("RFQLineID")["AwardedFlag"].sum()
    assert (awarded_counts <= 1).all()


def test_purchase_order_line_comes_from_awarded_quotation_line(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    awarded = data["SupplierQuotationLn"][data["SupplierQuotationLn"]["AwardedFlag"].astype(str) == "1"]
    assert set(data["PurchaseOrderLine"]["QuotationLineID"]).issubset(set(awarded["QuotationLineID"]))


def test_purchase_order_line_unit_price_matches_quote(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["PurchaseOrderLine"].merge(data["SupplierQuotationLn"][["QuotationLineID", "QuotedUnitPrice"]], on="QuotationLineID")
    assert (abs(merged["UnitPrice"] - merged["QuotedUnitPrice"]) <= 0.01).all()


def test_supplier_quotation_unit_price_is_related_to_contract_price(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    quoted = data["SupplierQuotationLn"].merge(data["SupplierQuotation"][["QuotationID", "SupplierID"]], on="QuotationID")
    merged = quoted.merge(master["SupplierComponent"][["SupplierID", "ComponentID", "ContractPrice"]], on=["SupplierID", "ComponentID"])
    ratio = merged["QuotedUnitPrice"].astype(float) / merged["ContractPrice"].astype(float)

    assert ratio.between(0.949, 1.151).all()


def test_high_price_components_use_lower_order_quantities(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    po_lines = data["PurchaseOrderLine"].merge(master["ComponentMaster"][["ComponentID", "ComponentCategory"]], on="ComponentID")
    high_price_quantity = po_lines[po_lines["UnitPrice"] >= 1000.0]["OrderedQuantity"].astype(float).mean()
    low_price_quantity = po_lines[po_lines["UnitPrice"] <= 100.0]["OrderedQuantity"].astype(float).mean()

    assert high_price_quantity < low_price_quantity


def test_financial_realism_high_value_percentages_are_controlled(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    po_lines = data["PurchaseOrderLine"].merge(master["ComponentMaster"][["ComponentID", "ComponentCategory"]], on="ComponentID")
    quote_lines = data["SupplierQuotationLn"]
    po_headers = data["PurchaseOrderHdr"]
    invoices = data["SupplierInvoice"]

    assert (po_lines["LineAmount"] >= 1_000_000).mean() < 0.05
    assert (quote_lines["QuotedLineAmount"] >= 1_000_000).mean() < 0.05
    assert (po_headers["TotalAmount"] >= 1_000_000).mean() < 0.10
    assert (invoices["TotalInvoiceAmount"] >= 1_000_000).mean() < 0.10

    packaging = po_lines[po_lines["ComponentCategory"] == "Packaging"]
    maintenance = po_lines[po_lines["ComponentCategory"] == "Maintenance"]
    assert (packaging["LineAmount"] >= 500_000).mean() <= 0.01
    assert (maintenance["LineAmount"] >= 500_000).mean() < 0.05


def test_po_schedule_total_quantity_does_not_exceed_ordered_quantity(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    grouped = data["POSchedule"].groupby("PurchaseOrderLineID")["ScheduledQuantity"].sum().reset_index()
    merged = grouped.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")
    assert (merged["ScheduledQuantity"] <= merged["OrderedQuantity"] + 0.0001).all()


def test_rfq_quote_and_po_quantities_do_not_exceed_upstream_lifecycle_quantities(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    rfq = data["RFQLine"].merge(data["PurchaseReqLine"][["RequisitionLineID", "RequestedQuantity"]], on="RequisitionLineID")
    quoted = data["SupplierQuotationLn"].merge(data["RFQLine"][["RFQLineID", "RFQQuantity"]], on="RFQLineID")
    po = data["PurchaseOrderLine"].merge(data["SupplierQuotationLn"][["QuotationLineID", "QuotedQuantity", "AwardedFlag"]], on="QuotationLineID")
    ordered_by_quote = data["PurchaseOrderLine"].groupby("QuotationLineID")["OrderedQuantity"].sum().reset_index()
    ordered_by_quote = ordered_by_quote.merge(data["SupplierQuotationLn"][["QuotationLineID", "QuotedQuantity"]], on="QuotationLineID")

    assert (rfq["RFQQuantity"] <= rfq["RequestedQuantity"] + 0.0001).all()
    assert (quoted["QuotedQuantity"] <= quoted["RFQQuantity"] + 0.0001).all()
    assert (po["AwardedFlag"] == 1).all()
    assert (po["OrderedQuantity"] <= po["QuotedQuantity"] + 0.0001).all()
    assert (ordered_by_quote["OrderedQuantity"] <= ordered_by_quote["QuotedQuantity"] + 0.0001).all()


def test_shipment_line_quantity_does_not_exceed_schedule(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["ShipmentLine"].merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID")
    assert (merged["ShippedQuantity"] <= merged["ScheduledQuantity"] + 0.0001).all()


def test_shipment_cumulative_quantities_do_not_exceed_schedule_or_po(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    by_schedule = data["ShipmentLine"].groupby("POScheduleID")["ShippedQuantity"].sum().reset_index()
    by_schedule = by_schedule.merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID")
    by_po = data["ShipmentLine"].groupby("PurchaseOrderLineID")["ShippedQuantity"].sum().reset_index()
    by_po = by_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")

    assert (by_schedule["ShippedQuantity"] <= by_schedule["ScheduledQuantity"] + 0.0001).all()
    assert (by_po["ShippedQuantity"] <= by_po["OrderedQuantity"] + 0.0001).all()


def test_goods_receipt_quantity_rules(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    lines = data["GoodsReceiptLine"]
    assert (lines["ReceivedQuantity"] <= lines["ShippedQuantity"] + 0.0001).all()
    assert (lines["DamagedQuantity"] <= lines["ReceivedQuantity"] + 0.0001).all()
    assert (abs(lines["ShortQuantity"] - (lines["ShippedQuantity"] - lines["ReceivedQuantity"])) <= 0.0001).all()


def test_goods_receipt_cumulative_quantities_do_not_exceed_shipment_or_po(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    by_shipment_line = data["GoodsReceiptLine"].groupby("ShipmentLineID")["ReceivedQuantity"].sum().reset_index()
    by_shipment_line = by_shipment_line.merge(data["ShipmentLine"][["ShipmentLineID", "ShippedQuantity"]], on="ShipmentLineID")
    by_po = data["GoodsReceiptLine"].groupby("PurchaseOrderLineID")["ReceivedQuantity"].sum().reset_index()
    by_po = by_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")

    assert (by_shipment_line["ReceivedQuantity"] <= by_shipment_line["ShippedQuantity"] + 0.0001).all()
    assert (by_po["ReceivedQuantity"] <= by_po["OrderedQuantity"] + 0.0001).all()


def test_goods_receipt_line_uses_shipment_lines_from_parent_receipt_shipment(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = (
        data["GoodsReceiptLine"]
        .merge(
            data["ShipmentLine"][["ShipmentLineID", "ShipmentID", "PurchaseOrderLineID", "ComponentID"]],
            on="ShipmentLineID",
            suffixes=("_receipt", "_shipment"),
        )
        .merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ShipmentID"]], on="GoodsReceiptID", suffixes=("_shipment", "_receipt_header"))
    )
    assert (merged["ShipmentID_shipment"] == merged["ShipmentID_receipt_header"]).all()
    assert (merged["PurchaseOrderLineID_receipt"] == merged["PurchaseOrderLineID_shipment"]).all()
    assert (merged["ComponentID_receipt"] == merged["ComponentID_shipment"]).all()


def test_inspection_result_quantities_reconcile(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    result = data["InspectionResult"]
    assert (abs((result["AcceptedQuantity"] + result["RejectedQuantity"]) - result["InspectedQuantity"]) <= 0.0001).all()


def test_inspection_cumulative_accepted_quantity_does_not_exceed_po(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    inspected = (
        data["InspectionResult"]
        .merge(data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID"]], on="InspectionID")
        .merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "ReceivedQuantity", "PurchaseOrderLineID"]], on="GoodsReceiptLineID")
    )
    accepted_by_po = inspected.groupby("PurchaseOrderLineID")["AcceptedQuantity"].sum().reset_index()
    accepted_by_po = accepted_by_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")

    assert (inspected["InspectedQuantity"] <= inspected["ReceivedQuantity"] + 0.0001).all()
    assert (accepted_by_po["AcceptedQuantity"] <= accepted_by_po["OrderedQuantity"] + 0.0001).all()


def test_inventory_transaction_quantity_equals_accepted_quantity(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["InventoryTransaction"].merge(data["InspectionResult"][["InspectionResultID", "AcceptedQuantity"]], on="InspectionResultID")
    assert (abs(merged["TransactionQuantity"] - merged["AcceptedQuantity"]) <= 0.0001).all()


def test_inventory_transaction_cumulative_stock_in_does_not_exceed_po_ordered_quantity(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    stock_in = data["InventoryTransaction"].groupby("PurchaseOrderLineID")["TransactionQuantity"].sum().reset_index()
    stock_in = stock_in.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "ComponentID", "OrderedQuantity"]], on="PurchaseOrderLineID")

    assert (stock_in["TransactionQuantity"] <= stock_in["OrderedQuantity"] + 0.0001).all()
    assert stock_in[stock_in["TransactionQuantity"] > stock_in["OrderedQuantity"] + 0.0001].empty


def test_inventory_transaction_stock_in_columns_are_populated(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    transactions = data["InventoryTransaction"]

    for column_name in [
        "GoodsReceiptLineID",
        "PurchaseOrderLineID",
        "SupplierID",
        "UnitPrice",
        "InventoryValue",
        "InventoryStatus",
    ]:
        assert column_name in transactions.columns
        assert transactions[column_name].notna().all()
    assert set(transactions["TransactionType"]) == {"StockIn"}
    assert set(transactions["InventoryStatus"]).issubset({"Posted", "QualityAccepted", "ReceivedToInventory"})


def test_inventory_transaction_receipt_and_po_lineage(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    transactions = data["InventoryTransaction"]

    assert set(transactions["GoodsReceiptLineID"]).issubset(set(data["GoodsReceiptLine"]["GoodsReceiptLineID"]))
    assert set(transactions["PurchaseOrderLineID"]).issubset(set(data["PurchaseOrderLine"]["PurchaseOrderLineID"]))
    assert set(transactions["SupplierID"]).issubset(set(master["SupplierMaster"]["SupplierID"]))

    inspection_lineage = data["InspectionResult"][["InspectionResultID", "InspectionID"]].merge(
        data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID"]],
        on="InspectionID",
    )
    merged = transactions.merge(inspection_lineage, on="InspectionResultID", suffixes=("_txn", "_inspection"))
    assert (merged["GoodsReceiptLineID_txn"] == merged["GoodsReceiptLineID_inspection"]).all()

    receipt_lineage = transactions.merge(
        data["GoodsReceiptLine"][["GoodsReceiptLineID", "PurchaseOrderLineID", "ComponentID"]],
        on="GoodsReceiptLineID",
        suffixes=("_txn", "_receipt"),
    )
    assert (receipt_lineage["PurchaseOrderLineID_txn"] == receipt_lineage["PurchaseOrderLineID_receipt"]).all()
    assert (receipt_lineage["ComponentID_txn"] == receipt_lineage["ComponentID_receipt"]).all()

    po_supplier = data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "UnitPrice"]].merge(
        data["PurchaseOrderHdr"][["PurchaseOrderID", "SupplierID"]],
        on="PurchaseOrderID",
    )
    po_lineage = transactions.merge(po_supplier, on="PurchaseOrderLineID", suffixes=("_txn", "_po"))
    assert (po_lineage["SupplierID_txn"] == po_lineage["SupplierID_po"]).all()
    assert (abs(po_lineage["UnitPrice_txn"] - po_lineage["UnitPrice_po"]) <= 0.01).all()


def test_inventory_transaction_value_is_calculated_and_rounded(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    transactions = data["InventoryTransaction"]
    expected_value = (transactions["TransactionQuantity"] * transactions["UnitPrice"]).round(2)

    assert (abs(transactions["InventoryValue"] - expected_value) <= 0.0100001).all()
    assert (transactions["InventoryValue"] >= 0).all()
    assert (transactions["InventoryValue"].map(lambda value: round(float(value), 2) == float(value))).all()


def test_inventory_row_count_matches_transaction_groups(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    grouped = data["InventoryTransaction"].groupby(["ComponentID", "PlantID", "WarehouseID"]).size().reset_index()

    assert len(data["Inventory"]) == len(grouped)


def test_inventory_primary_key_and_foreign_keys_are_valid(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    inventory = data["Inventory"]

    assert inventory["InventoryID"].notna().all()
    assert inventory["InventoryID"].is_unique
    assert set(inventory["ComponentID"]).issubset(set(master["ComponentMaster"]["ComponentID"]))
    assert set(inventory["PlantID"]).issubset(set(master["Plant"]["PlantID"]))
    assert set(inventory["WarehouseID"]).issubset(set(master["Warehouse"]["WarehouseID"]))


def test_inventory_warehouse_belongs_to_same_plant(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    merged = data["Inventory"].join(master["Warehouse"].set_index("WarehouseID")["PlantID"].rename("WarehousePlantID"), on="WarehouseID")

    assert (merged["PlantID"] == merged["WarehousePlantID"]).all()


def test_inventory_on_hand_equals_grouped_transaction_quantity(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    grouped = (
        data["InventoryTransaction"]
        .groupby(["ComponentID", "PlantID", "WarehouseID"], as_index=False)["TransactionQuantity"]
        .sum()
        .rename(columns={"TransactionQuantity": "ExpectedOnHandQuantity"})
    )
    merged = data["Inventory"].merge(grouped, on=["ComponentID", "PlantID", "WarehouseID"])

    assert (abs(merged["OnHandQuantity"] - merged["ExpectedOnHandQuantity"]) <= 0.0001).all()


def test_inventory_available_quantity_and_non_negative_rules(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    inventory = data["Inventory"]

    assert (inventory[["OnHandQuantity", "ReservedQuantity", "AvailableQuantity"]] >= 0).all().all()
    assert (inventory["ReservedQuantity"] <= inventory["OnHandQuantity"] + 0.0001).all()
    assert (abs(inventory["AvailableQuantity"] - (inventory["OnHandQuantity"] - inventory["ReservedQuantity"])) <= 0.0001).all()


def test_inventory_value_rollups_are_calculated(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    grouped = (
        data["InventoryTransaction"]
        .groupby(["ComponentID", "PlantID", "WarehouseID"], as_index=False)["InventoryValue"]
        .sum()
        .rename(columns={"InventoryValue": "ExpectedOnHandValue"})
    )
    inventory = data["Inventory"].merge(grouped, on=["ComponentID", "PlantID", "WarehouseID"])
    average_unit_cost = inventory["OnHandValue"].where(inventory["OnHandQuantity"] > 0, 0) / inventory["OnHandQuantity"].where(
        inventory["OnHandQuantity"] > 0,
        1,
    )
    expected_available_value = (inventory["AvailableQuantity"] * average_unit_cost).round(2)

    assert (abs(inventory["OnHandValue"] - inventory["ExpectedOnHandValue"]) <= 0.01).all()
    assert (abs(inventory["AvailableValue"] - expected_available_value) <= 0.01).all()
    assert (inventory[["OnHandValue", "AvailableValue"]] >= 0).all().all()
    assert (inventory["AvailableValue"] <= inventory["OnHandValue"] + 0.01).all()


def test_inventory_last_transaction_and_updated_dates(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    grouped = (
        data["InventoryTransaction"]
        .groupby(["ComponentID", "PlantID", "WarehouseID"], as_index=False)["TransactionDate"]
        .max()
        .rename(columns={"TransactionDate": "ExpectedLastTransactionDate"})
    )
    merged = data["Inventory"].merge(grouped, on=["ComponentID", "PlantID", "WarehouseID"])

    assert (_dt(merged["LastTransactionDate"]) == _dt(merged["ExpectedLastTransactionDate"])).all()
    assert (_dt(merged["LastUpdatedDate"]) >= _dt(merged["LastTransactionDate"])).all()


def test_inventory_status_values_logic_and_diversity(generated_v2_transactions) -> None:
    schema, _, _, data = generated_v2_transactions
    inventory = data["Inventory"].copy()
    allowed = next(column.allowed_values for column in schema.tables["Inventory"].columns if column.column_name == "InventoryStatus")

    assert set(inventory["InventoryStatus"]).issubset(set(allowed))
    expected = inventory.apply(_expected_inventory_status, axis=1)
    assert (inventory["InventoryStatus"] == expected).all()
    assert "Available" in set(inventory["InventoryStatus"])
    if len(inventory) >= 10:
        assert inventory["InventoryStatus"].nunique() > 1


def test_supplier_invoice_date_is_after_receipt(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["SupplierInvoice"].merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ReceiptDate"]], on="GoodsReceiptID")
    assert (_dt(merged["InvoiceDate"]) >= _dt(merged["ReceiptDate"])).all()


def test_payment_date_and_amount_are_valid(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["PaymentTransaction"].merge(data["SupplierInvoice"][["SupplierInvoiceID", "InvoiceDate", "TotalInvoiceAmount"]], on="SupplierInvoiceID")
    assert (_dt(merged["PaymentDate"]) >= _dt(merged["InvoiceDate"])).all()
    assert (merged["PaymentAmount"] <= merged["TotalInvoiceAmount"] + 0.0001).all()


def test_invoice_tax_and_payment_amount_ranges_respect_metadata(generated_v2_transactions) -> None:
    schema, _, _, data = generated_v2_transactions
    tax_column = next(column for column in schema.tables["SupplierInvoice"].columns if column.column_name == "TaxAmount")
    payment_column = next(column for column in schema.tables["PaymentTransaction"].columns if column.column_name == "PaymentAmount")
    assert data["SupplierInvoice"]["TaxAmount"].between(float(tax_column.min_value), float(tax_column.max_value)).all()
    assert data["PaymentTransaction"]["PaymentAmount"].between(float(payment_column.min_value), float(payment_column.max_value)).all()


def test_payment_status_aligns_with_payment_amount(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    merged = data["PaymentTransaction"].merge(data["SupplierInvoice"][["SupplierInvoiceID", "TotalInvoiceAmount"]], on="SupplierInvoiceID")
    zero = merged["PaymentAmount"].eq(0)
    partial = merged["PaymentAmount"].gt(0) & (merged["PaymentAmount"] < merged["TotalInvoiceAmount"])
    paid = merged["PaymentAmount"] >= merged["TotalInvoiceAmount"]
    assert merged.loc[zero, "PaymentStatus"].isin(["Pending", "Failed"]).all()
    assert merged.loc[partial, "PaymentStatus"].eq("PartiallyPaid").all()
    assert merged.loc[paid, "PaymentStatus"].eq("Paid").all()


def test_po_statuses_are_derived_from_stock_in_lifecycle(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    stock_in_by_line = data["InventoryTransaction"].groupby("PurchaseOrderLineID")["TransactionQuantity"].sum().reset_index(name="TotalStockInQuantity")
    line_status = data["PurchaseOrderLine"].merge(stock_in_by_line, on="PurchaseOrderLineID", how="left").fillna({"TotalStockInQuantity": 0})
    partial_closed = line_status["LineStatus"].eq("Closed") & (line_status["TotalStockInQuantity"] < line_status["OrderedQuantity"] - 0.0001)

    assert not partial_closed.any()

    po_totals = (
        line_status.groupby("PurchaseOrderID", as_index=False)
        .agg(TotalOrderedQuantity=("OrderedQuantity", "sum"), TotalStockInQuantity=("TotalStockInQuantity", "sum"))
        .merge(data["PurchaseOrderHdr"][["PurchaseOrderID", "POStatus"]], on="PurchaseOrderID")
    )
    closed_partial = po_totals["POStatus"].eq("Closed") & (po_totals["TotalStockInQuantity"] < po_totals["TotalOrderedQuantity"] - 0.0001)
    assert not closed_partial.any()


def test_receipt_and_inspection_statuses_follow_quantities(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    receipt_status = data["GoodsReceiptHeader"][["GoodsReceiptID", "ReceiptStatus"]].merge(
        data["GoodsReceiptLine"].groupby("GoodsReceiptID", as_index=False).agg(
            TotalShortQuantity=("ShortQuantity", "sum"),
            TotalDamagedQuantity=("DamagedQuantity", "sum"),
        ),
        on="GoodsReceiptID",
    )
    bad_receipts = receipt_status["ReceiptStatus"].isin(["Received", "Closed"]) & (
        (receipt_status["TotalShortQuantity"] > 0.0001) | (receipt_status["TotalDamagedQuantity"] > 0.0001)
    )
    assert not bad_receipts.any()

    result = data["InspectionResult"]
    passed = result["RejectedQuantity"].eq(0) & result["ResultStatus"].eq("Passed")
    partial = result["RejectedQuantity"].gt(0) & result["AcceptedQuantity"].gt(0) & result["ResultStatus"].eq("PartiallyRejected")
    failed = result["RejectedQuantity"].gt(0) & result["AcceptedQuantity"].eq(0) & result["ResultStatus"].eq("Failed")
    assert (passed | partial | failed).all()


def test_currency_code_is_usd_for_financial_tables(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    for table_name in ["SupplierQuotation", "PurchaseOrderHdr", "SupplierInvoice", "PaymentTransaction"]:
        assert set(data[table_name]["CurrencyCode"]) == {"USD"}


def test_warehouse_belongs_to_same_plant(generated_v2_transactions) -> None:
    _, _, master, data = generated_v2_transactions
    warehouse_lookup = master["Warehouse"].set_index("WarehouseID")["PlantID"]
    for table_name in ["GoodsReceiptHeader", "InventoryTransaction"]:
        merged = data[table_name].join(warehouse_lookup.rename("WarehousePlantID"), on="WarehouseID")
        assert (merged["PlantID"] == merged["WarehousePlantID"]).all()


def test_status_values_are_within_allowed_values(generated_v2_transactions) -> None:
    schema, _, _, data = generated_v2_transactions
    for table_name in EXPECTED_TABLES:
        table = schema.tables[table_name]
        for column in table.columns:
            if column.allowed_values:
                assert set(map(str, data[table_name][column.column_name].dropna())).issubset(set(map(str, column.allowed_values)))


def test_key_status_columns_have_diversity(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    for table_name, column_name in [
        ("PurchaseOrderHdr", "POStatus"),
        ("PurchaseOrderLine", "LineStatus"),
        ("ShipmentHdr", "ShipmentStatus"),
        ("GoodsReceiptHeader", "ReceiptStatus"),
        ("IncomingInspection", "InspectionStatus"),
        ("InspectionResult", "ResultStatus"),
        ("SupplierInvoice", "InvoiceStatus"),
        ("PaymentTransaction", "PaymentStatus"),
    ]:
        assert data[table_name][column_name].nunique() > 1
    assert set(data["InventoryTransaction"]["TransactionType"]) == {"StockIn"}


def test_rejection_reason_logic_and_variety(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    result = data["InspectionResult"]
    zero = result[result["RejectedQuantity"] == 0]
    rejected = result[result["RejectedQuantity"] > 0]
    assert zero["RejectionReason"].fillna("").isin(["", "Not Applicable"]).all()
    assert not rejected.empty
    assert rejected["RejectionReason"].nunique() > 1


def test_realistic_exception_events_exist(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    shipment_lines = data["ShipmentLine"].merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID")
    assert (shipment_lines["ShippedQuantity"] < shipment_lines["ScheduledQuantity"]).any()
    delayed = data["ShipmentHdr"].merge(data["PurchaseOrderHdr"][["PurchaseOrderID", "ExpectedDeliveryDate"]], on="PurchaseOrderID")
    assert (_dt(delayed["ShipmentDate"]) > _dt(delayed["ExpectedDeliveryDate"])).any()
    assert (data["GoodsReceiptLine"]["ShortQuantity"] > 0).any()
    assert (data["InspectionResult"]["RejectedQuantity"] > 0).any()


def test_invoice_and_payment_status_behaviors_exist(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    assert {"Paid", "PartiallyPaid", "Pending"}.issubset(set(data["PaymentTransaction"]["PaymentStatus"]))
    assert {"Paid", "PartiallyPaid"}.issubset(set(data["SupplierInvoice"]["InvoiceStatus"]))


def test_quotation_status_and_line_status_align_with_awards(generated_v2_transactions) -> None:
    _, _, _, data = generated_v2_transactions
    lines = data["SupplierQuotationLn"]
    assert lines.loc[lines["AwardedFlag"] == 1, "LineStatus"].eq("Awarded").all()
    assert lines.loc[lines["AwardedFlag"] == 0, "LineStatus"].isin(["Rejected", "Quoted"]).all()
    awarded_by_quote = lines.groupby("QuotationID")["AwardedFlag"].sum().reset_index()
    merged = data["SupplierQuotation"].merge(awarded_by_quote, on="QuotationID", how="left")
    assert merged.loc[merged["AwardedFlag"].fillna(0) > 0, "QuotationStatus"].eq("Awarded").all()


def test_same_seed_produces_deterministic_v2_transactions(generated_v2_transactions) -> None:
    schema, plan, master, _ = generated_v2_transactions
    first, first_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master, seed=42, model_version="v2")
    second, second_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master, seed=42, model_version="v2")
    assert first_report.is_valid
    assert second_report.is_valid
    for table_name in first:
        pdt.assert_frame_equal(first[table_name], second[table_name])


def test_different_seed_changes_some_v2_transaction_values(generated_v2_transactions) -> None:
    schema, plan, master, _ = generated_v2_transactions
    first, first_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master, seed=42, model_version="v2")
    second, second_report = ProcurementTransactionGenerator().generate_transaction_data(schema, plan, master, seed=99, model_version="v2")
    assert first_report.is_valid
    assert second_report.is_valid
    assert any(not first[table_name].equals(second[table_name]) for table_name in first)


def _dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series)


def _expected_inventory_status(row) -> str:
    on_hand = float(row["OnHandQuantity"])
    available = float(row["AvailableQuantity"])
    if on_hand <= 0:
        return "OutOfStock"
    if available <= 0:
        return "Hold"
    if available <= on_hand * 0.10:
        return "LowStock"
    return "Available"
