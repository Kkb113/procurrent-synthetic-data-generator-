"""Production Execution module within MES context v1 table role catalog for metadata and plan validation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProductionRoleDefinition:
    """Expected metadata characteristics for a supported Production Execution role."""

    role_name: str
    expected_table_name: str
    expected_area: str
    is_master_table: bool
    process_order: int
    expected_process_stage: str
    purpose: str
    required_column_names: tuple[str, ...] = field(default_factory=tuple)
    recommended_column_names: tuple[str, ...] = field(default_factory=tuple)
    expected_parent_roles: tuple[str, ...] = field(default_factory=tuple)


PRODUCTION_V1_EXPECTED_TABLES = (
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
)

PRODUCTION_V1_ROLE_CATALOG: dict[str, ProductionRoleDefinition] = {
    "product_master": ProductionRoleDefinition("product_master", "ProductMaster", "Master", True, 10, "Product Master", "Finished or semi-finished goods produced by the factory.", ("ProductID", "ProductCode", "ProductName", "ProductCategory", "ProductType", "UOM", "StandardCost", "ProductStatus")),
    "bom_header": ProductionRoleDefinition("bom_header", "BOMHeader", "Master", True, 20, "BOM Header", "Bill of Material header for a product and plant.", ("BOMID", "ProductID", "PlantID", "BOMVersion", "EffectiveFromDate", "EffectiveToDate", "BOMStatus"), expected_parent_roles=("product_master",)),
    "bom_line": ProductionRoleDefinition("bom_line", "BOMLine", "Master", True, 21, "BOM Line", "Component requirements for each product.", ("BOMLineID", "BOMID", "ComponentID", "ComponentQuantity", "UOM", "ScrapFactorPct", "IsCriticalComponent", "BOMLineStatus"), expected_parent_roles=("bom_header",)),
    "work_center": ProductionRoleDefinition("work_center", "WorkCenter", "Master", True, 30, "Work Center", "MES work center, station, line, or production cell.", ("WorkCenterID", "PlantID", "WorkCenterCode", "WorkCenterName", "LineName", "CapacityPerShift", "CapacityUOM", "WorkCenterStatus")),
    "routing_header": ProductionRoleDefinition("routing_header", "RoutingHeader", "Master", True, 40, "Routing Header", "Routing version for manufacturing a product.", ("RoutingID", "ProductID", "PlantID", "RoutingVersion", "RoutingStatus"), expected_parent_roles=("product_master",)),
    "routing_operation": ProductionRoleDefinition("routing_operation", "RoutingOperation", "Master", True, 41, "Routing Operation", "Step-by-step operations in a production routing.", ("RoutingOperationID", "RoutingID", "WorkCenterID", "OperationSequence", "OperationName", "SetupTimeMinutes", "RunTimeMinutesPerUnit", "StandardYieldPct", "OperationStatus"), expected_parent_roles=("routing_header", "work_center")),
    "production_shift": ProductionRoleDefinition("production_shift", "ProductionShift", "MES", True, 50, "Production Shift", "Shift calendar for MES execution.", ("ShiftID", "PlantID", "WorkCenterID", "ShiftDate", "ShiftCode", "ShiftStartTime", "ShiftEndTime", "PlannedHours"), expected_parent_roles=("work_center",)),
    "production_order_header": ProductionRoleDefinition("production_order_header", "ProductionOrderHdr", "Production", False, 60, "Production Order", "Released manufacturing order at a plant.", ("ProductionOrderID", "PlantID", "OrderDate", "PlannedStartDate", "PlannedEndDate", "ActualStartDate", "ActualEndDate", "ProductionOrderStatus", "Priority")),
    "production_order_line": ProductionRoleDefinition("production_order_line", "ProductionOrderLine", "Production", False, 61, "Production Order Line", "Product and quantity to build for the production order.", ("ProductionOrderLineID", "ProductionOrderID", "ProductID", "BOMID", "RoutingID", "PlannedQuantity", "ReleasedQuantity", "CompletedQuantity", "GoodQuantity", "ScrapQuantity", "UOM", "LineStatus"), expected_parent_roles=("production_order_header", "product_master", "bom_header", "routing_header")),
    "production_material_requirement": ProductionRoleDefinition("production_material_requirement", "ProductionMaterialRequirement", "Production", False, 70, "Production Material Requirement", "Derived component requirement from BOM and production order line.", ("MaterialRequirementID", "ProductionOrderLineID", "BOMLineID", "ComponentID", "PlantID", "WarehouseID", "InventoryID", "RequiredQuantity", "ScrapAdjustedQuantity", "IssuedQuantity", "RequirementStatus"), expected_parent_roles=("production_order_line", "bom_line")),
    "material_issue_header": ProductionRoleDefinition("material_issue_header", "MaterialIssueHeader", "Production", False, 80, "Material Issue Header", "Header for material issue or consumption event.", ("MaterialIssueID", "ProductionOrderID", "PlantID", "WarehouseID", "IssueDate", "IssueStatus"), expected_parent_roles=("production_order_header",)),
    "material_issue_line": ProductionRoleDefinition("material_issue_line", "MaterialIssueLine", "Production", False, 81, "Material Issue Line", "Production-side material consumption ledger.", ("MaterialIssueLineID", "MaterialIssueID", "MaterialRequirementID", "ComponentID", "InventoryID", "SourceInventoryTransactionID", "InventoryReceiptDetailID", "IssuedQuantity", "UOM", "UnitCost", "IssueValue", "IssueStatus"), expected_parent_roles=("material_issue_header", "production_material_requirement")),
    "production_batch": ProductionRoleDefinition("production_batch", "ProductionBatch", "Production", False, 90, "Production Batch", "Batch or lot execution record.", ("ProductionBatchID", "ProductionOrderLineID", "BatchNumber", "ProductID", "PlantID", "PlannedBatchQuantity", "ActualStartDate", "ActualEndDate", "BatchStatus"), expected_parent_roles=("production_order_line", "product_master")),
    "operation_execution": ProductionRoleDefinition("operation_execution", "OperationExecution", "MES", False, 100, "Operation Execution", "MES operation-level execution through routing operations.", ("OperationExecutionID", "ProductionBatchID", "RoutingOperationID", "WorkCenterID", "ShiftID", "OperationSequence", "ActualStartDateTime", "ActualEndDateTime", "InputQuantity", "OutputQuantity", "ScrapQuantity", "ReworkQuantity", "OperationStatus"), expected_parent_roles=("production_batch", "routing_operation", "work_center", "production_shift")),
    "production_quality_inspection": ProductionRoleDefinition("production_quality_inspection", "ProductionQualityInspection", "Quality", False, 110, "Production Quality Inspection", "Production quality inspection event.", ("ProductionInspectionID", "ProductionBatchID", "OperationExecutionID", "ProductID", "InspectionDate", "InspectionType", "SampleQuantity", "InspectorName", "InspectionStatus"), expected_parent_roles=("production_batch", "operation_execution", "product_master")),
    "production_quality_result": ProductionRoleDefinition("production_quality_result", "ProductionQualityResult", "Quality", False, 111, "Production Quality Result", "Result of production quality inspection.", ("ProductionQualityResultID", "ProductionInspectionID", "TestedQuantity", "PassedQuantity", "FailedQuantity", "DefectCode", "DefectSeverity", "ResultStatus"), expected_parent_roles=("production_quality_inspection",)),
    "scrap_rework_event": ProductionRoleDefinition("scrap_rework_event", "ScrapReworkEvent", "Quality", False, 120, "Scrap Rework Event", "Scrap and rework event details.", ("ScrapReworkID", "ProductionBatchID", "OperationExecutionID", "ProductID", "EventType", "Quantity", "ReasonCode", "CostImpact", "EventDate"), expected_parent_roles=("production_batch", "operation_execution", "product_master")),
    "finished_goods_receipt": ProductionRoleDefinition("finished_goods_receipt", "FinishedGoodsReceipt", "Inventory", False, 130, "Finished Goods Receipt", "Finished goods posted after production completion.", ("FinishedGoodsReceiptID", "ProductionBatchID", "ProductionOrderLineID", "ProductID", "PlantID", "WarehouseID", "ReceiptDate", "GoodQuantity", "ScrapQuantity", "UnitCost", "ReceiptValue", "ReceiptStatus"), expected_parent_roles=("production_batch", "production_order_line", "product_master")),
    "finished_goods_inventory": ProductionRoleDefinition("finished_goods_inventory", "FinishedGoodsInventory", "Inventory", False, 140, "Finished Goods Inventory", "Balance table for finished goods inventory.", ("FinishedGoodsInventoryID", "ProductID", "PlantID", "WarehouseID", "OnHandQuantity", "ReservedQuantity", "AvailableQuantity", "OnHandValue", "LastReceiptDate", "InventoryStatus"), expected_parent_roles=("product_master",)),
    "production_genealogy": ProductionRoleDefinition("production_genealogy", "ProductionGenealogy", "MES", False, 150, "Production Genealogy", "Traceability from finished goods back to consumed components and procurement receipt lineage.", ("ProductionGenealogyID", "FinishedGoodsReceiptID", "ProductionBatchID", "MaterialIssueLineID", "ComponentID", "InventoryReceiptDetailID", "SourceInventoryTransactionID", "SupplierID", "ConsumedQuantity", "TraceabilityStatus"), expected_parent_roles=("finished_goods_receipt", "production_batch", "material_issue_line")),
    "production_cost_summary": ProductionRoleDefinition("production_cost_summary", "ProductionCostSummary", "Finance", False, 160, "Production Cost Summary", "Production cost rollup by order line and batch.", ("ProductionCostSummaryID", "ProductionOrderLineID", "ProductionBatchID", "ProductID", "MaterialCost", "LaborCost", "OverheadCost", "ScrapCost", "TotalProductionCost", "UnitProductionCost"), expected_parent_roles=("production_order_line", "production_batch", "product_master")),
}


def get_production_role_catalog(model_version: str = "production_v1") -> dict[str, ProductionRoleDefinition]:
    """Return the supported Production Execution role catalog for the requested model version."""

    if model_version != "production_v1":
        return {}
    return PRODUCTION_V1_ROLE_CATALOG


