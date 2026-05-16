from __future__ import annotations

from procurement_data_generator.modules.production.role_catalog import (
    PRODUCTION_V1_EXPECTED_TABLES,
    get_production_role_catalog,
)


EXPECTED_ROLES = {
    "product_master",
    "bom_header",
    "bom_line",
    "work_center",
    "routing_header",
    "routing_operation",
    "production_shift",
    "production_order_header",
    "production_order_line",
    "production_material_requirement",
    "material_issue_header",
    "material_issue_line",
    "production_batch",
    "operation_execution",
    "production_quality_inspection",
    "production_quality_result",
    "scrap_rework_event",
    "finished_goods_receipt",
    "finished_goods_inventory",
    "production_genealogy",
    "production_cost_summary",
}


def test_production_role_catalog_imports_and_contains_21_roles() -> None:
    catalog = get_production_role_catalog()

    assert len(catalog) == 21
    assert set(catalog) == EXPECTED_ROLES


def test_production_roles_map_to_expected_table_names() -> None:
    catalog = get_production_role_catalog()

    assert [definition.expected_table_name for definition in catalog.values()] == list(PRODUCTION_V1_EXPECTED_TABLES)


def test_major_production_roles_include_required_columns() -> None:
    catalog = get_production_role_catalog()
    expected_columns = {
        "product_master": {"ProductID", "ProductCode", "ProductName", "UOM", "ProductStatus"},
        "bom_line": {"BOMLineID", "BOMID", "ComponentID", "ComponentQuantity", "ScrapFactorPct"},
        "production_order_line": {"ProductionOrderLineID", "ProductionOrderID", "ProductID", "PlannedQuantity", "GoodQuantity"},
        "production_material_requirement": {"MaterialRequirementID", "ProductionOrderLineID", "BOMLineID", "InventoryID", "RequiredQuantity"},
        "material_issue_line": {"MaterialIssueLineID", "MaterialRequirementID", "SourceInventoryTransactionID", "InventoryReceiptDetailID", "IssuedQuantity"},
        "production_batch": {"ProductionBatchID", "ProductionOrderLineID", "ProductID", "PlannedBatchQuantity", "BatchStatus"},
        "operation_execution": {"OperationExecutionID", "ProductionBatchID", "RoutingOperationID", "InputQuantity", "OutputQuantity"},
        "production_quality_result": {"ProductionQualityResultID", "ProductionInspectionID", "TestedQuantity", "PassedQuantity", "FailedQuantity"},
        "finished_goods_receipt": {"FinishedGoodsReceiptID", "ProductionBatchID", "GoodQuantity", "UnitCost", "ReceiptValue"},
        "finished_goods_inventory": {"FinishedGoodsInventoryID", "ProductID", "OnHandQuantity", "AvailableQuantity", "OnHandValue"},
        "production_genealogy": {"ProductionGenealogyID", "FinishedGoodsReceiptID", "MaterialIssueLineID", "InventoryReceiptDetailID", "SupplierID"},
        "production_cost_summary": {"ProductionCostSummaryID", "ProductionOrderLineID", "MaterialCost", "TotalProductionCost", "UnitProductionCost"},
    }

    for role_name, columns in expected_columns.items():
        assert columns.issubset(set(catalog[role_name].required_column_names))


def test_out_of_scope_mes_roles_are_not_present() -> None:
    catalog = get_production_role_catalog()

    for role_name in ["oee", "downtime", "maintenance", "labor_tracking", "warranty", "sales", "customer"]:
        assert role_name not in catalog
