from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_DOC = ROOT / "project.md"
UI_TEMPLATE = ROOT / "app" / "templates" / "index.html"

PRODUCTION_TABLES = [
    "ProductMaster",
    "BOMHeader",
    "BOMLine",
    "WorkCenter",
    "RoutingHeader",
    "RoutingOperation",
    "ProductionShift",
    "ProductionOrderHdr",
    "ProductionOrderLine",
    "ProductionMaterialRequirement",
    "MaterialIssueHeader",
    "MaterialIssueLine",
    "ProductionBatch",
    "OperationExecution",
    "ProductionQualityInspection",
    "ProductionQualityResult",
    "ScrapReworkEvent",
    "FinishedGoodsReceipt",
    "FinishedGoodsInventory",
    "ProductionGenealogy",
    "ProductionCostSummary",
]


def test_project_documentation_mentions_production_execution_context() -> None:
    text = PROJECT_DOC.read_text(encoding="utf-8")

    assert "Production Execution module within MES context" in text
    assert "not a full MES platform" in text
    assert "scripts/run_production_pipeline.py" in text


def test_project_documentation_lists_21_production_tables() -> None:
    text = PROJECT_DOC.read_text(encoding="utf-8")

    for table_name in PRODUCTION_TABLES:
        assert table_name in text


def test_project_documentation_describes_procurement_to_production_integration() -> None:
    text = PROJECT_DOC.read_text(encoding="utf-8")

    assert "Procurement creates available component/material inventory" in text
    assert "Production consumes that Procurement inventory" in text
    assert "InventoryReceiptDetail" in text
    assert "InventoryTransaction" in text
    assert "ProductionGenealogy" in text
    assert "MaterialIssueLine" in text


def test_project_documentation_includes_current_production_script_sequence() -> None:
    text = PROJECT_DOC.read_text(encoding="utf-8")

    assert "scripts/generate_production_master_data.py" in text
    assert "scripts/generate_production_transaction_data.py" in text
    assert "scripts/validate_production_generated_data.py" in text
    assert "scripts/run_production_pipeline.py" in text
    assert "docs/production_v1_sql_checks.sql" in text


def test_ui_documents_production_but_does_not_expose_active_production_option() -> None:
    text = UI_TEMPLATE.read_text(encoding="utf-8")

    assert "Production Execution module within MES context" in text
    assert "dedicated command-line pipeline" in text
    assert 'value="production_v1"' not in text
