"""Production Execution module within MES context v1 reconciliation and data quality rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from procurement_data_generator.modules.production.master_generator import PRODUCTION_MASTER_TABLES
from procurement_data_generator.modules.production.transaction_generator import PRODUCTION_TRANSACTION_TABLES
from procurement_data_generator.modules.shared.operating_scope import (
    get_allowed_shift_codes,
    get_expected_plant_count,
    get_expected_warehouse_count,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_default_industry_profile
from procurement_data_generator.modules.shared.quantity_precision import is_whole_quantity, requires_integer_quantity


UPSTREAM_TABLES = (
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "Inventory",
    "InventoryTransaction",
    "InventoryReceiptDetail",
    "SupplierMaster",
)
PRODUCTION_TABLES = (*PRODUCTION_MASTER_TABLES, *PRODUCTION_TRANSACTION_TABLES)


@dataclass(frozen=True)
class ProductionQualityIssue:
    """One Production data quality issue."""

    severity: str
    check_type: str
    table_name: str | None
    column_name: str | None
    message: str
    suggested_fix: str
    sample_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ProductionQualityResult:
    """Production reconciliation result."""

    status: str
    errors: list[ProductionQualityIssue]
    warnings: list[ProductionQualityIssue]
    table_row_counts: dict[str, int]
    scorecard: dict[str, int]
    summary_metrics: dict[str, Any]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def get_production_reconciler_rules() -> tuple[str, ...]:
    """Return active Production Execution reconciliation rule names."""

    return (
        "table_existence",
        "master_fk_lineage",
        "production_transaction_lineage",
        "material_issue_inventory_cap",
        "formula_reconciliation",
        "finished_goods_inventory_rollup",
        "production_genealogy_traceability",
        "production_cost_summary",
        "date_scope_2025",
        "uom_quantity_precision",
        "single_plant_warehouse_shift_a_scope",
    )


def reconcile_production_data(
    production_data: dict[str, pd.DataFrame],
    upstream_data: dict[str, pd.DataFrame],
    target_row_counts: dict[str, int] | None = None,
) -> ProductionQualityResult:
    """Run Production Execution module within MES context v1 reconciliation over generated data and upstream Procurement data."""

    errors: list[ProductionQualityIssue] = []
    warnings: list[ProductionQualityIssue] = []
    scorecard: dict[str, int] = {}
    table_row_counts = {table: len(df) for table, df in production_data.items()}

    _check_required_tables(production_data, upstream_data, errors, scorecard)
    if errors:
        return _result(errors, warnings, table_row_counts, scorecard, production_data)

    _check_row_count_warnings(production_data, target_row_counts or {}, warnings)
    _check_operating_scope(production_data, upstream_data, errors, scorecard)
    _check_master_data(production_data, upstream_data, errors, scorecard)
    _check_transaction_data(production_data, upstream_data, errors, scorecard)
    _check_dates(production_data, errors, scorecard)
    _check_uom_precision(production_data, upstream_data, errors, scorecard)

    return _result(errors, warnings, table_row_counts, scorecard, production_data)


def _check_required_tables(production_data, upstream_data, errors, scorecard) -> None:
    issue_count = 0
    for table_name in PRODUCTION_TABLES:
        if table_name not in production_data:
            issue_count += 1
            _error(errors, "PROD_MISSING_TABLE", table_name, None, f"Required Production table {table_name} is missing.", "Generate all 21 Production v1 tables.")
    for table_name in UPSTREAM_TABLES:
        if table_name not in upstream_data:
            issue_count += 1
            _error(errors, "PROD_MISSING_UPSTREAM_TABLE", table_name, None, f"Required upstream Procurement table {table_name} is missing.", "Provide Procurement v2 final_data as upstream input.")
    scorecard["missing_required_tables"] = issue_count


def _check_operating_scope(d, u, errors, scorecard) -> None:
    before = len(errors)
    expected_plant_count = get_expected_plant_count()
    expected_warehouse_count = get_expected_warehouse_count()
    allowed_shift_codes = set(get_allowed_shift_codes())

    if len(u["Plant"]) != expected_plant_count:
        _error(errors, "PROD_OPERATING_SCOPE_UPSTREAM_PLANT_COUNT", "Plant", None, f"Upstream Procurement Plant row count must be {expected_plant_count}.", "Run Procurement v2 with the shared one-plant operating scope.")
    if len(u["Warehouse"]) != expected_warehouse_count:
        _error(errors, "PROD_OPERATING_SCOPE_UPSTREAM_WAREHOUSE_COUNT", "Warehouse", None, f"Upstream Procurement Warehouse row count must be {expected_warehouse_count}.", "Run Procurement v2 with the shared one-warehouse operating scope.")

    if "PlantID" not in u["Plant"].columns or "WarehouseID" not in u["Warehouse"].columns:
        scorecard["operating_scope_issues"] = len(errors) - before
        return

    plant_ids = u["Plant"]["PlantID"].dropna().unique()
    warehouse_ids = u["Warehouse"]["WarehouseID"].dropna().unique()
    if len(plant_ids) != 1 or len(warehouse_ids) != 1:
        scorecard["operating_scope_issues"] = len(errors) - before
        return

    single_plant_id = plant_ids[0]
    single_warehouse_id = warehouse_ids[0]

    if "PlantID" in u["Warehouse"].columns:
        _bad_rows(
            u["Warehouse"][u["Warehouse"]["PlantID"] != single_plant_id],
            errors,
            "PROD_OPERATING_SCOPE_UPSTREAM_WAREHOUSE_PLANT",
            "Warehouse",
            "PlantID",
            "Upstream Warehouse.PlantID must reference the single upstream PlantID.",
        )

    for table_name, dataframe in d.items():
        if "PlantID" in dataframe.columns:
            _bad_rows(
                dataframe[dataframe["PlantID"] != single_plant_id],
                errors,
                "PROD_OPERATING_SCOPE_PLANT_REFERENCE",
                table_name,
                "PlantID",
                f"{table_name}.PlantID must use the single upstream Procurement PlantID.",
            )
        if "WarehouseID" in dataframe.columns:
            _bad_rows(
                dataframe[dataframe["WarehouseID"] != single_warehouse_id],
                errors,
                "PROD_OPERATING_SCOPE_WAREHOUSE_REFERENCE",
                table_name,
                "WarehouseID",
                f"{table_name}.WarehouseID must use the single upstream Procurement WarehouseID.",
            )

    invalid_shifts = d["ProductionShift"][~d["ProductionShift"]["ShiftCode"].isin(allowed_shift_codes)]
    _bad_rows(
        invalid_shifts,
        errors,
        "PROD_OPERATING_SCOPE_SHIFT_CODE",
        "ProductionShift",
        "ShiftCode",
        "ProductionShift must use only the shared operating scope shift code A.",
    )
    _bad_rows(
        d["ProductionShift"][d["ProductionShift"]["PlantID"] != single_plant_id],
        errors,
        "PROD_OPERATING_SCOPE_SHIFT_PLANT",
        "ProductionShift",
        "PlantID",
        "ProductionShift.PlantID must equal the single upstream Procurement PlantID.",
    )

    shift_refs = d["OperationExecution"].merge(
        d["ProductionShift"][["ShiftID", "ShiftCode", "WorkCenterID"]],
        on="ShiftID",
        how="left",
        suffixes=("", "_Shift"),
    )
    _bad_rows(
        shift_refs[~shift_refs["ShiftCode"].isin(allowed_shift_codes)],
        errors,
        "PROD_OPERATING_SCOPE_OPERATION_SHIFT_CODE",
        "OperationExecution",
        "ShiftID",
        "OperationExecution.ShiftID must reference a ProductionShift row with ShiftCode A.",
    )
    _bad_rows(
        shift_refs[shift_refs["WorkCenterID"] != shift_refs["WorkCenterID_Shift"]],
        errors,
        "PROD_OPERATING_SCOPE_OPERATION_SHIFT_WORKCENTER",
        "OperationExecution",
        "ShiftID",
        "OperationExecution.WorkCenterID must match the referenced Shift A WorkCenterID.",
    )
    scorecard["operating_scope_issues"] = len(errors) - before


def _check_row_count_warnings(production_data, target_row_counts, warnings) -> None:
    for table_name in PRODUCTION_TRANSACTION_TABLES:
        target = target_row_counts.get(table_name)
        if target and table_name in production_data and len(production_data[table_name]) < target:
            _warning(
                warnings,
                "PROD_ROW_COUNT_BELOW_TARGET",
                table_name,
                None,
                f"{table_name} row count is below metadata target because generation is constrained by available inventory or actual scrap/rework events.",
                "Accept when all lineage, formulas, and rollups pass; otherwise increase upstream inventory or lower target rows.",
            )


def _check_master_data(d, u, errors, scorecard) -> None:
    before = len(errors)
    _unique(d, "ProductMaster", "ProductID", errors)
    _unique(d, "ProductMaster", "ProductCode", errors)
    _allowed(d, "ProductMaster", "ProductType", {"FinishedGood", "SemiFinished"}, errors)
    _allowed(d, "ProductMaster", "ProductStatus", {"Active", "Inactive"}, errors)
    _fk(d["BOMHeader"], "BOMHeader", "ProductID", d["ProductMaster"], "ProductID", errors)
    _fk(d["BOMHeader"], "BOMHeader", "PlantID", u["Plant"], "PlantID", errors)
    _date_order(d["BOMHeader"], "BOMHeader", "EffectiveFromDate", "EffectiveToDate", errors)
    _allowed(d, "BOMHeader", "BOMStatus", {"Active", "Inactive"}, errors)
    _fk(d["BOMLine"], "BOMLine", "BOMID", d["BOMHeader"], "BOMID", errors)
    _fk(d["BOMLine"], "BOMLine", "ComponentID", u["ComponentMaster"], "ComponentID", errors)
    _component_uom_match(d["BOMLine"], u["ComponentMaster"], "BOMLine", "ComponentQuantity", errors)
    _positive(d["BOMLine"], "BOMLine", "ComponentQuantity", errors)
    _range(d["BOMLine"], "BOMLine", "ScrapFactorPct", 0, 3, errors)
    _allowed(d, "BOMLine", "IsCriticalComponent", {0, 1}, errors)
    _allowed(d, "BOMLine", "BOMLineStatus", {"Active", "Inactive"}, errors)
    _fk(d["WorkCenter"], "WorkCenter", "PlantID", u["Plant"], "PlantID", errors)
    _unique(d, "WorkCenter", "WorkCenterCode", errors)
    _positive(d["WorkCenter"], "WorkCenter", "CapacityPerShift", errors)
    _allowed(d, "WorkCenter", "WorkCenterStatus", {"Active", "Inactive", "Maintenance"}, errors)
    _fk(d["RoutingHeader"], "RoutingHeader", "ProductID", d["ProductMaster"], "ProductID", errors)
    _fk(d["RoutingHeader"], "RoutingHeader", "PlantID", u["Plant"], "PlantID", errors)
    _allowed(d, "RoutingHeader", "RoutingStatus", {"Active", "Inactive"}, errors)
    _fk(d["RoutingOperation"], "RoutingOperation", "RoutingID", d["RoutingHeader"], "RoutingID", errors)
    _fk(d["RoutingOperation"], "RoutingOperation", "WorkCenterID", d["WorkCenter"], "WorkCenterID", errors)
    _routing_operation_alignment(d, errors)
    _positive_or_zero(d["RoutingOperation"], "RoutingOperation", "SetupTimeMinutes", errors)
    _positive(d["RoutingOperation"], "RoutingOperation", "RunTimeMinutesPerUnit", errors)
    _range(d["RoutingOperation"], "RoutingOperation", "StandardYieldPct", 0, 100, errors)
    _allowed(d, "RoutingOperation", "OperationStatus", {"Active", "Inactive"}, errors)
    _fk(d["ProductionShift"], "ProductionShift", "PlantID", u["Plant"], "PlantID", errors)
    _fk(d["ProductionShift"], "ProductionShift", "WorkCenterID", d["WorkCenter"], "WorkCenterID", errors)
    _shift_alignment(d, errors)
    _allowed(d, "ProductionShift", "ShiftCode", set(get_allowed_shift_codes()), errors)
    _positive(d["ProductionShift"], "ProductionShift", "PlannedHours", errors)
    scorecard["master_data_issues"] = len(errors) - before


def _check_transaction_data(d, u, errors, scorecard) -> None:
    before = len(errors)
    _unique(d, "ProductionOrderHdr", "ProductionOrderID", errors)
    _fk(d["ProductionOrderHdr"], "ProductionOrderHdr", "PlantID", u["Plant"], "PlantID", errors)
    _date_order(d["ProductionOrderHdr"], "ProductionOrderHdr", "OrderDate", "PlannedStartDate", errors)
    _date_order(d["ProductionOrderHdr"], "ProductionOrderHdr", "PlannedStartDate", "PlannedEndDate", errors)
    _date_order(d["ProductionOrderHdr"], "ProductionOrderHdr", "ActualStartDate", "ActualEndDate", errors)
    _allowed(d, "ProductionOrderHdr", "ProductionOrderStatus", {"Planned", "Released", "InProduction", "Completed", "Cancelled"}, errors)
    _allowed(d, "ProductionOrderHdr", "Priority", {"Low", "Normal", "High", "Urgent"}, errors)
    _production_order_line(d, errors)
    _material_requirements(d, u, errors)
    _material_issue(d, u, errors)
    _production_batches(d, errors)
    _operation_execution(d, errors)
    _quality(d, errors)
    _scrap_rework(d, errors)
    _finished_goods(d, u, errors)
    _genealogy(d, u, errors)
    _cost_summary(d, errors)
    scorecard["transaction_data_issues"] = len(errors) - before


def _production_order_line(d, errors) -> None:
    _unique(d, "ProductionOrderLine", "ProductionOrderLineID", errors)
    _fk(d["ProductionOrderLine"], "ProductionOrderLine", "ProductionOrderID", d["ProductionOrderHdr"], "ProductionOrderID", errors)
    _fk(d["ProductionOrderLine"], "ProductionOrderLine", "ProductID", d["ProductMaster"], "ProductID", errors)
    _fk(d["ProductionOrderLine"], "ProductionOrderLine", "BOMID", d["BOMHeader"], "BOMID", errors)
    _fk(d["ProductionOrderLine"], "ProductionOrderLine", "RoutingID", d["RoutingHeader"], "RoutingID", errors)
    line = d["ProductionOrderLine"].merge(d["BOMHeader"][["BOMID", "ProductID"]], on="BOMID", suffixes=("", "_BOM"))
    _bad_rows(line[line["ProductID"] != line["ProductID_BOM"]], errors, "PROD_POL_BOM_PRODUCT_MISMATCH", "ProductionOrderLine", "BOMID", "BOMHeader.ProductID must match ProductionOrderLine.ProductID.")
    line = d["ProductionOrderLine"].merge(d["RoutingHeader"][["RoutingID", "ProductID"]], on="RoutingID", suffixes=("", "_Routing"))
    _bad_rows(line[line["ProductID"] != line["ProductID_Routing"]], errors, "PROD_POL_ROUTING_PRODUCT_MISMATCH", "ProductionOrderLine", "RoutingID", "RoutingHeader.ProductID must match ProductionOrderLine.ProductID.")
    _positive(d["ProductionOrderLine"], "ProductionOrderLine", "PlannedQuantity", errors)
    _almost_equal(d["ProductionOrderLine"], "ProductionOrderLine", "ReleasedQuantity", d["ProductionOrderLine"]["PlannedQuantity"], errors, "ReleasedQuantity must equal PlannedQuantity.")
    _almost_equal(d["ProductionOrderLine"], "ProductionOrderLine", "CompletedQuantity", d["ProductionOrderLine"]["GoodQuantity"] + d["ProductionOrderLine"]["ScrapQuantity"], errors, "CompletedQuantity must equal GoodQuantity + ScrapQuantity.")
    _positive(d["ProductionOrderLine"], "ProductionOrderLine", "GoodQuantity", errors)
    _positive_or_zero(d["ProductionOrderLine"], "ProductionOrderLine", "ScrapQuantity", errors)
    products = d["ProductMaster"][["ProductID", "UOM"]]
    merged = d["ProductionOrderLine"].merge(products, on="ProductID", suffixes=("", "_Product"))
    _bad_rows(merged[merged["UOM"] != merged["UOM_Product"]], errors, "PROD_POL_UOM_MISMATCH", "ProductionOrderLine", "UOM", "ProductionOrderLine.UOM must match ProductMaster.UOM.")


def _material_requirements(d, u, errors) -> None:
    _unique(d, "ProductionMaterialRequirement", "MaterialRequirementID", errors)
    _fk(d["ProductionMaterialRequirement"], "ProductionMaterialRequirement", "ProductionOrderLineID", d["ProductionOrderLine"], "ProductionOrderLineID", errors)
    _fk(d["ProductionMaterialRequirement"], "ProductionMaterialRequirement", "BOMLineID", d["BOMLine"], "BOMLineID", errors)
    _fk(d["ProductionMaterialRequirement"], "ProductionMaterialRequirement", "ComponentID", u["ComponentMaster"], "ComponentID", errors)
    _fk(d["ProductionMaterialRequirement"], "ProductionMaterialRequirement", "PlantID", u["Plant"], "PlantID", errors)
    _fk(d["ProductionMaterialRequirement"], "ProductionMaterialRequirement", "WarehouseID", u["Warehouse"], "WarehouseID", errors)
    _fk(d["ProductionMaterialRequirement"], "ProductionMaterialRequirement", "InventoryID", u["Inventory"], "InventoryID", errors)
    req = d["ProductionMaterialRequirement"].merge(d["ProductionOrderLine"][["ProductionOrderLineID", "PlannedQuantity"]], on="ProductionOrderLineID").merge(d["BOMLine"][["BOMLineID", "ComponentID", "ComponentQuantity", "ScrapFactorPct"]], on="BOMLineID", suffixes=("", "_BOM"))
    _bad_rows(req[req["ComponentID"] != req["ComponentID_BOM"]], errors, "PROD_REQ_COMPONENT_MISMATCH", "ProductionMaterialRequirement", "ComponentID", "Requirement component must match BOMLine.ComponentID.")
    _almost_equal(req, "ProductionMaterialRequirement", "RequiredQuantity", req["PlannedQuantity"] * req["ComponentQuantity"], errors, "RequiredQuantity must equal PlannedQuantity * ComponentQuantity.")
    _almost_equal(req, "ProductionMaterialRequirement", "ScrapAdjustedQuantity", req["RequiredQuantity"] * (1 + req["ScrapFactorPct"] / 100), errors, "ScrapAdjustedQuantity must equal RequiredQuantity * (1 + ScrapFactorPct / 100).", tolerance=1.01)
    over = req[req["IssuedQuantity"] > req["ScrapAdjustedQuantity"] + 0.0001]
    _bad_rows(over, errors, "PROD_REQ_ISSUED_EXCEEDS_SCRAP_ADJUSTED", "ProductionMaterialRequirement", "IssuedQuantity", "IssuedQuantity must not exceed ScrapAdjustedQuantity.")
    inv = u["Inventory"][["InventoryID", "ComponentID", "PlantID", "WarehouseID"]]
    req_inv = d["ProductionMaterialRequirement"].merge(inv, on="InventoryID", suffixes=("", "_Inventory"))
    bad = req_inv[(req_inv["ComponentID"] != req_inv["ComponentID_Inventory"]) | (req_inv["PlantID"] != req_inv["PlantID_Inventory"]) | (req_inv["WarehouseID"] != req_inv["WarehouseID_Inventory"])]
    _bad_rows(bad, errors, "PROD_REQ_INVENTORY_LINEAGE", "ProductionMaterialRequirement", "InventoryID", "Inventory ComponentID/PlantID/WarehouseID must match requirement lineage.")


def _material_issue(d, u, errors) -> None:
    _unique(d, "MaterialIssueHeader", "MaterialIssueID", errors)
    _fk(d["MaterialIssueHeader"], "MaterialIssueHeader", "ProductionOrderID", d["ProductionOrderHdr"], "ProductionOrderID", errors)
    _fk(d["MaterialIssueHeader"], "MaterialIssueHeader", "PlantID", u["Plant"], "PlantID", errors)
    _fk(d["MaterialIssueHeader"], "MaterialIssueHeader", "WarehouseID", u["Warehouse"], "WarehouseID", errors)
    _allowed(d, "MaterialIssueHeader", "IssueStatus", {"Planned", "Issued", "Cancelled"}, errors)
    _unique(d, "MaterialIssueLine", "MaterialIssueLineID", errors)
    _fk(d["MaterialIssueLine"], "MaterialIssueLine", "MaterialIssueID", d["MaterialIssueHeader"], "MaterialIssueID", errors)
    _fk(d["MaterialIssueLine"], "MaterialIssueLine", "MaterialRequirementID", d["ProductionMaterialRequirement"], "MaterialRequirementID", errors)
    _fk(d["MaterialIssueLine"], "MaterialIssueLine", "InventoryID", u["Inventory"], "InventoryID", errors)
    _fk(d["MaterialIssueLine"], "MaterialIssueLine", "SourceInventoryTransactionID", u["InventoryTransaction"], "InventoryTransactionID", errors)
    _fk(d["MaterialIssueLine"], "MaterialIssueLine", "InventoryReceiptDetailID", u["InventoryReceiptDetail"], "InventoryReceiptDetailID", errors)
    issue = d["MaterialIssueLine"].merge(d["ProductionMaterialRequirement"][["MaterialRequirementID", "ComponentID", "InventoryID", "IssuedQuantity"]], on="MaterialRequirementID", suffixes=("", "_Req"))
    bad = issue[(issue["ComponentID"] != issue["ComponentID_Req"]) | (issue["InventoryID"] != issue["InventoryID_Req"])]
    _bad_rows(bad, errors, "PROD_MIL_REQUIREMENT_LINEAGE", "MaterialIssueLine", "MaterialRequirementID", "MaterialIssueLine must match requirement component and inventory.")
    _almost_equal(issue, "MaterialIssueLine", "IssuedQuantity", issue["IssuedQuantity_Req"], errors, "MaterialIssueLine.IssuedQuantity must equal requirement IssuedQuantity.")
    _positive(issue, "MaterialIssueLine", "IssuedQuantity", errors)
    issued = d["MaterialIssueLine"].groupby("InventoryID")["IssuedQuantity"].sum()
    available = u["Inventory"].set_index("InventoryID")["AvailableQuantity"]
    for inventory_id, quantity in issued.items():
        if quantity > available.get(inventory_id, 0) + 0.0001:
            _error(errors, "PROD_MATERIAL_ISSUE_EXCEEDS_INVENTORY", "MaterialIssueLine", "IssuedQuantity", f"IssuedQuantity exceeds available inventory for InventoryID {inventory_id}.", "Reduce production demand or allocate a different inventory bucket.")
    issued_txn = d["MaterialIssueLine"].groupby("SourceInventoryTransactionID")["IssuedQuantity"].sum()
    txn_qty = u["InventoryTransaction"].set_index("InventoryTransactionID")["TransactionQuantity"]
    for txn_id, quantity in issued_txn.items():
        if quantity > txn_qty.get(txn_id, 0) + 0.0001:
            _error(errors, "PROD_MATERIAL_ISSUE_EXCEEDS_SOURCE_TXN", "MaterialIssueLine", "SourceInventoryTransactionID", f"IssuedQuantity exceeds source transaction quantity for InventoryTransactionID {txn_id}.", "Track source transaction consumption and allocate within stock-in quantity.")
    txn = u["InventoryTransaction"][["InventoryTransactionID", "ComponentID", "PlantID", "WarehouseID", "UnitPrice", "ReferenceDocument"]]
    issue_txn = d["MaterialIssueLine"].merge(txn, left_on="SourceInventoryTransactionID", right_on="InventoryTransactionID", suffixes=("", "_Txn"))
    _bad_rows(issue_txn[issue_txn["ComponentID"] != issue_txn["ComponentID_Txn"]], errors, "PROD_MIL_TXN_COMPONENT_LINEAGE", "MaterialIssueLine", "SourceInventoryTransactionID", "Source InventoryTransaction.ComponentID must match issue component.")
    _almost_equal(issue_txn, "MaterialIssueLine", "UnitCost", issue_txn["UnitPrice"], errors, "MaterialIssueLine.UnitCost must match InventoryTransaction.UnitPrice.")
    _almost_equal(d["MaterialIssueLine"], "MaterialIssueLine", "IssueValue", d["MaterialIssueLine"]["IssuedQuantity"] * d["MaterialIssueLine"]["UnitCost"], errors, "IssueValue must equal IssuedQuantity * UnitCost.", tolerance=0.011)
    _component_uom_match(d["MaterialIssueLine"], u["ComponentMaster"], "MaterialIssueLine", "IssuedQuantity", errors)


def _production_batches(d, errors) -> None:
    _unique(d, "ProductionBatch", "ProductionBatchID", errors)
    _fk(d["ProductionBatch"], "ProductionBatch", "ProductionOrderLineID", d["ProductionOrderLine"], "ProductionOrderLineID", errors)
    batch = d["ProductionBatch"].merge(d["ProductionOrderLine"][["ProductionOrderLineID", "ProductionOrderID", "ProductID", "PlannedQuantity"]], on="ProductionOrderLineID", suffixes=("", "_Line")).merge(d["ProductionOrderHdr"][["ProductionOrderID", "PlantID"]], on="ProductionOrderID", suffixes=("", "_Order"))
    bad = batch[(batch["ProductID"] != batch["ProductID_Line"]) | (batch["PlantID"] != batch["PlantID_Order"])]
    _bad_rows(bad, errors, "PROD_BATCH_LINEAGE", "ProductionBatch", "ProductionOrderLineID", "Batch ProductID and PlantID must match order line/header.")
    _almost_equal(batch, "ProductionBatch", "PlannedBatchQuantity", batch["PlannedQuantity"], errors, "PlannedBatchQuantity must align with ProductionOrderLine.PlannedQuantity.")
    _date_order(d["ProductionBatch"], "ProductionBatch", "ActualStartDate", "ActualEndDate", errors)
    _allowed(d, "ProductionBatch", "BatchStatus", {"Planned", "InProgress", "Completed", "Cancelled"}, errors)


def _operation_execution(d, errors) -> None:
    _unique(d, "OperationExecution", "OperationExecutionID", errors)
    _fk(d["OperationExecution"], "OperationExecution", "ProductionBatchID", d["ProductionBatch"], "ProductionBatchID", errors)
    _fk(d["OperationExecution"], "OperationExecution", "RoutingOperationID", d["RoutingOperation"], "RoutingOperationID", errors)
    _fk(d["OperationExecution"], "OperationExecution", "ShiftID", d["ProductionShift"], "ShiftID", errors)
    op = d["OperationExecution"].merge(d["RoutingOperation"][["RoutingOperationID", "WorkCenterID", "OperationSequence"]], on="RoutingOperationID", suffixes=("", "_Routing"))
    bad = op[(op["WorkCenterID"] != op["WorkCenterID_Routing"]) | (op["OperationSequence"] != op["OperationSequence_Routing"])]
    _bad_rows(bad, errors, "PROD_OPERATION_ROUTING_LINEAGE", "OperationExecution", "RoutingOperationID", "OperationExecution must match RoutingOperation work center and sequence.")
    shift = d["OperationExecution"].merge(d["ProductionShift"][["ShiftID", "WorkCenterID"]], on="ShiftID", suffixes=("", "_Shift"))
    _bad_rows(shift[shift["WorkCenterID"] != shift["WorkCenterID_Shift"]], errors, "PROD_OPERATION_SHIFT_LINEAGE", "OperationExecution", "ShiftID", "ProductionShift.WorkCenterID must match OperationExecution.WorkCenterID.")
    for batch_id, rows in d["OperationExecution"].sort_values("OperationSequence").groupby("ProductionBatchID"):
        previous_output = None
        batch_qty = float(d["ProductionBatch"].set_index("ProductionBatchID").loc[batch_id, "PlannedBatchQuantity"])
        for idx, row in enumerate(rows.itertuples(index=False)):
            expected_input = batch_qty if idx == 0 else previous_output
            if abs(float(row.InputQuantity) - expected_input) > 0.0001:
                _error(errors, "PROD_OPERATION_INPUT_FLOW", "OperationExecution", "InputQuantity", "Operation input quantity does not follow batch/previous operation output.", "Set first input to batch quantity and later inputs to previous output.")
            if abs(float(row.OutputQuantity) - (float(row.InputQuantity) - float(row.ScrapQuantity))) > 0.0001:
                _error(errors, "PROD_OPERATION_OUTPUT_FORMULA", "OperationExecution", "OutputQuantity", "OutputQuantity must equal InputQuantity - ScrapQuantity.", "Recalculate operation output.")
            previous_output = float(row.OutputQuantity)
    _positive_or_zero(d["OperationExecution"], "OperationExecution", "ScrapQuantity", errors)
    _positive_or_zero(d["OperationExecution"], "OperationExecution", "ReworkQuantity", errors)
    _allowed(d, "OperationExecution", "OperationStatus", {"Planned", "InProgress", "Completed", "Skipped"}, errors)


def _quality(d, errors) -> None:
    _unique(d, "ProductionQualityInspection", "ProductionInspectionID", errors)
    _fk(d["ProductionQualityInspection"], "ProductionQualityInspection", "ProductionBatchID", d["ProductionBatch"], "ProductionBatchID", errors)
    _fk(d["ProductionQualityInspection"], "ProductionQualityInspection", "OperationExecutionID", d["OperationExecution"], "OperationExecutionID", errors)
    insp = d["ProductionQualityInspection"].merge(d["ProductionBatch"][["ProductionBatchID", "ProductID"]], on="ProductionBatchID", suffixes=("", "_Batch")).merge(d["OperationExecution"][["OperationExecutionID", "OutputQuantity"]], on="OperationExecutionID")
    _bad_rows(insp[insp["ProductID"] != insp["ProductID_Batch"]], errors, "PROD_INSPECTION_PRODUCT_LINEAGE", "ProductionQualityInspection", "ProductID", "Inspection ProductID must match batch ProductID.")
    _bad_rows(insp[insp["SampleQuantity"] > insp["OutputQuantity"] + 0.0001], errors, "PROD_INSPECTION_SAMPLE_EXCEEDS_OUTPUT", "ProductionQualityInspection", "SampleQuantity", "SampleQuantity must not exceed operation OutputQuantity.")
    _allowed(d, "ProductionQualityInspection", "InspectionType", {"InProcess", "Final"}, errors)
    _allowed(d, "ProductionQualityInspection", "InspectionStatus", {"Passed", "PartiallyPassed", "Failed"}, errors)
    _unique(d, "ProductionQualityResult", "ProductionQualityResultID", errors)
    _fk(d["ProductionQualityResult"], "ProductionQualityResult", "ProductionInspectionID", d["ProductionQualityInspection"], "ProductionInspectionID", errors)
    q = d["ProductionQualityResult"].merge(d["ProductionQualityInspection"][["ProductionInspectionID", "SampleQuantity"]], on="ProductionInspectionID")
    _almost_equal(q, "ProductionQualityResult", "TestedQuantity", q["SampleQuantity"], errors, "TestedQuantity must equal inspection SampleQuantity.")
    _almost_equal(q, "ProductionQualityResult", "TestedQuantity", q["PassedQuantity"] + q["FailedQuantity"], errors, "PassedQuantity + FailedQuantity must equal TestedQuantity.")
    bad_pass = q[
        (q["FailedQuantity"] == 0)
        & (
            (q["ResultStatus"] != "Passed")
            | (q["DefectSeverity"] != "None")
            | (q["DefectCode"].fillna("").astype(str).str.strip() != "NoDefect")
        )
    ]
    _bad_rows(bad_pass, errors, "PROD_QUALITY_STATUS_FAILED_ZERO", "ProductionQualityResult", "ResultStatus", "Zero failed quantity must have Passed / NoDefect / None status.")
    failed_rows = q[q["FailedQuantity"] > 0]
    bad_failed = failed_rows[
        (failed_rows["DefectCode"].fillna("").astype(str).str.strip().isin({"", "NoDefect", "None"}))
        | (failed_rows["DefectSeverity"] == "None")
        | (~failed_rows["ResultStatus"].isin({"PartiallyFailed", "Failed"}))
    ]
    _bad_rows(bad_failed, errors, "PROD_QUALITY_FAILED_DEFECT_REQUIRED", "ProductionQualityResult", "DefectCode", "Failed quality rows must have a real defect code, non-None severity, and failed status.")
    _allowed(d, "ProductionQualityResult", "ResultStatus", {"Passed", "PartiallyFailed", "Failed"}, errors)
    _allowed(d, "ProductionQualityResult", "DefectSeverity", {"None", "Low", "Medium", "High", "Critical"}, errors)
    _allowed(d, "ProductionQualityResult", "DefectCode", {"NoDefect", *get_default_industry_profile().production.quality_defect_codes}, errors)


def _scrap_rework(d, errors) -> None:
    _unique(d, "ScrapReworkEvent", "ScrapReworkID", errors)
    if d["ScrapReworkEvent"].empty:
        return
    _fk(d["ScrapReworkEvent"], "ScrapReworkEvent", "ProductionBatchID", d["ProductionBatch"], "ProductionBatchID", errors)
    _fk(d["ScrapReworkEvent"], "ScrapReworkEvent", "OperationExecutionID", d["OperationExecution"], "OperationExecutionID", errors)
    event = d["ScrapReworkEvent"].merge(d["ProductionBatch"][["ProductionBatchID", "ProductID"]], on="ProductionBatchID", suffixes=("", "_Batch")).merge(d["OperationExecution"][["OperationExecutionID", "ScrapQuantity", "ReworkQuantity"]], on="OperationExecutionID")
    _bad_rows(event[event["ProductID"] != event["ProductID_Batch"]], errors, "PROD_SCRAP_PRODUCT_LINEAGE", "ScrapReworkEvent", "ProductID", "Scrap/rework ProductID must match batch ProductID.")
    scrap_bad = event[(event["EventType"] == "Scrap") & (abs(event["Quantity"] - event["ScrapQuantity"]) > 0.0001)]
    rework_bad = event[(event["EventType"] == "Rework") & (abs(event["Quantity"] - event["ReworkQuantity"]) > 0.0001)]
    _bad_rows(pd.concat([scrap_bad, rework_bad]), errors, "PROD_SCRAP_REWORK_QUANTITY", "ScrapReworkEvent", "Quantity", "Scrap/Rework quantity must match operation quantity.")
    _allowed(d, "ScrapReworkEvent", "EventType", {"Scrap", "Rework"}, errors)
    _positive(d["ScrapReworkEvent"], "ScrapReworkEvent", "Quantity", errors)
    _positive_or_zero(d["ScrapReworkEvent"], "ScrapReworkEvent", "CostImpact", errors)


def _finished_goods(d, u, errors) -> None:
    _unique(d, "FinishedGoodsReceipt", "FinishedGoodsReceiptID", errors)
    _fk(d["FinishedGoodsReceipt"], "FinishedGoodsReceipt", "ProductionBatchID", d["ProductionBatch"], "ProductionBatchID", errors)
    _fk(d["FinishedGoodsReceipt"], "FinishedGoodsReceipt", "ProductionOrderLineID", d["ProductionOrderLine"], "ProductionOrderLineID", errors)
    _fk(d["FinishedGoodsReceipt"], "FinishedGoodsReceipt", "WarehouseID", u["Warehouse"], "WarehouseID", errors)
    receipt = d["FinishedGoodsReceipt"].merge(d["ProductionBatch"][["ProductionBatchID", "ProductID", "PlantID", "ActualEndDate"]], on="ProductionBatchID", suffixes=("", "_Batch")).merge(d["ProductionOrderLine"][["ProductionOrderLineID", "ProductID", "GoodQuantity"]], on="ProductionOrderLineID", suffixes=("", "_Line"))
    bad = receipt[(receipt["ProductID"] != receipt["ProductID_Batch"]) | (receipt["ProductID"] != receipt["ProductID_Line"]) | (receipt["PlantID"] != receipt["PlantID_Batch"])]
    _bad_rows(bad, errors, "PROD_FG_RECEIPT_LINEAGE", "FinishedGoodsReceipt", "ProductionBatchID", "Finished goods receipt lineage must match batch/order line.")
    _bad_rows(receipt[pd.to_datetime(receipt["ReceiptDate"]) < pd.to_datetime(receipt["ActualEndDate"])], errors, "PROD_FG_RECEIPT_DATE", "FinishedGoodsReceipt", "ReceiptDate", "ReceiptDate must be on or after batch ActualEndDate.")
    _almost_equal(receipt, "FinishedGoodsReceipt", "GoodQuantity", receipt["GoodQuantity_Line"], errors, "FinishedGoodsReceipt.GoodQuantity must align with ProductionOrderLine.GoodQuantity.")
    _positive(receipt, "FinishedGoodsReceipt", "GoodQuantity", errors)
    _almost_equal(receipt, "FinishedGoodsReceipt", "ReceiptValue", receipt["GoodQuantity"] * receipt["UnitCost"], errors, "ReceiptValue must equal GoodQuantity * UnitCost.", tolerance=0.011)
    _allowed(d, "FinishedGoodsReceipt", "ReceiptStatus", {"Received", "Cancelled"}, errors)
    _fg_inventory_rollup(d, u, errors)


def _fg_inventory_rollup(d, u, errors) -> None:
    _unique(d, "FinishedGoodsInventory", "FinishedGoodsInventoryID", errors)
    _fk(d["FinishedGoodsInventory"], "FinishedGoodsInventory", "ProductID", d["ProductMaster"], "ProductID", errors)
    _fk(d["FinishedGoodsInventory"], "FinishedGoodsInventory", "PlantID", u["Plant"], "PlantID", errors)
    _fk(d["FinishedGoodsInventory"], "FinishedGoodsInventory", "WarehouseID", u["Warehouse"], "WarehouseID", errors)
    rolled = d["FinishedGoodsReceipt"].groupby(["ProductID", "PlantID", "WarehouseID"]).agg(OnHandQuantity=("GoodQuantity", "sum"), OnHandValue=("ReceiptValue", "sum"), LastReceiptDate=("ReceiptDate", "max")).reset_index()
    inv = d["FinishedGoodsInventory"].merge(rolled, on=["ProductID", "PlantID", "WarehouseID"], suffixes=("", "_Expected"))
    _almost_equal(inv, "FinishedGoodsInventory", "OnHandQuantity", inv["OnHandQuantity_Expected"], errors, "OnHandQuantity must roll up from FinishedGoodsReceipt.GoodQuantity.")
    _almost_equal(inv, "FinishedGoodsInventory", "OnHandValue", inv["OnHandValue_Expected"], errors, "OnHandValue must roll up from FinishedGoodsReceipt.ReceiptValue.", tolerance=0.011)
    _bad_rows(inv[inv["ReservedQuantity"] > inv["OnHandQuantity"] + 0.0001], errors, "PROD_FG_RESERVED_EXCEEDS_ONHAND", "FinishedGoodsInventory", "ReservedQuantity", "ReservedQuantity must not exceed OnHandQuantity.")
    _almost_equal(inv, "FinishedGoodsInventory", "AvailableQuantity", inv["OnHandQuantity"] - inv["ReservedQuantity"], errors, "AvailableQuantity must equal OnHandQuantity - ReservedQuantity.")
    _allowed(d, "FinishedGoodsInventory", "InventoryStatus", {"Available", "LowStock", "Hold", "OutOfStock"}, errors)


def _genealogy(d, u, errors) -> None:
    _unique(d, "ProductionGenealogy", "ProductionGenealogyID", errors)
    _fk(d["ProductionGenealogy"], "ProductionGenealogy", "FinishedGoodsReceiptID", d["FinishedGoodsReceipt"], "FinishedGoodsReceiptID", errors)
    _fk(d["ProductionGenealogy"], "ProductionGenealogy", "ProductionBatchID", d["ProductionBatch"], "ProductionBatchID", errors)
    _fk(d["ProductionGenealogy"], "ProductionGenealogy", "MaterialIssueLineID", d["MaterialIssueLine"], "MaterialIssueLineID", errors)
    _fk(d["ProductionGenealogy"], "ProductionGenealogy", "InventoryReceiptDetailID", u["InventoryReceiptDetail"], "InventoryReceiptDetailID", errors)
    _fk(d["ProductionGenealogy"], "ProductionGenealogy", "SourceInventoryTransactionID", u["InventoryTransaction"], "InventoryTransactionID", errors)
    gene = d["ProductionGenealogy"].merge(d["MaterialIssueLine"][["MaterialIssueLineID", "ComponentID", "InventoryReceiptDetailID", "SourceInventoryTransactionID", "IssuedQuantity"]], on="MaterialIssueLineID", suffixes=("", "_Issue"))
    bad = gene[(gene["ComponentID"] != gene["ComponentID_Issue"]) | (gene["InventoryReceiptDetailID"] != gene["InventoryReceiptDetailID_Issue"]) | (gene["SourceInventoryTransactionID"] != gene["SourceInventoryTransactionID_Issue"])]
    _bad_rows(bad, errors, "PROD_GENEALOGY_ISSUE_LINEAGE", "ProductionGenealogy", "MaterialIssueLineID", "Genealogy must match MaterialIssueLine lineage.")
    _almost_equal(gene, "ProductionGenealogy", "ConsumedQuantity", gene["IssuedQuantity"], errors, "ConsumedQuantity must equal MaterialIssueLine.IssuedQuantity.")
    receipt_supplier = u["InventoryReceiptDetail"][["InventoryReceiptDetailID", "SupplierID"]]
    gene_supplier = d["ProductionGenealogy"].merge(receipt_supplier, on="InventoryReceiptDetailID", suffixes=("", "_Receipt"))
    _bad_rows(gene_supplier[gene_supplier["SupplierID"] != gene_supplier["SupplierID_Receipt"]], errors, "PROD_GENEALOGY_SUPPLIER_LINEAGE", "ProductionGenealogy", "SupplierID", "SupplierID must match InventoryReceiptDetail.SupplierID.")
    _allowed(d, "ProductionGenealogy", "TraceabilityStatus", {"Traced", "MissingSource"}, errors)


def _cost_summary(d, errors) -> None:
    _unique(d, "ProductionCostSummary", "ProductionCostSummaryID", errors)
    _fk(d["ProductionCostSummary"], "ProductionCostSummary", "ProductionOrderLineID", d["ProductionOrderLine"], "ProductionOrderLineID", errors)
    _fk(d["ProductionCostSummary"], "ProductionCostSummary", "ProductionBatchID", d["ProductionBatch"], "ProductionBatchID", errors)
    cost = d["ProductionCostSummary"].merge(d["ProductionBatch"][["ProductionBatchID", "ProductID"]], on="ProductionBatchID", suffixes=("", "_Batch"))
    _bad_rows(cost[cost["ProductID"] != cost["ProductID_Batch"]], errors, "PROD_COST_PRODUCT_LINEAGE", "ProductionCostSummary", "ProductID", "Cost ProductID must match batch ProductID.")
    req_to_line = d["ProductionMaterialRequirement"][["MaterialRequirementID", "ProductionOrderLineID"]]
    issue = d["MaterialIssueLine"].merge(req_to_line, on="MaterialRequirementID")
    material_cost = issue.groupby("ProductionOrderLineID")["IssueValue"].sum().rename("ExpectedMaterialCost").reset_index()
    cost = d["ProductionCostSummary"].merge(material_cost, on="ProductionOrderLineID")
    _almost_equal(cost, "ProductionCostSummary", "MaterialCost", cost["ExpectedMaterialCost"], errors, "MaterialCost must equal SUM(MaterialIssueLine.IssueValue).", tolerance=0.011)
    scrap_cost = d["ScrapReworkEvent"].groupby("ProductionBatchID")["CostImpact"].sum().rename("ExpectedScrapCost").reset_index() if not d["ScrapReworkEvent"].empty else pd.DataFrame(columns=["ProductionBatchID", "ExpectedScrapCost"])
    cost = d["ProductionCostSummary"].merge(scrap_cost, on="ProductionBatchID", how="left").fillna({"ExpectedScrapCost": 0})
    _almost_equal(cost, "ProductionCostSummary", "ScrapCost", cost["ExpectedScrapCost"], errors, "ScrapCost must equal SUM(ScrapReworkEvent.CostImpact).", tolerance=0.011)
    _almost_equal(cost, "ProductionCostSummary", "TotalProductionCost", cost["MaterialCost"] + cost["LaborCost"] + cost["OverheadCost"] + cost["ScrapCost"], errors, "TotalProductionCost must equal material + labor + overhead + scrap.", tolerance=0.011)
    receipt = d["FinishedGoodsReceipt"][["ProductionBatchID", "GoodQuantity", "UnitCost"]]
    cost = d["ProductionCostSummary"].merge(receipt, on="ProductionBatchID")
    _almost_equal(cost, "ProductionCostSummary", "UnitProductionCost", cost["TotalProductionCost"] / cost["GoodQuantity"], errors, "UnitProductionCost must equal TotalProductionCost / GoodQuantity.", tolerance=0.011)
    _almost_equal(cost, "FinishedGoodsReceipt", "UnitCost", cost["UnitProductionCost"], errors, "FinishedGoodsReceipt.UnitCost must align with ProductionCostSummary.UnitProductionCost.", tolerance=0.011)


def _check_dates(d, errors, scorecard) -> None:
    before = len(errors)
    date_columns = {
        "BOMHeader": ["EffectiveFromDate", "EffectiveToDate"],
        "ProductionShift": ["ShiftDate"],
        "ProductionOrderHdr": ["OrderDate", "PlannedStartDate", "PlannedEndDate", "ActualStartDate", "ActualEndDate"],
        "MaterialIssueHeader": ["IssueDate"],
        "ProductionBatch": ["ActualStartDate", "ActualEndDate"],
        "OperationExecution": ["ActualStartDateTime", "ActualEndDateTime"],
        "ProductionQualityInspection": ["InspectionDate"],
        "ScrapReworkEvent": ["EventDate"],
        "FinishedGoodsReceipt": ["ReceiptDate"],
        "FinishedGoodsInventory": ["LastReceiptDate"],
    }
    for table_name, columns in date_columns.items():
        dataframe = d[table_name]
        if dataframe.empty:
            continue
        for column in columns:
            values = pd.to_datetime(dataframe[column], errors="coerce")
            bad = dataframe[values.isna() | (values.dt.date < pd.Timestamp("2025-01-01").date()) | (values.dt.date > pd.Timestamp("2025-12-31").date())]
            _bad_rows(bad, errors, "PROD_DATE_OUTSIDE_2025", table_name, column, "Production dates must be within 2025.")
    scorecard["date_scope_issues"] = len(errors) - before


def _check_uom_precision(d, u, errors, scorecard) -> None:
    before = len(errors)
    component_uom = dict(zip(u["ComponentMaster"]["ComponentID"], u["ComponentMaster"]["UOM"]))
    product_uom = dict(zip(d["ProductMaster"]["ProductID"], d["ProductMaster"]["UOM"]))
    _check_precision(d["BOMLine"], "BOMLine", "ComponentID", component_uom, ["ComponentQuantity"], errors)
    _check_precision(d["MaterialIssueLine"], "MaterialIssueLine", "ComponentID", component_uom, ["IssuedQuantity"], errors)
    _check_precision(d["ProductionGenealogy"], "ProductionGenealogy", "ComponentID", component_uom, ["ConsumedQuantity"], errors)
    _check_precision(d["ProductionOrderLine"], "ProductionOrderLine", "ProductID", product_uom, ["PlannedQuantity", "ReleasedQuantity", "CompletedQuantity", "GoodQuantity", "ScrapQuantity"], errors)
    _check_precision(d["ProductionBatch"], "ProductionBatch", "ProductID", product_uom, ["PlannedBatchQuantity"], errors)
    op = d["OperationExecution"].merge(d["ProductionBatch"][["ProductionBatchID", "ProductID"]], on="ProductionBatchID")
    _check_precision(op, "OperationExecution", "ProductID", product_uom, ["InputQuantity", "OutputQuantity", "ScrapQuantity", "ReworkQuantity"], errors)
    fgr = d["FinishedGoodsReceipt"]
    _check_precision(fgr, "FinishedGoodsReceipt", "ProductID", product_uom, ["GoodQuantity", "ScrapQuantity"], errors)
    fgi = d["FinishedGoodsInventory"]
    _check_precision(fgi, "FinishedGoodsInventory", "ProductID", product_uom, ["OnHandQuantity", "AvailableQuantity"], errors)
    scorecard["uom_precision_issues"] = len(errors) - before


def _check_precision(dataframe, table_name, key_column, uom_lookup, quantity_columns, errors) -> None:
    for row in dataframe.itertuples(index=False):
        uom = uom_lookup.get(getattr(row, key_column))
        if not requires_integer_quantity(uom):
            continue
        for column in quantity_columns:
            if not is_whole_quantity(getattr(row, column)):
                _error(errors, "PROD_COUNTABLE_UOM_DECIMAL_QUANTITY", table_name, column, f"Countable UOM {uom} has decimal quantity in {table_name}.{column}.", "Apply shared UOM precision and regenerate.")
                return


def _result(errors, warnings, table_row_counts, scorecard, production_data) -> ProductionQualityResult:
    status = "failed" if errors else ("passed_with_warnings" if warnings else "passed")
    metrics = {
        "production_tables": len([table for table in PRODUCTION_TABLES if table in production_data]),
        "total_rows": sum(table_row_counts.values()),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return ProductionQualityResult(status, errors, warnings, table_row_counts, scorecard, metrics)


def _unique(d, table, column, errors) -> None:
    bad = d[table][d[table][column].duplicated(keep=False)]
    _bad_rows(bad, errors, "PROD_UNIQUE_CHECK", table, column, f"{table}.{column} must be unique.")


def _fk(child, table, column, parent, parent_column, errors) -> None:
    invalid = child[~child[column].isin(parent[parent_column])]
    _bad_rows(invalid, errors, "PROD_FK_CHECK", table, column, f"{table}.{column} contains values missing from parent {parent_column}.")


def _allowed(d, table, column, allowed, errors) -> None:
    invalid = d[table][~d[table][column].isin(allowed)]
    _bad_rows(invalid, errors, "PROD_ALLOWED_VALUE_CHECK", table, column, f"{table}.{column} contains invalid values.")


def _positive(df, table, column, errors) -> None:
    _bad_rows(df[df[column] <= 0], errors, "PROD_POSITIVE_CHECK", table, column, f"{table}.{column} must be positive.")


def _positive_or_zero(df, table, column, errors) -> None:
    _bad_rows(df[df[column] < 0], errors, "PROD_NON_NEGATIVE_CHECK", table, column, f"{table}.{column} must be non-negative.")


def _range(df, table, column, low, high, errors) -> None:
    _bad_rows(df[(df[column] < low) | (df[column] > high)], errors, "PROD_RANGE_CHECK", table, column, f"{table}.{column} must be between {low} and {high}.")


def _date_order(df, table, earlier, later, errors) -> None:
    invalid = df[pd.to_datetime(df[earlier]) > pd.to_datetime(df[later])]
    _bad_rows(invalid, errors, "PROD_DATE_ORDER_CHECK", table, later, f"{table}.{earlier} must be <= {later}.")


def _almost_equal(df, table, column, expected, errors, message, tolerance=0.0001) -> None:
    actual = pd.to_numeric(df[column], errors="coerce")
    expected_series = pd.Series(expected, index=df.index)
    invalid = df[(actual - expected_series).abs() > tolerance]
    _bad_rows(invalid, errors, "PROD_FORMULA_CHECK", table, column, message)


def _component_uom_match(df, components, table, quantity_column, errors) -> None:
    comp = components[["ComponentID", "UOM"]]
    merged = df.merge(comp, on="ComponentID", suffixes=("", "_Component"))
    if "UOM" in df.columns:
        _bad_rows(merged[merged["UOM"] != merged["UOM_Component"]], errors, "PROD_COMPONENT_UOM_MISMATCH", table, "UOM", f"{table}.UOM must match ComponentMaster.UOM.")
    for row in merged.itertuples(index=False):
        if requires_integer_quantity(row.UOM_Component) and not is_whole_quantity(getattr(row, quantity_column)):
            _error(errors, "PROD_COUNTABLE_UOM_DECIMAL_QUANTITY", table, quantity_column, f"Countable UOM {row.UOM_Component} has decimal quantity.", "Apply shared UOM precision and regenerate.")
            break


def _routing_operation_alignment(d, errors) -> None:
    routing = d["RoutingOperation"].merge(d["RoutingHeader"][["RoutingID", "PlantID"]], on="RoutingID").merge(d["WorkCenter"][["WorkCenterID", "PlantID"]], on="WorkCenterID", suffixes=("_Routing", "_WC"))
    _bad_rows(routing[routing["PlantID_Routing"] != routing["PlantID_WC"]], errors, "PROD_ROUTING_WORKCENTER_PLANT", "RoutingOperation", "WorkCenterID", "RoutingOperation WorkCenter plant should match RoutingHeader plant.")
    for routing_id, rows in d["RoutingOperation"].groupby("RoutingID"):
        sequences = list(rows["OperationSequence"])
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            _error(errors, "PROD_ROUTING_SEQUENCE", "RoutingOperation", "OperationSequence", f"OperationSequence must be ordered and unique for RoutingID {routing_id}.", "Generate monotonic unique operation sequences per routing.")


def _shift_alignment(d, errors) -> None:
    shift = d["ProductionShift"].merge(d["WorkCenter"][["WorkCenterID", "PlantID"]], on="WorkCenterID", suffixes=("", "_WC"))
    _bad_rows(shift[shift["PlantID"] != shift["PlantID_WC"]], errors, "PROD_SHIFT_WORKCENTER_PLANT", "ProductionShift", "PlantID", "ProductionShift.PlantID must equal WorkCenter.PlantID.")


def _bad_rows(df, errors, check_type, table, column, message) -> None:
    if df.empty:
        return
    _error(errors, check_type, table, column, message, "Regenerate or recalculate the affected Production data.", _sample(df))


def _sample(df) -> list[dict[str, Any]]:
    return df.head(5).where(pd.notna(df.head(5)), None).to_dict("records")


def _error(errors, check_type, table, column, message, suggested_fix, sample_rows=None) -> None:
    errors.append(ProductionQualityIssue("error", check_type, table, column, message, suggested_fix, sample_rows or []))


def _warning(warnings, check_type, table, column, message, suggested_fix) -> None:
    warnings.append(ProductionQualityIssue("warning", check_type, table, column, message, suggested_fix, []))

