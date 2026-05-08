from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.erd.erd_validator import validate_erd_relationships
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.role_validator import validate_procurement_roles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"
SCENARIO = PROJECT_ROOT / "input" / "procurement_v2_business_scenario.txt"

EXPECTED_TABLES = {
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
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
}


def test_procurement_v2_metadata_fixture_exists() -> None:
    assert METADATA.exists()


def test_procurement_v2_erd_fixture_exists() -> None:
    assert ERD.exists()


def test_procurement_v2_business_scenario_fixture_exists() -> None:
    assert SCENARIO.exists()


def test_procurement_v2_metadata_loads_successfully() -> None:
    result = load_metadata_schema(METADATA)

    assert result.schema is not None
    assert result.report.is_valid


def test_procurement_v2_metadata_validation_has_zero_errors() -> None:
    result = load_metadata_schema(METADATA)

    assert result.report.errors == []


def test_procurement_v2_role_validation_passes_with_24_roles() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    role_result = validate_procurement_roles(result.schema, model_version="v2")

    assert role_result.report.is_valid
    assert role_result.summary.expected_roles == 24
    assert role_result.summary.detected_roles == 24
    assert role_result.summary.unsupported_roles == 0
    assert role_result.summary.duplicate_roles == 0


def test_inventory_balance_is_not_present() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    assert "InventoryBalance" not in result.schema.tables
    assert all(table.table_role != "inventory_balance" for table in result.schema.tables.values())


def test_all_expected_24_tables_are_present() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    assert set(result.schema.tables) == EXPECTED_TABLES


def test_inventory_table_is_present_with_required_columns() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    inventory = result.schema.tables["Inventory"]
    columns = {column.column_name for column in inventory.columns}

    assert inventory.area == "Inventory"
    assert inventory.table_role == "inventory"
    assert {
        "InventoryID",
        "ComponentID",
        "PlantID",
        "WarehouseID",
        "OnHandQuantity",
        "ReservedQuantity",
        "AvailableQuantity",
        "OnHandValue",
        "AvailableValue",
        "LastTransactionDate",
        "LastUpdatedDate",
        "InventoryStatus",
    }.issubset(columns)


def test_inventory_transaction_has_refined_stockin_traceability_columns() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    inventory_transaction = result.schema.tables["InventoryTransaction"]
    columns = {column.column_name for column in inventory_transaction.columns}

    assert {
        "InventoryTransactionID",
        "InspectionResultID",
        "GoodsReceiptLineID",
        "PurchaseOrderLineID",
        "SupplierID",
        "ComponentID",
        "PlantID",
        "WarehouseID",
        "TransactionDate",
        "TransactionType",
        "TransactionQuantity",
        "UnitPrice",
        "InventoryValue",
        "ReferenceDocument",
        "InventoryStatus",
    }.issubset(columns)
    assert _column(inventory_transaction, "GoodsReceiptLineID").related_table == "GoodsReceiptLine"
    assert _column(inventory_transaction, "PurchaseOrderLineID").related_table == "PurchaseOrderLine"
    assert _column(inventory_transaction, "SupplierID").related_table == "SupplierMaster"
    assert _column(inventory_transaction, "TransactionType").allowed_values == ["StockIn"]
    assert _column(inventory_transaction, "InventoryValue").formula == "TransactionQuantity * UnitPrice"


def test_inventory_has_expected_foreign_keys_and_status_values() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    inventory = result.schema.tables["Inventory"]

    assert _column(inventory, "ComponentID").related_table == "ComponentMaster"
    assert _column(inventory, "ComponentID").related_column == "ComponentID"
    assert _column(inventory, "PlantID").related_table == "Plant"
    assert _column(inventory, "PlantID").related_column == "PlantID"
    assert _column(inventory, "WarehouseID").related_table == "Warehouse"
    assert _column(inventory, "WarehouseID").related_column == "WarehouseID"
    assert _column(inventory, "InventoryStatus").allowed_values == [
        "Available",
        "LowStock",
        "OutOfStock",
        "Hold",
    ]


def test_finance_area_is_used_by_invoice_and_payment_tables() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    assert result.schema.tables["SupplierInvoice"].area == "Finance"
    assert result.schema.tables["PaymentTransaction"].area == "Finance"


def test_warehouse_location_columns_are_present() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    columns = {column.column_name for column in result.schema.tables["Warehouse"].columns}

    assert {
        "WarehouseLocation",
        "WarehouseCity",
        "WarehouseState",
        "WarehouseCountry",
        "WarehouseZipCode",
    }.issubset(columns)


def test_plant_and_warehouse_country_allowed_values_include_usa() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    plant_country = _column(result.schema.tables["Plant"], "PlantCountry")
    warehouse_country = _column(result.schema.tables["Warehouse"], "WarehouseCountry")

    assert "USA" in plant_country.allowed_values
    assert "USA" in warehouse_country.allowed_values


def test_currency_code_fields_have_usd_allowed_value() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    currency_columns = [
        column
        for table in result.schema.tables.values()
        for column in table.columns
        if column.column_name == "CurrencyCode"
    ]

    assert currency_columns
    assert all(column.allowed_values == ["USD"] for column in currency_columns)


def test_status_columns_have_multiple_allowed_values_where_appropriate() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    status_columns = [
        column
        for table in result.schema.tables.values()
        for column in table.columns
        if column.generation_type == "status"
    ]

    assert status_columns
    assert all(len(column.allowed_values) > 1 or column.column_name == "TransactionType" for column in status_columns)
    assert _column(result.schema.tables["InventoryTransaction"], "TransactionType").allowed_values == ["StockIn"]


def test_erd_validation_passes_without_errors() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    relationships = parse_mermaid_erd_file(ERD)
    erd_result = validate_erd_relationships(result.schema, relationships)

    assert erd_result.report.errors == []
    assert erd_result.report.is_valid
    assert erd_result.summary.metadata_fk_relationships_checked == 52
    assert erd_result.summary.matched_relationships == 52


def test_erd_includes_inventory_relationships_and_excludes_inventory_balance() -> None:
    erd_text = ERD.read_text(encoding="utf-8")

    assert "ComponentMaster ||--o{ Inventory : inventory_component" in erd_text
    assert "Plant ||--o{ Inventory : inventory_plant" in erd_text
    assert "Warehouse ||--o{ Inventory : inventory_warehouse" in erd_text
    assert "SupplierMaster ||--o{ InventoryTransaction : supplied_inventory" in erd_text
    assert "GoodsReceiptLine ||--o{ InventoryTransaction : received_inventory_line" in erd_text
    assert "PurchaseOrderLine ||--o{ InventoryTransaction : inventory_po_line" in erd_text
    assert "InventoryBalance" not in erd_text


def test_business_scenario_mentions_inventory_balance_concept_without_inventory_balance_table() -> None:
    scenario = SCENARIO.read_text(encoding="utf-8")

    assert "InventoryTransaction as the detailed inbound stock posting ledger" in scenario
    assert "accepted StockIn posting" in scenario
    assert "unit price, inventory value" in scenario
    assert "Inventory as the current calculated stock balance" in scenario
    assert "Inventory.OnHandQuantity" in scenario
    assert "Inventory.OnHandValue" in scenario
    assert "Inventory.AvailableQuantity" in scenario
    assert "Inventory.AvailableValue" in scenario
    assert "InventoryBalance" not in scenario


def test_procurement_v2_metadata_shape_and_target_rows() -> None:
    metadata_df = pd.read_excel(METADATA, sheet_name="Metadata", engine="openpyxl", dtype=object)

    assert len(metadata_df) == 205
    assert metadata_df["TableName"].nunique() == 24
    assert metadata_df.drop_duplicates("TableName")["TargetRows"].sum() == 84242


def _column(table, column_name: str):
    return next(column for column in table.columns if column.column_name == column_name)
