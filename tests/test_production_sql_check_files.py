from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SQL = ROOT / "docs" / "production_v1_sql_checks.sql"

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

UPSTREAM_PROCUREMENT_TABLES = [
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "Inventory",
    "InventoryTransaction",
    "InventoryReceiptDetail",
    "SupplierMaster",
]


def _sql_text() -> str:
    return PRODUCTION_SQL.read_text(encoding="utf-8")


def test_production_v1_sql_checks_file_exists() -> None:
    assert PRODUCTION_SQL.exists()


def test_production_sql_contains_all_21_production_tables() -> None:
    text = _sql_text()

    for table_name in PRODUCTION_TABLES:
        assert table_name in text


def test_production_sql_contains_required_upstream_procurement_tables() -> None:
    text = _sql_text()

    for table_name in UPSTREAM_PROCUREMENT_TABLES:
        assert table_name in text


def test_production_sql_contains_row_count_summary() -> None:
    text = _sql_text()

    assert "ROW COUNT SUMMARY" in text
    assert "TableName" in text
    assert "RowCount" in text
    assert "COUNT(*) AS RowCount" in text


def test_production_sql_contains_material_issue_inventory_cap_check() -> None:
    text = _sql_text()

    assert "Inventory consumption cap by InventoryID" in text
    assert "SUM(mil.IssuedQuantity)" in text
    assert "i.AvailableQuantity" in text
    assert "Material issue exceeds Inventory.AvailableQuantity" in text


def test_production_sql_contains_inventory_transaction_lineage_checks() -> None:
    text = _sql_text()

    assert "SourceInventoryTransactionID" in text
    assert "InventoryTransaction" in text
    assert "it.InventoryTransactionID = mil.SourceInventoryTransactionID" in text
    assert "Bad InventoryTransaction lineage" in text


def test_production_sql_contains_inventory_receipt_detail_lineage_checks() -> None:
    text = _sql_text()

    assert "InventoryReceiptDetailID" in text
    assert "InventoryReceiptDetail" in text
    assert "ird.InventoryReceiptDetailID = mil.InventoryReceiptDetailID" in text
    assert "Bad InventoryReceiptDetail lineage" in text


def test_production_sql_contains_genealogy_checks() -> None:
    text = _sql_text()

    assert "ProductionGenealogy traceability checks" in text
    assert "TraceabilityStatus" in text
    assert "pg.SupplierID <> ird.SupplierID" in text
    assert "Bad genealogy traceability" in text


def test_production_sql_contains_finished_goods_inventory_rollup_checks() -> None:
    text = _sql_text()

    assert "FinishedGoodsInventory rollup checks" in text
    assert "ExpectedOnHandQuantity" in text
    assert "ExpectedOnHandValue" in text
    assert "AvailableQuantity - (fgi.OnHandQuantity - fgi.ReservedQuantity)" in text
    assert "Bad finished goods inventory rollup" in text


def test_production_sql_contains_cost_summary_checks() -> None:
    text = _sql_text()

    assert "ProductionCostSummary formulas" in text
    assert "MaterialCostRollup" in text
    assert "TotalProductionCost" in text
    assert "UnitProductionCost" in text
    assert "Bad production cost summary" in text


def test_production_sql_contains_quality_defect_code_checks() -> None:
    text = _sql_text()

    assert "NoDefect" in text
    assert "TorqueDeviation" in text
    assert "Failed quality rows" not in text or "DefectCode" in text
    assert "pqr.DefectCode IN ('NoDefect', 'None')" in text
    assert "pqr.DefectCode NOT IN" in text


def test_production_sql_contains_2025_date_checks() -> None:
    text = _sql_text()

    assert "2025 DATE SCOPE CHECK" in text
    assert "2025-01-01" in text
    assert "2025-12-31" in text
    assert "TRY_CONVERT(date, ActualStartDateTime)" in text
    assert "Dates outside 2025" in text


def test_production_sql_contains_uom_precision_checks() -> None:
    text = _sql_text()

    assert "UOM QUANTITY PRECISION CHECKS" in text
    assert "CountableUOM" in text
    assert "BOMLine.ComponentQuantity decimal for countable UOM" in text
    assert "MaterialIssueLine.IssuedQuantity decimal for countable UOM" in text
    assert "FinishedGoodsInventory.OnHandQuantity decimal for countable UOM" in text
    assert "FLOOR(" in text
    assert "BATTERYPACK" in text


def test_production_sql_contains_final_scorecard() -> None:
    text = _sql_text()

    assert "FINAL SCORECARD" in text
    assert "Final Production v1 scorecard" in text
    assert "IssueName" in text
    assert "IssueCount" in text
    assert "Expected: all IssueCount = 0" in text
    assert "Countable UOM decimal quantity issues" in text


def test_production_sql_contains_one_location_and_shift_a_scope_checks() -> None:
    text = _sql_text()

    assert "SIMPLIFIED OPERATING SCOPE" in text
    assert "Upstream Plant count should be 1" in text
    assert "Upstream Warehouse count should be 1" in text
    assert "Invalid Production PlantID references" in text
    assert "Invalid Production WarehouseID references" in text
    assert "DistinctPlantCount" in text
    assert "DistinctWarehouseCount" in text
    assert "ShiftCode, COUNT(*) AS RowCount" in text
    assert "Invalid ProductionShift ShiftCode" in text
    assert "ShiftCode <> 'A'" in text
    assert "Shift B/C should not exist" in text
    assert "ShiftCode IN ('B', 'C')" in text
    assert "OperationExecution references non-A shift" in text
    assert "OperationExecution WorkCenter/Shift mismatch" in text
    assert "oe.WorkCenterID <> ps.WorkCenterID" in text
    assert "WorkCenter count is informational only" in text
    assert "WorkCenterCount" in text
