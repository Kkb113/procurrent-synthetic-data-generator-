from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file


SALES_ERD = Path("input/sales_v1_erd.mmd")


@pytest.mark.unit
def test_sales_erd_fixture_parses_successfully() -> None:
    relationships = parse_mermaid_erd_file(SALES_ERD)

    assert len(relationships) >= 40
    assert any(
        relationship.parent_table == "SalesShipmentLine"
        and relationship.child_table == "SalesShipmentTraceability"
        for relationship in relationships
    )


@pytest.mark.unit
def test_sales_erd_includes_traceability_links_to_production_and_procurement_lineage() -> None:
    relationships = parse_mermaid_erd_file(SALES_ERD)
    pairs = {(relationship.parent_table, relationship.child_table) for relationship in relationships}

    for pair in (
        ("FinishedGoodsReceipt", "SalesShipmentTraceability"),
        ("ProductionBatch", "SalesShipmentTraceability"),
        ("ProductionGenealogy", "SalesShipmentTraceability"),
        ("MaterialIssueLine", "SalesShipmentTraceability"),
        ("InventoryReceiptDetail", "SalesShipmentTraceability"),
        ("SupplierMaster", "SalesShipmentTraceability"),
        ("ComponentMaster", "SalesShipmentTraceability"),
        ("ProductMaster", "SalesShipmentTraceability"),
    ):
        assert pair in pairs


@pytest.mark.unit
def test_sales_erd_excludes_sales_credit_memo() -> None:
    assert "SalesCreditMemo" not in SALES_ERD.read_text(encoding="utf-8")

