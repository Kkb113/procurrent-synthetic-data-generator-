from __future__ import annotations

import json
from pathlib import Path

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.shared.operating_scope import get_allowed_shift_codes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "production_v1_metadata.xlsx"
ERD = PROJECT_ROOT / "input" / "production_v1_erd.mmd"
SCENARIO = PROJECT_ROOT / "input" / "production_v1_business_scenario.txt"
VALID_PLAN = PROJECT_ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
INVALID_PLAN = PROJECT_ROOT / "input" / "sample_generation_plan_production_v1_invalid.json"

EXPECTED_TABLES = [
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


def test_production_v1_fixture_files_exist() -> None:
    assert METADATA.exists()
    assert ERD.exists()
    assert SCENARIO.exists()
    assert VALID_PLAN.exists()
    assert INVALID_PLAN.exists()


def test_production_v1_metadata_loads_with_21_tables() -> None:
    result = load_metadata_schema(METADATA)

    assert result.schema is not None
    assert result.report.is_valid
    assert list(result.schema.tables) == EXPECTED_TABLES
    assert len(result.schema.tables) == 21


def test_production_v1_metadata_contains_cross_module_foreign_keys() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    expected = [
        ("BOMLine", "ComponentID", "ComponentMaster", "ComponentID"),
        ("BOMHeader", "PlantID", "Plant", "PlantID"),
        ("WorkCenter", "PlantID", "Plant", "PlantID"),
        ("ProductionOrderHdr", "PlantID", "Plant", "PlantID"),
        ("ProductionMaterialRequirement", "InventoryID", "Inventory", "InventoryID"),
        ("MaterialIssueLine", "SourceInventoryTransactionID", "InventoryTransaction", "InventoryTransactionID"),
        ("MaterialIssueLine", "InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"),
        ("ProductionGenealogy", "InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"),
        ("ProductionGenealogy", "SourceInventoryTransactionID", "InventoryTransaction", "InventoryTransactionID"),
        ("ProductionGenealogy", "SupplierID", "SupplierMaster", "SupplierID"),
    ]
    for table_name, column_name, related_table, related_column in expected:
        column = _column(result.schema.tables[table_name], column_name)
        assert column.key_type == "FK"
        assert column.related_table == related_table
        assert column.related_column == related_column


def test_production_v1_metadata_allows_only_shift_a() -> None:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    shift_code = _column(result.schema.tables["ProductionShift"], "ShiftCode")
    assert tuple(shift_code.allowed_values or []) == get_allowed_shift_codes()


def test_production_v1_erd_includes_corrected_lifecycle_and_cross_module_relationships() -> None:
    text = ERD.read_text(encoding="utf-8")

    expected_relationships = [
        "Inventory ||--o{ ProductionMaterialRequirement : source_inventory",
        "ProductionOrderHdr ||--o{ ProductionOrderLine : contains",
        "ProductionOrderLine ||--o{ ProductionMaterialRequirement : requires",
        "ProductionMaterialRequirement ||--o{ MaterialIssueLine : fulfilled_by",
        "MaterialIssueHeader ||--o{ MaterialIssueLine : contains",
        "ProductionOrderLine ||--o{ ProductionBatch : executed_as",
        "ProductionBatch ||--o{ OperationExecution : has_operations",
        "OperationExecution ||--o{ ProductionQualityInspection : inspected_operation",
        "ProductionQualityInspection ||--o{ ProductionQualityResult : has_result",
        "ProductionBatch ||--o{ ScrapReworkEvent : has_scrap_rework",
        "ProductionBatch ||--o{ FinishedGoodsReceipt : produces_receipt",
        "FinishedGoodsReceipt ||--o{ FinishedGoodsInventory : rolls_up_to",
        "FinishedGoodsReceipt ||--o{ ProductionGenealogy : traced_output",
        "MaterialIssueLine ||--o{ ProductionGenealogy : traced_consumption",
        "ProductionBatch ||--o{ ProductionCostSummary : costed_batch",
        "InventoryTransaction ||--o{ MaterialIssueLine : source_stockin",
        "InventoryReceiptDetail ||--o{ MaterialIssueLine : source_receipt",
        "SupplierMaster ||--o{ ProductionGenealogy : traced_supplier",
        "InventoryReceiptDetail ||--o{ ProductionGenealogy : traced_receipt",
    ]
    for relationship in expected_relationships:
        assert relationship in text


def test_production_v1_business_scenario_mentions_required_design_points() -> None:
    text = SCENARIO.read_text(encoding="utf-8")

    for phrase in [
        "Production Execution module within MES context v1",
        "Procurement provides component inventory",
        "MaterialIssueLine",
        "FinishedGoodsInventory",
        "ProductionGenealogy",
        "2025-01-01 and 2025-12-31",
        "UOM-aware quantity precision",
        "Production MaterialIssueLine is the production-side material consumption ledger",
        "one Procurement Plant, one Procurement Warehouse, and Shift A only",
    ]:
        assert phrase in text


def test_production_v1_valid_sample_plan_mentions_21_tables_and_production_v1() -> None:
    plan = json.loads(VALID_PLAN.read_text(encoding="utf-8"))

    assert plan["module"] == "production"
    assert "production_v1" in json.dumps(plan).lower()
    assert len(plan["table_role_mapping"]) == 21
    assert len(plan["row_count_plan"]) == 21
    assert plan["generation_order"] == EXPECTED_TABLES
    assert any("2025-01-01 to 2025-12-31" in rule["condition"] for rule in plan["validation_rules"])
    assert any("InventoryReceiptDetail" in assumption for assumption in plan["assumptions"])
    assert any("Shift A only" in assumption for assumption in plan["assumptions"])


def test_production_v1_invalid_sample_plan_is_intentionally_invalid() -> None:
    plan = json.loads(INVALID_PLAN.read_text(encoding="utf-8"))

    assert plan["module"] != "production"
    assert len(plan["generation_order"]) != 21
    assert "2026" in json.dumps(plan)
    assert plan["generation_order"][0] == "ProductionMaterialRequirement"
    assert "invalid lifecycle order" in " ".join(plan["assumptions"]).lower()


def _column(table, column_name: str):
    return next(column for column in table.columns if column.column_name == column_name)
