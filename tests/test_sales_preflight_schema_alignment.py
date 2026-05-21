from pathlib import Path

import pytest

from procurement_data_generator.core.metadata.metadata_reader import read_metadata_schema


REPORT_PATH = Path("docs/sales_preflight_schema_alignment.md")

SALES_V1_TABLES = (
    "CustomerMaster",
    "CustomerLocation",
    "SalesChannel",
    "SalesPriceListHeader",
    "SalesPriceListLine",
    "SalesOrderHdr",
    "SalesOrderLine",
    "SalesInventoryReservation",
    "SalesPickListHeader",
    "SalesPickListLine",
    "SalesShipmentHeader",
    "SalesShipmentLine",
    "SalesInvoiceHeader",
    "SalesInvoiceLine",
    "CustomerPaymentReceipt",
    "SalesReturnHeader",
    "SalesReturnLine",
    "SalesShipmentTraceability",
)

PRODUCTION_DEPENDENCY_COLUMNS = {
    "ProductMaster": {"ProductID"},
    "FinishedGoodsReceipt": {
        "FinishedGoodsReceiptID",
        "ProductionBatchID",
        "ProductionOrderLineID",
        "ProductID",
        "PlantID",
        "WarehouseID",
        "GoodQuantity",
        "UnitCost",
    },
    "FinishedGoodsInventory": {
        "FinishedGoodsInventoryID",
        "ProductID",
        "PlantID",
        "WarehouseID",
        "OnHandQuantity",
        "ReservedQuantity",
        "AvailableQuantity",
        "OnHandValue",
    },
    "ProductionBatch": {"ProductionBatchID", "ProductionOrderLineID", "ProductID", "PlantID"},
    "ProductionGenealogy": {
        "ProductionGenealogyID",
        "FinishedGoodsReceiptID",
        "ProductionBatchID",
        "MaterialIssueLineID",
        "ComponentID",
        "InventoryReceiptDetailID",
        "SourceInventoryTransactionID",
        "SupplierID",
    },
    "ProductionCostSummary": {"ProductionBatchID", "ProductID", "UnitProductionCost"},
    "MaterialIssueLine": {
        "MaterialIssueLineID",
        "ComponentID",
        "SourceInventoryTransactionID",
        "InventoryReceiptDetailID",
        "UnitCost",
        "IssueValue",
    },
    "ProductionOrderLine": {"ProductionOrderLineID", "ProductionOrderID", "ProductID", "GoodQuantity"},
    "ProductionOrderHdr": {"ProductionOrderID", "PlantID"},
}

PROCUREMENT_DEPENDENCY_COLUMNS = {
    "SupplierMaster": {"SupplierID"},
    "ComponentMaster": {"ComponentID"},
    "InventoryReceiptDetail": {
        "InventoryReceiptDetailID",
        "SupplierID",
        "ComponentID",
        "AcceptedQuantity",
        "DeliveredUnitPrice",
        "AcceptedStockValue",
    },
    "InventoryTransaction": {
        "InventoryTransactionID",
        "SupplierID",
        "ComponentID",
        "TransactionQuantity",
        "UnitPrice",
        "InventoryValue",
    },
}


@pytest.mark.unit
def test_sales_preflight_report_exists_and_lists_v1_scope() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")

    for table_name in SALES_V1_TABLES:
        assert table_name in text
    assert "SalesCreditMemo" in text
    assert "explicitly excluded from Sales v1" in text
    assert "Sales must start from Production finished goods inventory" in text
    assert "must not consume raw Procurement `Inventory` directly" in text


@pytest.mark.unit
def test_sales_preflight_report_documents_core_dependency_findings() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")

    for dependency in (
        "ProductID",
        "FinishedGoodsInventoryID",
        "FinishedGoodsReceiptID",
        "ProductionBatchID",
        "ProductionGenealogyID",
        "MaterialIssueLineID",
        "InventoryReceiptDetailID",
        "SupplierID",
        "ComponentID",
    ):
        assert dependency in text
    assert "Use Option C" in text
    assert "FinishedGoodsReceipt.UnitCost" in text
    assert "ProductionCostSummary.UnitProductionCost" in text
    assert "OnHandQuantity =" in text
    assert "Supplier-to-customer traceability is feasible" in text


@pytest.mark.unit
def test_current_production_metadata_has_sales_upstream_columns() -> None:
    schema = read_metadata_schema("input/production_v1_metadata.xlsx")

    for table_name, expected_columns in PRODUCTION_DEPENDENCY_COLUMNS.items():
        actual_columns = {column.column_name for column in schema.tables[table_name].columns}
        assert expected_columns <= actual_columns


@pytest.mark.unit
def test_current_procurement_metadata_has_sales_traceability_columns() -> None:
    schema = read_metadata_schema("input/procurement_v2_metadata.xlsx")

    for table_name, expected_columns in PROCUREMENT_DEPENDENCY_COLUMNS.items():
        actual_columns = {column.column_name for column in schema.tables[table_name].columns}
        assert expected_columns <= actual_columns


@pytest.mark.unit
def test_sales_preflight_report_records_sales_currently_implemented() -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")

    assert "Sales Phase 10 enabled generic backend execution" in text
    assert "Sales Phase 11 activated Sales in the browser/API generic workflow" in text
    assert Path("procurement_data_generator/modules/sales").exists()
