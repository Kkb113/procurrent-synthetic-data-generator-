"""Create Production/MES v1 metadata, ERD, scenario, and sample plan fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.modules.shared.operating_scope import get_allowed_shift_codes

INPUT_DIR = PROJECT_ROOT / "input"

HEADERS = [
    "TableName",
    "ProcessOrder",
    "Process",
    "Area",
    "TableRole",
    "TargetRows",
    "ColumnName",
    "DataType",
    "KeyType",
    "RelatedTable",
    "RelatedColumn",
    "Nullable",
    "AllowedValues",
    "MinValue",
    "MaxValue",
    "Purpose",
    "GenerationType",
    "Formula",
]

TARGET_ROWS = {
    "ProductMaster": 30,
    "BOMHeader": 40,
    "BOMLine": 250,
    "WorkCenter": 20,
    "RoutingHeader": 40,
    "RoutingOperation": 180,
    "ProductionShift": 500,
    "ProductionOrderHdr": 800,
    "ProductionOrderLine": 1000,
    "ProductionMaterialRequirement": 4000,
    "MaterialIssueHeader": 800,
    "MaterialIssueLine": 4000,
    "ProductionBatch": 1000,
    "OperationExecution": 4000,
    "ProductionQualityInspection": 1500,
    "ProductionQualityResult": 1500,
    "ScrapReworkEvent": 300,
    "FinishedGoodsReceipt": 1000,
    "FinishedGoodsInventory": 120,
    "ProductionGenealogy": 4000,
    "ProductionCostSummary": 1000,
}


def main() -> int:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _metadata_rows()
    _write_metadata(rows)
    _write_erd()
    _write_scenario()
    _write_sample_plans()
    print(f"Created {INPUT_DIR / 'production_v1_metadata.xlsx'}")
    print(f"Metadata rows: {len(rows)}")
    print(f"Production tables: {len({row['TableName'] for row in rows})}")
    print(f"Created {INPUT_DIR / 'production_v1_erd.mmd'}")
    print(f"Created {INPUT_DIR / 'production_v1_business_scenario.txt'}")
    print(f"Created {INPUT_DIR / 'sample_generation_plan_production_v1_valid.json'}")
    print(f"Created {INPUT_DIR / 'sample_generation_plan_production_v1_invalid.json'}")
    return 0


def _metadata_rows() -> list[dict]:
    rows = []
    for table in _tables():
        for column in table["columns"]:
            (
                column_name,
                data_type,
                key_type,
                related_table,
                related_column,
                nullable,
                allowed_values,
                min_value,
                max_value,
                purpose,
                generation_type,
                formula,
            ) = column
            rows.append(
                {
                    "TableName": table["table"],
                    "ProcessOrder": table["order"],
                    "Process": table["process"],
                    "Area": table["area"],
                    "TableRole": table["role"],
                    "TargetRows": table["rows"],
                    "ColumnName": column_name,
                    "DataType": data_type,
                    "KeyType": key_type,
                    "RelatedTable": related_table,
                    "RelatedColumn": related_column,
                    "Nullable": nullable,
                    "AllowedValues": allowed_values,
                    "MinValue": min_value,
                    "MaxValue": max_value,
                    "Purpose": purpose,
                    "GenerationType": generation_type,
                    "Formula": formula,
                }
            )
    return rows


def _tables() -> list[dict]:
    return [
        _table("ProductMaster", 10, "Product Master", "Master", "product_master", [
            _pk("ProductID"), _cat("ProductCode", "", "varchar(40)"), _cat("ProductName", "", "varchar(200)"),
            _cat("ProductCategory", "Battery Pack,Drive Unit,Power Electronics,Thermal Module,Chassis Assembly", "varchar(100)"),
            _cat("ProductType", "FinishedGood,SemiFinished"), _cat("UOM", "EA,Unit,Set"),
            _decimal("StandardCost", 1000, 80000), _decimal("StandardBuildTimeHours", 1, 80), _status("ProductStatus", "Active,Inactive"),
        ]),
        _table("BOMHeader", 20, "BOM Header", "Master", "bom_header", [
            _pk("BOMID"), _fk("ProductID", "ProductMaster", "ProductID"), _fk("PlantID", "Plant", "PlantID"),
            _cat("BOMVersion", "", "varchar(40)"), _date("EffectiveFromDate", "date_range"), _date("EffectiveToDate", "date_range"),
            _status("BOMStatus", "Active,Inactive"),
        ]),
        _table("BOMLine", 21, "BOM Line", "Master", "bom_line", [
            _pk("BOMLineID"), _fk("BOMID", "BOMHeader", "BOMID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
            _decimal("ComponentQuantity", 0.01, 500), _cat("UOM", "Each,Box,Kg,Meter,Roll,Liter,Set", "varchar(30)"),
            _decimal("ScrapFactorPct", 0, 5), _cat("IsCriticalComponent", "0,1", "int"), _status("BOMLineStatus", "Active,Inactive"),
        ]),
        _table("WorkCenter", 30, "Work Center", "Master", "work_center", [
            _pk("WorkCenterID"), _fk("PlantID", "Plant", "PlantID"), _cat("WorkCenterCode", "", "varchar(40)"),
            _cat("WorkCenterName", "", "varchar(150)"), _cat("LineName", "Battery Line A,Drive Unit Line,Thermal Line,Final Assembly", "varchar(120)"),
            _decimal("CapacityPerShift", 1, 1000), _cat("CapacityUOM", "EA,Unit,Set"), _status("WorkCenterStatus", "Active,Inactive,Maintenance"),
        ]),
        _table("RoutingHeader", 40, "Routing Header", "Master", "routing_header", [
            _pk("RoutingID"), _fk("ProductID", "ProductMaster", "ProductID"), _fk("PlantID", "Plant", "PlantID"),
            _cat("RoutingVersion", "", "varchar(40)"), _status("RoutingStatus", "Active,Inactive"),
        ]),
        _table("RoutingOperation", 41, "Routing Operation", "Master", "routing_operation", [
            _pk("RoutingOperationID"), _fk("RoutingID", "RoutingHeader", "RoutingID"), _fk("WorkCenterID", "WorkCenter", "WorkCenterID"),
            _int("OperationSequence", 10, 999), _cat("OperationName", "Kitting,Assembly,Torque Check,Calibration,End Of Line Test,Packout", "varchar(120)"),
            _decimal("SetupTimeMinutes", 0, 240), _decimal("RunTimeMinutesPerUnit", 0.1, 120), _decimal("StandardYieldPct", 90, 100),
            _status("OperationStatus", "Active,Inactive"),
        ]),
        _table("ProductionShift", 50, "Production Shift", "MES", "production_shift", [
            _pk("ShiftID"), _fk("PlantID", "Plant", "PlantID"), _fk("WorkCenterID", "WorkCenter", "WorkCenterID"),
            _date("ShiftDate", "date_range"), _cat("ShiftCode", ",".join(get_allowed_shift_codes())), _cat("ShiftStartTime", "08:00", "varchar(20)"),
            _cat("ShiftEndTime", "16:00", "varchar(20)"), _decimal("PlannedHours", 4, 12),
        ]),
        _table("ProductionOrderHdr", 60, "Production Order", "Production", "production_order_header", [
            _pk("ProductionOrderID"), _fk("PlantID", "Plant", "PlantID"), _date("OrderDate", "date_range"),
            _date("PlannedStartDate", "date_offset"), _date("PlannedEndDate", "date_offset"), _date("ActualStartDate", "date_offset"),
            _date("ActualEndDate", "date_offset"), _status("ProductionOrderStatus", "Planned,Released,InProduction,Completed,Cancelled"),
            _cat("Priority", "Low,Normal,High,Urgent"),
        ]),
        _table("ProductionOrderLine", 61, "Production Order Line", "Production", "production_order_line", [
            _pk("ProductionOrderLineID"), _fk("ProductionOrderID", "ProductionOrderHdr", "ProductionOrderID"),
            _fk("ProductID", "ProductMaster", "ProductID"), _fk("BOMID", "BOMHeader", "BOMID"), _fk("RoutingID", "RoutingHeader", "RoutingID"),
            _decimal("PlannedQuantity", 1, 1000), _decimal("ReleasedQuantity", 0, 1000), _decimal("CompletedQuantity", 0, 1000),
            _decimal("GoodQuantity", 0, 1000), _decimal("ScrapQuantity", 0, 30), _cat("UOM", "EA,Unit,Set"), _status("LineStatus", "Planned,Released,InProduction,Completed,Cancelled"),
        ]),
        _table("ProductionMaterialRequirement", 70, "Production Material Requirement", "Production", "production_material_requirement", [
            _pk("MaterialRequirementID"), _fk("ProductionOrderLineID", "ProductionOrderLine", "ProductionOrderLineID"),
            _fk("BOMLineID", "BOMLine", "BOMLineID"), _fk("ComponentID", "ComponentMaster", "ComponentID"), _fk("PlantID", "Plant", "PlantID"),
            _fk("WarehouseID", "Warehouse", "WarehouseID"), _fk("InventoryID", "Inventory", "InventoryID"),
            _calc("RequiredQuantity", "ProductionOrderLine.PlannedQuantity * BOMLine.ComponentQuantity", 0, 1000000),
            _calc("ScrapAdjustedQuantity", "RequiredQuantity * (1 + ScrapFactorPct / 100)", 0, 1000000),
            _decimal("IssuedQuantity", 0, 1000000), _status("RequirementStatus", "Required,Issued,Consumed,Short"),
        ]),
        _table("MaterialIssueHeader", 80, "Material Issue Header", "Production", "material_issue_header", [
            _pk("MaterialIssueID"), _fk("ProductionOrderID", "ProductionOrderHdr", "ProductionOrderID"),
            _fk("PlantID", "Plant", "PlantID"), _fk("WarehouseID", "Warehouse", "WarehouseID"), _date("IssueDate", "date_offset"),
            _status("IssueStatus", "Planned,Issued,Cancelled"),
        ]),
        _table("MaterialIssueLine", 81, "Material Issue Line", "Production", "material_issue_line", [
            _pk("MaterialIssueLineID"), _fk("MaterialIssueID", "MaterialIssueHeader", "MaterialIssueID"),
            _fk("MaterialRequirementID", "ProductionMaterialRequirement", "MaterialRequirementID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
            _fk("InventoryID", "Inventory", "InventoryID"), _fk("SourceInventoryTransactionID", "InventoryTransaction", "InventoryTransactionID"),
            _fk("InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"), _decimal("IssuedQuantity", 0, 1000000),
            _cat("UOM", "Each,Box,Kg,Meter,Roll,Liter,Set", "varchar(30)"), _decimal("UnitCost", 0, 6000), _calc("IssueValue", "IssuedQuantity * UnitCost", 0, 100000000),
            _status("IssueStatus", "Issued,Cancelled"),
        ]),
        _table("ProductionBatch", 90, "Production Batch", "Production", "production_batch", [
            _pk("ProductionBatchID"), _fk("ProductionOrderLineID", "ProductionOrderLine", "ProductionOrderLineID"),
            _cat("BatchNumber", "", "varchar(80)"), _fk("ProductID", "ProductMaster", "ProductID"), _fk("PlantID", "Plant", "PlantID"),
            _decimal("PlannedBatchQuantity", 1, 1000), _date("ActualStartDate", "date_offset"), _date("ActualEndDate", "date_offset"),
            _status("BatchStatus", "Planned,InProgress,Completed,Cancelled"),
        ]),
        _table("OperationExecution", 100, "Operation Execution", "MES", "operation_execution", [
            _pk("OperationExecutionID"), _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"),
            _fk("RoutingOperationID", "RoutingOperation", "RoutingOperationID"), _fk("WorkCenterID", "WorkCenter", "WorkCenterID"),
            _fk("ShiftID", "ProductionShift", "ShiftID"), _int("OperationSequence", 10, 999),
            _cat("ActualStartDateTime", "", "varchar(40)"), _cat("ActualEndDateTime", "", "varchar(40)"),
            _decimal("InputQuantity", 0, 1000), _calc("OutputQuantity", "InputQuantity - ScrapQuantity", 0, 1000),
            _decimal("ScrapQuantity", 0, 30), _decimal("ReworkQuantity", 0, 20), _status("OperationStatus", "Planned,InProgress,Completed,Skipped"),
        ]),
        _table("ProductionQualityInspection", 110, "Production Quality Inspection", "Quality", "production_quality_inspection", [
            _pk("ProductionInspectionID"), _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"),
            _fk("OperationExecutionID", "OperationExecution", "OperationExecutionID"), _fk("ProductID", "ProductMaster", "ProductID"),
            _date("InspectionDate", "date_offset"), _cat("InspectionType", "InProcess,Final"), _decimal("SampleQuantity", 0, 1000),
            ("InspectorName", "varchar(120)", "", None, None, "No", "", "", "", "Inspector name", "faker_person", ""),
            _status("InspectionStatus", "Passed,PartiallyPassed,Failed"),
        ]),
        _table("ProductionQualityResult", 111, "Production Quality Result", "Quality", "production_quality_result", [
            _pk("ProductionQualityResultID"), _fk("ProductionInspectionID", "ProductionQualityInspection", "ProductionInspectionID"),
            _decimal("TestedQuantity", 0, 1000), _decimal("PassedQuantity", 0, 1000), _calc("FailedQuantity", "TestedQuantity - PassedQuantity", 0, 1000),
            _cat("DefectCode", "NoDefect,TorqueDeviation,ElectricalContinuityFailure,ThermalLeak,CalibrationFailure,CosmeticDamage,ConnectorFitmentIssue", "varchar(80)"),
            _cat("DefectSeverity", "None,Low,Medium,High,Critical"), _status("ResultStatus", "Passed,PartiallyFailed,Failed"),
        ]),
        _table("ScrapReworkEvent", 120, "Scrap Rework Event", "Quality", "scrap_rework_event", [
            _pk("ScrapReworkID"), _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"),
            _fk("OperationExecutionID", "OperationExecution", "OperationExecutionID"), _fk("ProductID", "ProductMaster", "ProductID"),
            _cat("EventType", "Scrap,Rework"), _decimal("Quantity", 0, 100), _cat("ReasonCode", "None,Setup Loss,Process Defect,Material Defect,Rework Hold", "varchar(100)"),
            _decimal("CostImpact", 0, 100000), _date("EventDate", "date_offset"),
        ]),
        _table("FinishedGoodsReceipt", 130, "Finished Goods Receipt", "Inventory", "finished_goods_receipt", [
            _pk("FinishedGoodsReceiptID"), _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"),
            _fk("ProductionOrderLineID", "ProductionOrderLine", "ProductionOrderLineID"), _fk("ProductID", "ProductMaster", "ProductID"),
            _fk("PlantID", "Plant", "PlantID"), _fk("WarehouseID", "Warehouse", "WarehouseID"), _date("ReceiptDate", "date_offset"),
            _decimal("GoodQuantity", 0, 1000), _decimal("ScrapQuantity", 0, 30), _decimal("UnitCost", 0, 100000),
            _calc("ReceiptValue", "GoodQuantity * UnitCost", 0, 100000000), _status("ReceiptStatus", "Received,Cancelled"),
        ]),
        _table("FinishedGoodsInventory", 140, "Finished Goods Inventory", "Inventory", "finished_goods_inventory", [
            _pk("FinishedGoodsInventoryID"), _fk("ProductID", "ProductMaster", "ProductID"), _fk("PlantID", "Plant", "PlantID"),
            _fk("WarehouseID", "Warehouse", "WarehouseID"), _calc("OnHandQuantity", "SUM(FinishedGoodsReceipt.GoodQuantity) GROUP BY ProductID, PlantID, WarehouseID", 0, 1000000),
            _decimal("ReservedQuantity", 0, 100000), _calc("AvailableQuantity", "OnHandQuantity - ReservedQuantity", 0, 1000000),
            _calc("OnHandValue", "SUM(FinishedGoodsReceipt.ReceiptValue) GROUP BY ProductID, PlantID, WarehouseID", 0, 100000000),
            _date("LastReceiptDate", "calculated"), _status("InventoryStatus", "Available,LowStock,Hold,OutOfStock"),
        ]),
        _table("ProductionGenealogy", 150, "Production Genealogy", "MES", "production_genealogy", [
            _pk("ProductionGenealogyID"), _fk("FinishedGoodsReceiptID", "FinishedGoodsReceipt", "FinishedGoodsReceiptID"),
            _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"), _fk("MaterialIssueLineID", "MaterialIssueLine", "MaterialIssueLineID"),
            _fk("ComponentID", "ComponentMaster", "ComponentID"), _fk("InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"),
            _fk("SourceInventoryTransactionID", "InventoryTransaction", "InventoryTransactionID"), _fk("SupplierID", "SupplierMaster", "SupplierID"),
            _decimal("ConsumedQuantity", 0, 1000000), _status("TraceabilityStatus", "Traced,MissingSource"),
        ]),
        _table("ProductionCostSummary", 160, "Production Cost Summary", "Finance", "production_cost_summary", [
            _pk("ProductionCostSummaryID"), _fk("ProductionOrderLineID", "ProductionOrderLine", "ProductionOrderLineID"),
            _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"), _fk("ProductID", "ProductMaster", "ProductID"),
            _calc("MaterialCost", "SUM(MaterialIssueLine.IssueValue)", 0, 100000000), _decimal("LaborCost", 0, 10000000),
            _decimal("OverheadCost", 0, 10000000), _decimal("ScrapCost", 0, 10000000),
            _calc("TotalProductionCost", "MaterialCost + LaborCost + OverheadCost + ScrapCost", 0, 100000000),
            _calc("UnitProductionCost", "TotalProductionCost / FinishedGoodsReceipt.GoodQuantity", 0, 1000000),
        ]),
    ]


def _table(name, order, process, area, role, columns):
    return {"table": name, "order": order, "process": process, "area": area, "role": role, "rows": TARGET_ROWS[name], "columns": columns}


def _pk(name):
    return (name, "int", "PK", None, None, "No", "", "", "", f"{name} primary key", "sequence_id", "")


def _fk(name, table, column):
    return (name, "int", "FK", table, column, "No", "", "", "", f"{name} foreign key", "foreign_key", "")


def _cat(name, values, data_type="varchar(80)"):
    return (name, data_type, "", None, None, "No", values, "", "", name, "category", "")


def _status(name, values):
    return (name, "varchar(40)", "", None, None, "No", values, "", "", name, "status", "")


def _date(name, generation_type, min_value="2025-01-01", max_value="2025-12-31"):
    return (name, "date", "", None, None, "No", "", min_value, max_value, name, generation_type, "")


def _decimal(name, min_value, max_value):
    return (name, "decimal(18,2)", "", None, None, "No", "", min_value, max_value, name, "decimal_range", "")


def _int(name, min_value, max_value):
    return (name, "int", "", None, None, "No", "", min_value, max_value, name, "integer_range", "")


def _calc(name, formula, min_value, max_value):
    return (name, "decimal(18,2)", "", None, None, "No", "", min_value, max_value, name, "calculated", formula)


def _write_metadata(rows: list[dict]) -> None:
    path = INPUT_DIR / "production_v1_metadata.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=HEADERS).to_excel(writer, sheet_name="Metadata", index=False)
        summary = pd.DataFrame(
            [
                {"Metric": "Tables", "Value": len({row["TableName"] for row in rows})},
                {"Metric": "MetadataRows", "Value": len(rows)},
                {"Metric": "TotalTargetRows", "Value": sum(TARGET_ROWS.values())},
            ]
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)


def _write_erd() -> None:
    erd = """erDiagram
    ComponentMaster ||--o{ BOMLine : used_in
    Plant ||--o{ BOMHeader : has
    Plant ||--o{ WorkCenter : has
    Plant ||--o{ RoutingHeader : has
    Plant ||--o{ ProductionOrderHdr : manufactures_at
    Plant ||--o{ ProductionMaterialRequirement : requires_at
    Plant ||--o{ MaterialIssueHeader : issues_at
    Plant ||--o{ ProductionBatch : executes_at
    Plant ||--o{ FinishedGoodsReceipt : receives_at
    Plant ||--o{ FinishedGoodsInventory : stores_at
    Warehouse ||--o{ ProductionMaterialRequirement : source_stock
    Warehouse ||--o{ MaterialIssueHeader : issues_from
    Warehouse ||--o{ FinishedGoodsReceipt : receives_finished_goods
    Warehouse ||--o{ FinishedGoodsInventory : stores_finished_goods
    Inventory ||--o{ ProductionMaterialRequirement : source_inventory
    Inventory ||--o{ MaterialIssueLine : consumed_from
    InventoryTransaction ||--o{ MaterialIssueLine : source_stockin
    InventoryReceiptDetail ||--o{ MaterialIssueLine : source_receipt
    SupplierMaster ||--o{ ProductionGenealogy : traced_supplier
    InventoryTransaction ||--o{ ProductionGenealogy : traced_stockin
    InventoryReceiptDetail ||--o{ ProductionGenealogy : traced_receipt
    ComponentMaster ||--o{ ProductionGenealogy : traced_component
    ProductMaster ||--o{ BOMHeader : has_bom
    BOMHeader ||--o{ BOMLine : contains
    ProductMaster ||--o{ RoutingHeader : has_routing
    RoutingHeader ||--o{ RoutingOperation : contains
    WorkCenter ||--o{ RoutingOperation : performs
    WorkCenter ||--o{ ProductionShift : scheduled_for
    ProductionOrderHdr ||--o{ ProductionOrderLine : contains
    ProductMaster ||--o{ ProductionOrderLine : produces
    BOMHeader ||--o{ ProductionOrderLine : uses_bom
    RoutingHeader ||--o{ ProductionOrderLine : uses_routing
    ProductionOrderLine ||--o{ ProductionMaterialRequirement : requires
    BOMLine ||--o{ ProductionMaterialRequirement : derives_from
    ComponentMaster ||--o{ ProductionMaterialRequirement : required_component
    ProductionOrderHdr ||--o{ MaterialIssueHeader : has_issue
    MaterialIssueHeader ||--o{ MaterialIssueLine : contains
    ProductionMaterialRequirement ||--o{ MaterialIssueLine : fulfilled_by
    ComponentMaster ||--o{ MaterialIssueLine : issued_component
    ProductionOrderLine ||--o{ ProductionBatch : executed_as
    ProductMaster ||--o{ ProductionBatch : batch_product
    ProductionBatch ||--o{ OperationExecution : has_operations
    RoutingOperation ||--o{ OperationExecution : executed_step
    WorkCenter ||--o{ OperationExecution : executed_at
    ProductionShift ||--o{ OperationExecution : executed_in_shift
    ProductionBatch ||--o{ ProductionQualityInspection : inspected
    OperationExecution ||--o{ ProductionQualityInspection : inspected_operation
    ProductionQualityInspection ||--o{ ProductionQualityResult : has_result
    ProductionBatch ||--o{ ScrapReworkEvent : has_scrap_rework
    OperationExecution ||--o{ ScrapReworkEvent : event_at_operation
    ProductionBatch ||--o{ FinishedGoodsReceipt : produces_receipt
    ProductionOrderLine ||--o{ FinishedGoodsReceipt : output_for
    ProductMaster ||--o{ FinishedGoodsReceipt : received_product
    ProductMaster ||--o{ FinishedGoodsInventory : stocked_as
    FinishedGoodsReceipt ||--o{ FinishedGoodsInventory : rolls_up_to
    FinishedGoodsReceipt ||--o{ ProductionGenealogy : traced_output
    ProductionBatch ||--o{ ProductionGenealogy : traced_batch
    MaterialIssueLine ||--o{ ProductionGenealogy : traced_consumption
    ProductionOrderLine ||--o{ ProductionCostSummary : costed_order_line
    ProductionBatch ||--o{ ProductionCostSummary : costed_batch
    ProductMaster ||--o{ ProductionCostSummary : costed_product
"""
    (INPUT_DIR / "production_v1_erd.mmd").write_text(erd, encoding="utf-8")


def _write_scenario() -> None:
    scenario = """Production Execution module within MES context v1 synthetic data is connected to completed Procurement v2 data.

Production v1 is scoped to calendar year 2025 only. All dates should remain between 2025-01-01 and 2025-12-31.

Procurement provides component inventory through ComponentMaster, Plant, Warehouse, Inventory, InventoryTransaction, and InventoryReceiptDetail. Production must not change Procurement InventoryTransaction; Procurement InventoryTransaction remains a StockIn ledger. Production MaterialIssueLine is the production-side material consumption ledger.

Production v1 uses one Procurement Plant, one Procurement Warehouse, and Shift A only for the simplified demo operating scope. Multiple WorkCenters remain valid inside the single Plant.

Production creates finished goods and semi-finished goods using ProductMaster, BOMHeader, BOMLine, WorkCenter, RoutingHeader, RoutingOperation, and ProductionShift. Production orders define the product and quantity to build. BOM lines derive material requirements from ProductionOrderLine. MaterialIssueHeader and MaterialIssueLine consume available procurement inventory, and issued quantities must not exceed available inventory.

The corrected Production/MES lifecycle is:
Procurement Inventory -> ProductionOrderHdr -> ProductionOrderLine -> ProductionMaterialRequirement -> MaterialIssueHeader -> MaterialIssueLine -> ProductionBatch -> OperationExecution -> ProductionQualityInspection -> ProductionQualityResult -> ScrapReworkEvent -> FinishedGoodsReceipt -> FinishedGoodsInventory -> ProductionGenealogy -> ProductionCostSummary.

Production tracks BOM, routing, work centers, shifts, production orders, material issue, batch execution, operations, production quality, controlled scrap and rework, finished goods receipt, finished goods inventory, genealogy, and production cost summary.

UOM-aware quantity precision must be used. Countable products and components should use integer quantities. Bulk or measurable components may use decimal quantities.

FinishedGoodsInventory should roll up from FinishedGoodsReceipt. ProductionGenealogy should trace finished goods back to MaterialIssueLine, InventoryReceiptDetail, InventoryTransaction, ComponentMaster, and SupplierMaster.
"""
    (INPUT_DIR / "production_v1_business_scenario.txt").write_text(scenario, encoding="utf-8")


def _write_sample_plans() -> None:
    tables = [table["table"] for table in _tables()]
    valid_plan = _production_plan_payload(tables)
    invalid_plan = _production_plan_payload(tables)
    invalid_plan["module"] = "manufacturing"
    invalid_plan["generation_order"] = ["ProductionMaterialRequirement", "ProductionOrderHdr", "ProductionOrderLine"] + [
        table for table in tables if table not in {"ProductionMaterialRequirement", "ProductionOrderHdr", "ProductionOrderLine", "ProductionCostSummary"}
    ]
    invalid_plan["assumptions"] = ["Invalid module name, invalid lifecycle order, missing ProductionCostSummary, and 2026 date rule are intentional."]
    invalid_plan["date_rules"][0]["min_offset_days"] = 366
    invalid_plan["validation_rules"][0]["condition"] = "Production dates may use 2026, which is invalid for production_v1."
    (INPUT_DIR / "sample_generation_plan_production_v1_valid.json").write_text(json.dumps(valid_plan, indent=2), encoding="utf-8")
    (INPUT_DIR / "sample_generation_plan_production_v1_invalid.json").write_text(json.dumps(invalid_plan, indent=2), encoding="utf-8")


def _production_plan_payload(tables: list[str]) -> dict:
    table_definitions = _tables()
    return {
        "module": "production",
        "business_summary": "Generate 2025 Production Execution module within MES context production_v1 data connected to Procurement v2 inventory using one Plant, one Warehouse, and Shift A only.",
        "domain_profile": {
            "industry": "EV manufacturing production execution",
            "business_context": "Production consumes Procurement component inventory from the single Procurement Plant/Warehouse and creates finished goods inventory.",
            "vendor_categories": [],
            "material_categories": [
                {
                    "category_name": "EV finished goods",
                    "material_examples": ["Battery Pack", "Drive Unit", "Thermal Module"],
                    "specification_patterns": ["EA", "Unit", "Set"],
                }
            ],
            "warehouse_types": ["Raw Material", "Finished Goods Staging"],
            "plant_locations": ["Detroit, Michigan"],
            "carrier_name_patterns": [],
            "inspection_test_categories": ["InProcess", "Final"],
        },
        "table_role_mapping": [
            {"table_name": table["table"], "table_role": table["role"], "area": table["area"], "confidence": "high", "reasoning": "Production/MES v1 fixture design."}
            for table in table_definitions
        ],
        "generation_order": tables,
        "row_count_plan": [
            {"table_name": table_name, "target_rows": count, "source": "metadata", "reasoning": None}
            for table_name, count in TARGET_ROWS.items()
        ],
        "column_generation_rules": _production_column_generation_rules(table_definitions),
        "formula_rules": _production_formula_rules(),
        "date_rules": [
            {"rule_id": "prod_order_to_actual_end_2025", "earlier_table": "ProductionOrderHdr", "earlier_column": "OrderDate", "later_table": "ProductionOrderHdr", "later_column": "ActualEndDate", "min_offset_days": 0, "max_offset_days": 60, "description": "Production order dates stay inside 2025."}
        ],
        "quantity_rules": [
            {"rule_id": "issued_le_scrap_adjusted", "left_table": "ProductionMaterialRequirement", "left_column": "IssuedQuantity", "operator": "<=", "right_table": "ProductionMaterialRequirement", "right_column": "ScrapAdjustedQuantity", "description": "Issued quantity should not exceed the derived requirement."}
        ],
        "status_rules": [
            {"rule_id": "status_production_order_completed", "table_name": "ProductionOrderHdr", "status_column": "ProductionOrderStatus", "status_values": ["Completed"], "derivation_logic": "Production v1 should generate mostly or fully completed production orders.", "description": "Controlled Production v1 status guidance."},
            {"rule_id": "status_material_issue_issued", "table_name": "MaterialIssueHeader", "status_column": "IssueStatus", "status_values": ["Issued"], "derivation_logic": "Material issue headers should be Issued when production consumes inventory.", "description": "Controlled Production v1 status guidance."},
        ],
        "validation_rules": _production_validation_rules(),
        "assumptions": [
            "Production v1 / production_v1 is 2025-only.",
            "Production v1 uses one Procurement Plant, one Procurement Warehouse, and Shift A only.",
            "Production consumes Procurement Inventory and does not change Procurement InventoryTransaction.",
            "MaterialIssueLine references InventoryTransaction and InventoryReceiptDetail.",
            "ProductionGenealogy traces back to MaterialIssueLine, InventoryReceiptDetail, InventoryTransaction, ComponentMaster, and SupplierMaster.",
            "Countable UOMs use integer quantities; bulk/measurable UOMs may use decimals.",
        ],
        "warnings": [],
    }


def _production_column_generation_rules(table_definitions: list[dict]) -> list[dict]:
    rules = []
    for table in table_definitions:
        for column in table["columns"]:
            column_name, _data_type, key_type, _related_table, _related_column, _nullable, allowed_values, min_value, max_value, purpose, generation_type, _formula = column
            if key_type in {"PK", "FK"} or generation_type == "calculated":
                continue
            rules.append(
                {
                    "table_name": table["table"],
                    "column_name": column_name,
                    "generation_type": generation_type,
                    "strategy": purpose or column_name,
                    "allowed_values": [value for value in str(allowed_values).split(",") if value],
                    "min_value": min_value if min_value != "" else None,
                    "max_value": max_value if max_value != "" else None,
                    "nullable_strategy": "never_null",
                    "depends_on_columns": [],
                    "notes": None,
                }
            )
    return rules


def _production_formula_rules() -> list[dict]:
    return [
        _formula("issue_value", "MaterialIssueLine", "IssueValue", "multiply", ["IssuedQuantity", "UnitCost"], "IssuedQuantity * UnitCost"),
        _formula("operation_output_quantity", "OperationExecution", "OutputQuantity", "subtract", ["InputQuantity", "ScrapQuantity"], "InputQuantity - ScrapQuantity"),
        _formula("quality_failed_quantity", "ProductionQualityResult", "FailedQuantity", "subtract", ["TestedQuantity", "PassedQuantity"], "TestedQuantity - PassedQuantity"),
        _formula("fg_receipt_value", "FinishedGoodsReceipt", "ReceiptValue", "multiply", ["GoodQuantity", "UnitCost"], "GoodQuantity * UnitCost"),
        {
            "rule_id": "fg_inventory_onhand_quantity",
            "rule_type": "aggregate",
            "target_table": "FinishedGoodsInventory",
            "target_column": "OnHandQuantity",
            "operation": "sum",
            "input_columns": [],
            "source_table": "FinishedGoodsReceipt",
            "source_column": "GoodQuantity",
            "relationship_key": None,
            "group_by_columns": ["ProductID", "PlantID", "WarehouseID"],
            "formula": "SUM(FinishedGoodsReceipt.GoodQuantity) GROUP BY ProductID, PlantID, WarehouseID",
            "denominator_column": None,
            "denominator_guard": False,
            "tolerance_type": "absolute",
            "tolerance_value": 0.0001,
            "description": "Finished goods inventory quantity rollup.",
        },
        _formula("production_total_cost", "ProductionCostSummary", "TotalProductionCost", "add", ["MaterialCost", "LaborCost", "OverheadCost", "ScrapCost"], "MaterialCost + LaborCost + OverheadCost + ScrapCost"),
    ]


def _formula(rule_id: str, table: str, column: str, operation: str, inputs: list[str], formula: str) -> dict:
    return {
        "rule_id": rule_id,
        "rule_type": "row_level",
        "target_table": table,
        "target_column": column,
        "operation": operation,
        "input_columns": inputs,
        "source_table": None,
        "source_column": None,
        "relationship_key": None,
        "group_by_columns": [],
        "formula": formula,
        "denominator_column": None,
        "denominator_guard": False,
        "tolerance_type": "absolute",
        "tolerance_value": 0.01,
        "description": None,
    }


def _production_validation_rules() -> list[dict]:
    return [
        {"rule_id": "PROD_V1_2025_ONLY", "rule_type": "date_order", "table_name": None, "column_name": None, "condition": "Production dates must stay within 2025-01-01 to 2025-12-31.", "severity": "error", "description": "Production v1 is 2025-only."},
        {"rule_id": "PROD_V1_REQUIRED_QUANTITY", "rule_type": "formula_check", "table_name": "ProductionMaterialRequirement", "column_name": "RequiredQuantity", "condition": "RequiredQuantity = ProductionOrderLine.PlannedQuantity * BOMLine.ComponentQuantity.", "severity": "error", "description": "BOM-derived requirement formula."},
        {"rule_id": "PROD_V1_SCRAP_ADJUSTED_QUANTITY", "rule_type": "formula_check", "table_name": "ProductionMaterialRequirement", "column_name": "ScrapAdjustedQuantity", "condition": "ScrapAdjustedQuantity = RequiredQuantity * (1 + ScrapFactorPct / 100).", "severity": "error", "description": "Scrap-adjusted material requirement formula."},
        {"rule_id": "PROD_V1_MATERIAL_ISSUE_LE_AVAILABLE", "rule_type": "quantity_check", "table_name": "MaterialIssueLine", "column_name": "IssuedQuantity", "condition": "IssuedQuantity must not exceed Inventory.AvailableQuantity.", "severity": "error", "description": "Production consumes only available procurement inventory."},
        {"rule_id": "PROD_V1_GENEALOGY_TRACE", "rule_type": "fk_check", "table_name": "ProductionGenealogy", "column_name": "InventoryReceiptDetailID", "condition": "ProductionGenealogy traces back to MaterialIssueLine, InventoryReceiptDetail, InventoryTransaction, ComponentMaster, and SupplierMaster.", "severity": "error", "description": "Production genealogy must preserve procurement receipt lineage."},
        {"rule_id": "PROD_V1_UOM_PRECISION", "rule_type": "quantity_check", "table_name": None, "column_name": None, "condition": "Countable UOMs use integer quantities; bulk/measurable UOMs may use decimals.", "severity": "error", "description": "Use shared UOM-aware quantity precision."},
        {"rule_id": "PROD_V1_UNIT_COST", "rule_type": "formula_check", "table_name": "ProductionCostSummary", "column_name": "UnitProductionCost", "condition": "UnitProductionCost = TotalProductionCost / FinishedGoodsReceipt.GoodQuantity with denominator guard.", "severity": "error", "description": "Production unit cost summary formula."},
    ]


if __name__ == "__main__":
    raise SystemExit(main())
