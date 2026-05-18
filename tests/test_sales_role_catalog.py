from __future__ import annotations

import pytest

from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES, get_sales_role_catalog


APPROVED_SALES_V1_TABLES = (
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


@pytest.mark.unit
def test_sales_role_catalog_contains_exactly_approved_v1_tables() -> None:
    catalog = get_sales_role_catalog()

    assert SALES_V1_EXPECTED_TABLES == APPROVED_SALES_V1_TABLES
    assert len(catalog) == 18
    assert tuple(definition.expected_table_name for definition in catalog.values()) == APPROVED_SALES_V1_TABLES


@pytest.mark.unit
def test_sales_role_catalog_includes_required_order_to_cash_tables() -> None:
    table_names = {definition.expected_table_name for definition in get_sales_role_catalog().values()}

    for table_name in (
        "CustomerMaster",
        "SalesOrderHdr",
        "SalesOrderLine",
        "SalesInventoryReservation",
        "SalesShipmentLine",
        "SalesInvoiceHeader",
        "SalesInvoiceLine",
        "CustomerPaymentReceipt",
        "SalesReturnHeader",
        "SalesReturnLine",
        "SalesShipmentTraceability",
    ):
        assert table_name in table_names


@pytest.mark.unit
def test_sales_credit_memo_is_not_in_sales_v1_catalog() -> None:
    table_names = {definition.expected_table_name for definition in get_sales_role_catalog().values()}

    assert "SalesCreditMemo" not in table_names


@pytest.mark.unit
def test_sales_traceability_role_documents_upstream_lineage() -> None:
    role = get_sales_role_catalog()["sales_shipment_traceability"]
    notes = " ".join(role.upstream_notes)

    assert role.expected_table_name == "SalesShipmentTraceability"
    assert role.table_kind == "traceability"
    assert "ProductionGenealogy" in notes
    assert "InventoryReceiptDetail" in notes
    assert "SupplierMaster" in notes

