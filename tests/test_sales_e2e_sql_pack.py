from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_PACK = ROOT / "sql" / "mes_procurement_production_sales_validation.sql"
E2E_DOC = ROOT / "docs" / "SALES_E2E_VALIDATION.md"


def test_sales_e2e_sql_validation_pack_exists() -> None:
    assert SQL_PACK.exists()
    assert SQL_PACK.read_text(encoding="utf-8").strip()


def test_sales_e2e_sql_pack_contains_major_sections() -> None:
    sql = SQL_PACK.read_text(encoding="utf-8")

    expected_sections = [
        "TABLE PRESENCE AND ROW-COUNT READINESS",
        "PROCUREMENT LIFECYCLE VALIDATION",
        "PROCUREMENT RECONCILIATION VALIDATION",
        "PRODUCTION MATERIAL CONSUMPTION VALIDATION",
        "PRODUCTION FINISHED GOODS, GENEALOGY, AND COST VALIDATION",
        "SALES MASTER/REFERENCE VALIDATION",
        "SALES ORDER/RESERVATION/PICK/SHIPMENT VALIDATION",
        "SALES INVOICE/PAYMENT VALIDATION",
        "SALES RETURNS VALIDATION",
        "SALES SHIPMENT TRACEABILITY VALIDATION",
        "FINISHED GOODS INVENTORY AFTER SALES VALIDATION",
        "END-TO-END SUPPLIER-TO-CUSTOMER TRACEABILITY",
        "FOOD MANUFACTURING VOCABULARY / EV LEAKAGE CHECK",
        "FINAL READINESS STATUS",
        "SALES_E2E_VALIDATED",
    ]

    for section in expected_sections:
        assert section in sql


def test_sales_e2e_sql_pack_contains_key_tables() -> None:
    sql = SQL_PACK.read_text(encoding="utf-8")

    key_tables = [
        "SalesOrderLine",
        "SalesShipmentLine",
        "SalesInvoiceHeader",
        "CustomerPaymentReceipt",
        "SalesReturnLine",
        "SalesShipmentTraceability",
        "FinishedGoodsInventory",
        "FinishedGoodsReceipt",
        "ProductionGenealogy",
        "MaterialIssueLine",
        "InventoryReceiptDetail",
        "SupplierMaster",
        "ComponentMaster",
    ]

    for table_name in key_tables:
        assert table_name in sql


def test_sales_e2e_sql_pack_does_not_require_sales_credit_memo() -> None:
    sql = SQL_PACK.read_text(encoding="utf-8")

    assert "SalesCreditMemoObjectCount" in sql
    assert "SalesCreditMemo is not part of Sales v1" in sql
    assert "('Sales', 'SalesCreditMemo')" not in sql
    assert "('SalesCreditMemo')" not in sql


def test_sales_e2e_documentation_exists_and_mentions_frontend_and_sql_validation() -> None:
    assert E2E_DOC.exists()
    text = E2E_DOC.read_text(encoding="utf-8")

    assert "uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" in text
    assert "Procurement checked" in text
    assert "Production checked" in text
    assert "Sales checked" in text
    assert "profile_id" in text or "Profile ID" in text
    assert "food_manufacturing" in text
    assert "sql/mes_procurement_production_sales_validation.sql" in text
    assert "SALES_E2E_VALIDATED" in text
