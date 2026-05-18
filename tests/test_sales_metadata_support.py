from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.metadata.metadata_reader import read_metadata_schema
from procurement_data_generator.core.metadata.metadata_validator import validate_metadata_dataframe
from procurement_data_generator.modules.sales.metadata import build_sales_v1_metadata_dataframe
from procurement_data_generator.modules.sales.plugin import SalesModulePlugin
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES


SALES_METADATA = Path("input/sales_v1_metadata.xlsx")


@pytest.mark.unit
def test_sales_metadata_fixture_includes_exactly_approved_tables() -> None:
    schema = read_metadata_schema(SALES_METADATA)

    assert tuple(schema.tables) == SALES_V1_EXPECTED_TABLES
    assert len(schema.tables) == 18
    assert "SalesCreditMemo" not in schema.tables


@pytest.mark.unit
def test_sales_metadata_builder_validates_with_core_metadata_contract() -> None:
    result = validate_metadata_dataframe(build_sales_v1_metadata_dataframe())

    assert result.report.is_valid
    assert result.schema is not None
    assert len(result.schema.tables) == 18


@pytest.mark.unit
def test_sales_metadata_includes_required_primary_keys() -> None:
    schema = read_metadata_schema(SALES_METADATA)

    expected_pks = {
        "CustomerMaster": "CustomerID",
        "CustomerLocation": "CustomerLocationID",
        "SalesChannel": "SalesChannelID",
        "SalesPriceListHeader": "PriceListID",
        "SalesPriceListLine": "PriceListLineID",
        "SalesOrderHdr": "SalesOrderID",
        "SalesOrderLine": "SalesOrderLineID",
        "SalesInventoryReservation": "ReservationID",
        "SalesPickListHeader": "PickListID",
        "SalesPickListLine": "PickListLineID",
        "SalesShipmentHeader": "ShipmentID",
        "SalesShipmentLine": "ShipmentLineID",
        "SalesInvoiceHeader": "InvoiceID",
        "SalesInvoiceLine": "InvoiceLineID",
        "CustomerPaymentReceipt": "PaymentReceiptID",
        "SalesReturnHeader": "SalesReturnID",
        "SalesReturnLine": "SalesReturnLineID",
        "SalesShipmentTraceability": "SalesTraceabilityID",
    }
    for table_name, pk_column in expected_pks.items():
        table = schema.tables[table_name]
        pks = [column.column_name for column in table.columns if column.key_type == "PK"]
        assert pks == [pk_column]


@pytest.mark.unit
def test_sales_metadata_includes_key_upstream_foreign_keys() -> None:
    schema = read_metadata_schema(SALES_METADATA)

    expected_fks = {
        ("SalesOrderLine", "ProductID"): ("ProductMaster", "ProductID"),
        ("SalesInventoryReservation", "FinishedGoodsInventoryID"): ("FinishedGoodsInventory", "FinishedGoodsInventoryID"),
        ("SalesShipmentLine", "FinishedGoodsReceiptID"): ("FinishedGoodsReceipt", "FinishedGoodsReceiptID"),
        ("SalesShipmentLine", "ProductionBatchID"): ("ProductionBatch", "ProductionBatchID"),
        ("SalesShipmentTraceability", "ProductionGenealogyID"): ("ProductionGenealogy", "ProductionGenealogyID"),
        ("SalesShipmentTraceability", "MaterialIssueLineID"): ("MaterialIssueLine", "MaterialIssueLineID"),
        ("SalesShipmentTraceability", "InventoryReceiptDetailID"): ("InventoryReceiptDetail", "InventoryReceiptDetailID"),
        ("SalesShipmentTraceability", "SupplierID"): ("SupplierMaster", "SupplierID"),
        ("SalesShipmentTraceability", "ComponentID"): ("ComponentMaster", "ComponentID"),
    }
    for (table_name, column_name), (related_table, related_column) in expected_fks.items():
        column = next(column for column in schema.tables[table_name].columns if column.column_name == column_name)
        assert column.key_type == "FK"
        assert column.related_table == related_table
        assert column.related_column == related_column


@pytest.mark.unit
def test_sales_role_validation_passes_for_sales_metadata() -> None:
    schema = read_metadata_schema(SALES_METADATA)
    result = SalesModulePlugin().validate_roles(schema)

    assert result.report.is_valid
    assert result.summary.expected_roles == 18
    assert result.summary.detected_roles == 18

