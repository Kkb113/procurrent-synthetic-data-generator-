from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.core.validation.reconciler import ProcurementDataQualityEngine
from procurement_data_generator.core.validation.data_validator import GeneratedDataValidator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V2_TABLES = {
    "SupplierMaster",
    "SupplierComponent",
    "ComponentMaster",
    "Plant",
    "Warehouse",
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
    "InventoryReceiptDetail",
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
}


def test_v2_generated_data_has_all_expected_tables_for_validation() -> None:
    report = _validate(_clean_v2_data())

    assert V2_TABLES.issubset(report.table_summaries)
    assert not _has_issue(report, "V2_EXPECTED_TABLE")
    assert not _has_issue(report, "V2_NO_INVENTORY_BALANCE")


def test_v2_inventory_balance_present_fails() -> None:
    data = _clean_v2_data()
    data["InventoryBalance"] = pd.DataFrame({"InventoryBalanceID": [1]})

    report = _validate(data)

    assert _has_issue(report, "V2_NO_INVENTORY_BALANCE")


def test_v2_inventory_table_missing_fails() -> None:
    data = _clean_v2_data()
    data.pop("Inventory")

    report = _validate(data)

    assert _has_issue(report, "TABLE_EXISTENCE")
    assert _has_issue(report, "V2_EXPECTED_TABLE")


def test_v2_inventory_receipt_detail_missing_fails() -> None:
    data = _clean_v2_data()
    data.pop("InventoryReceiptDetail")

    report = _validate(data)

    assert _has_issue(report, "TABLE_EXISTENCE")
    assert _has_issue(report, "V2_EXPECTED_TABLE")


def test_v2_missing_table_fails() -> None:
    data = _clean_v2_data()
    data.pop("SupplierInvoice")

    report = _validate(data)

    assert _has_issue(report, "TABLE_EXISTENCE")
    assert _has_issue(report, "V2_EXPECTED_TABLE")


def test_v2_duplicate_pk_fails() -> None:
    data = _clean_v2_data()
    data["SupplierMaster"].loc[1, "SupplierID"] = data["SupplierMaster"].loc[0, "SupplierID"]

    report = _validate(data)

    assert _has_issue(report, "PK_UNIQUE")


def test_v2_fk_orphan_fails() -> None:
    data = _clean_v2_data()
    data["SupplierComponent"].loc[0, "SupplierID"] = 999999

    report = _validate(data)

    assert _has_issue(report, "FK_INTEGRITY")


def test_v2_inventory_fk_orphans_fail() -> None:
    data = _clean_v2_data()
    data["Inventory"].loc[0, "ComponentID"] = 999999
    data["Inventory"].loc[1, "PlantID"] = 999999
    data["Inventory"].loc[2, "WarehouseID"] = 999999

    report = _validate(data)

    assert _has_issue(report, "FK_INTEGRITY")


def test_v2_usa_country_checks_fail_on_non_usa_values() -> None:
    data = _clean_v2_data()
    data["SupplierMaster"].loc[0, "SupplierCountry"] = "Canada"
    data["Plant"].loc[0, "PlantCountry"] = "Mexico"
    data["Warehouse"].loc[0, "WarehouseCountry"] = "Germany"

    report = _validate(data)

    assert _has_issue(report, "V2_USA_SUPPLIER_COUNTRY")
    assert _has_issue(report, "V2_USA_PLANT_COUNTRY")
    assert _has_issue(report, "V2_USA_WAREHOUSE_COUNTRY")


def test_v2_usd_currency_check_fails_on_non_usd_value() -> None:
    data = _clean_v2_data()
    data["SupplierInvoice"].loc[0, "CurrencyCode"] = "EUR"

    report = _validate(data)

    assert _has_issue(report, "V2_USD_CURRENCY")


def test_v2_warehouse_location_must_match_plant() -> None:
    data = _clean_v2_data()
    data["Warehouse"].loc[0, "WarehouseCity"] = "Seattle"

    report = _validate(data)

    assert _has_issue(report, "V2_WAREHOUSE_PLANT_LOCATION")


def test_v2_invalid_status_value_fails_allowed_values() -> None:
    data = _clean_v2_data()
    data["PurchaseOrderHdr"].loc[0, "POStatus"] = "Impossible"
    data["Inventory"].loc[0, "InventoryStatus"] = "Impossible"
    data["InventoryTransaction"].loc[0, "TransactionType"] = "Receipt"
    data["InventoryTransaction"].loc[1, "InventoryStatus"] = "Impossible"

    report = _validate(data)

    assert _has_issue(report, "ALLOWED_VALUES")


def test_v2_inventory_transaction_refined_fk_orphans_fail() -> None:
    data = _clean_v2_data()
    data["InventoryTransaction"].loc[0, "GoodsReceiptLineID"] = 999999
    data["InventoryTransaction"].loc[1, "PurchaseOrderLineID"] = 999999
    data["InventoryTransaction"].loc[2, "SupplierID"] = 999999

    report = _validate(data)

    assert _has_issue(report, "FK_INTEGRITY")


def test_v2_inventory_refined_value_ranges_fail_on_negative_values() -> None:
    data = _clean_v2_data()
    data["InventoryTransaction"].loc[0, "InventoryValue"] = -1.0
    data["Inventory"].loc[0, "OnHandValue"] = -1.0
    data["Inventory"].loc[1, "AvailableValue"] = -1.0

    report = _validate(data)

    assert _has_issue(report, "NUMERIC_RANGE")


def test_v2_single_status_value_warns_when_allowed_values_are_diverse() -> None:
    data = _clean_v2_data()
    data["PurchaseRequisition"]["Status"] = "Draft"

    report = _validate(data)

    assert _has_issue(report, "V2_STATUS_DIVERSITY", level="warning")


def test_v2_inventory_row_count_target_mismatch_is_warning_only() -> None:
    report = _validate(_clean_v2_data())

    inventory_row_count_issues = [
        issue
        for issue in report.issues
        if issue.check_type == "ROW_COUNT" and issue.table_name == "Inventory"
    ]

    assert inventory_row_count_issues
    assert all(issue.level == "warning" for issue in inventory_row_count_issues)


def test_v2_inventory_one_status_value_warns_but_out_of_stock_absence_does_not() -> None:
    data = _clean_v2_data()
    data["Inventory"]["InventoryStatus"] = "Available"

    report = _validate(data)

    assert _has_issue(report, "V2_STATUS_DIVERSITY", level="warning")
    assert not any("OutOfStock" in issue.message for issue in report.warnings)


def test_v2_data_quality_engine_fails_when_stock_in_exceeds_ordered_quantity() -> None:
    data = _clean_v2_data()
    stock_in = data["InventoryTransaction"].groupby("PurchaseOrderLineID")["TransactionQuantity"].sum().reset_index()
    candidate = stock_in[stock_in["TransactionQuantity"] > 0].iloc[0]
    purchase_order_line_id = candidate["PurchaseOrderLineID"]
    data["PurchaseOrderLine"].loc[data["PurchaseOrderLine"]["PurchaseOrderLineID"] == purchase_order_line_id, "OrderedQuantity"] = max(
        float(candidate["TransactionQuantity"]) - 1.0,
        0.01,
    )

    report = _validate_and_reconcile(data)

    assert _has_issue(report, "INVENTORY_TRANSACTION_CUMULATIVE_EXCEEDS_ORDERED")


def test_v2_countable_component_decimal_quantity_fails_data_validation() -> None:
    data = _clean_v2_data()
    component_id = data["PurchaseOrderLine"].loc[0, "ComponentID"]
    data["ComponentMaster"].loc[data["ComponentMaster"]["ComponentID"] == component_id, "UOM"] = "EA"
    data["PurchaseOrderLine"].loc[0, "OrderedQuantity"] = float(data["PurchaseOrderLine"].loc[0, "OrderedQuantity"]) + 0.5

    report = _validate(data)

    assert _has_issue(report, "V2_INTEGER_QUANTITY_PRECISION")


def test_v2_data_validation_enforces_single_plant_and_warehouse() -> None:
    data = _single_scope_v2_data()
    data["Plant"] = pd.concat([data["Plant"], data["Plant"].iloc[[0]].assign(PlantID=999999)], ignore_index=True)
    data["Warehouse"] = pd.concat([data["Warehouse"], data["Warehouse"].iloc[[0]].assign(WarehouseID=999999)], ignore_index=True)

    report = _validate(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_PLANT_COUNT")
    assert _has_issue(report, "V2_OPERATING_SCOPE_WAREHOUSE_COUNT")


def test_v2_data_validation_enforces_single_location_references() -> None:
    data = _single_scope_v2_data()
    data["InventoryReceiptDetail"].loc[0, "PlantID"] = 999999
    data["InventoryTransaction"].loc[0, "WarehouseID"] = 999999

    report = _validate(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_PLANT_REFERENCE")
    assert _has_issue(report, "V2_OPERATING_SCOPE_WAREHOUSE_REFERENCE")


def _validate(dataframes: dict[str, pd.DataFrame]):
    schema_result = load_metadata_schema(PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx")
    assert schema_result.schema is not None
    return GeneratedDataValidator().validate_dataset(dataframes, schema_result.schema, model_version="v2")


def _validate_and_reconcile(dataframes: dict[str, pd.DataFrame]):
    schema_result = load_metadata_schema(PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx")
    assert schema_result.schema is not None
    return ProcurementDataQualityEngine().validate_and_reconcile(dataframes, schema_result.schema, model_version="v2")


def _clean_v2_data() -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    for folder_name in ("v2_master_data", "v2_transaction_data", "v2_formula_data"):
        for path in (PROJECT_ROOT / "output" / folder_name).glob("*.csv"):
            data[path.stem] = pd.read_csv(path)

    invoices = data["SupplierInvoice"].copy()
    invoices["TaxAmount"] = 100.0
    invoices["FreightAmount"] = 50.0
    invoices["TotalInvoiceAmount"] = invoices["InvoiceAmount"] + invoices["TaxAmount"] + invoices["FreightAmount"]
    data["SupplierInvoice"] = invoices

    payments = data["PaymentTransaction"].copy()
    payments["PaymentAmount"] = payments["PaymentAmount"].clip(upper=999999.0)
    data["PaymentTransaction"] = payments
    return data


def _single_scope_v2_data() -> dict[str, pd.DataFrame]:
    data = _clean_v2_data()
    plant_id = data["Plant"].loc[0, "PlantID"]
    warehouse_id = data["Warehouse"].loc[0, "WarehouseID"]
    data["Plant"] = data["Plant"].iloc[[0]].copy()
    data["Warehouse"] = data["Warehouse"].iloc[[0]].copy()
    data["Warehouse"]["PlantID"] = plant_id
    for dataframe in data.values():
        if "PlantID" in dataframe.columns:
            dataframe["PlantID"] = plant_id
        if "WarehouseID" in dataframe.columns:
            dataframe["WarehouseID"] = warehouse_id
    return data


def _has_issue(report, check_type: str, level: str = "error") -> bool:
    return any(issue.check_type == check_type and issue.level == level for issue in report.issues)
