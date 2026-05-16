from __future__ import annotations

from copy import deepcopy

import pandas as pd

from procurement_data_generator.modules.production.reconciler_rules import (
    PRODUCTION_TABLES,
    reconcile_production_data,
)
from tests.test_production_transaction_generator import _generate


def test_production_reconciler_imports_and_valid_generated_data_passes(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)

    result = reconcile_production_data(production_data, upstream)

    assert result.status == "passed"
    assert result.errors == []


def test_missing_required_production_table_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    del production_data["ProductionGenealogy"]

    result = reconcile_production_data(production_data, upstream)

    assert not result.is_valid
    assert _has_error(result, "PROD_MISSING_TABLE")


def test_broken_product_bom_fk_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["BOMHeader"].loc[0, "ProductID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_FK_CHECK")


def test_broken_bom_component_fk_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["BOMLine"].loc[0, "ComponentID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_FK_CHECK")


def test_material_issue_exceeding_inventory_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["MaterialIssueLine"].loc[0, "IssuedQuantity"] = 9999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_MATERIAL_ISSUE_EXCEEDS_INVENTORY")


def test_broken_inventory_transaction_lineage_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["MaterialIssueLine"].loc[0, "SourceInventoryTransactionID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_FK_CHECK")


def test_broken_inventory_receipt_detail_lineage_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["MaterialIssueLine"].loc[0, "InventoryReceiptDetailID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_FK_CHECK")


def test_broken_genealogy_supplier_lineage_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["ProductionGenealogy"].loc[0, "SupplierID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_GENEALOGY_SUPPLIER_LINEAGE")


def test_formula_failures_are_errors(tmp_path) -> None:
    mutations = [
        ("ProductionMaterialRequirement", "RequiredQuantity", "PROD_FORMULA_CHECK"),
        ("ProductionMaterialRequirement", "ScrapAdjustedQuantity", "PROD_FORMULA_CHECK"),
        ("MaterialIssueLine", "IssueValue", "PROD_FORMULA_CHECK"),
        ("OperationExecution", "OutputQuantity", "PROD_OPERATION_OUTPUT_FORMULA"),
        ("ProductionQualityResult", "PassedQuantity", "PROD_FORMULA_CHECK"),
        ("FinishedGoodsInventory", "OnHandQuantity", "PROD_FORMULA_CHECK"),
        ("ProductionCostSummary", "TotalProductionCost", "PROD_FORMULA_CHECK"),
    ]
    for table_name, column_name, expected_check in mutations:
        production_data, upstream = _valid_data(tmp_path)
        production_data[table_name].loc[0, column_name] = float(production_data[table_name].loc[0, column_name]) + 10

        result = reconcile_production_data(production_data, upstream)

        assert _has_error(result, expected_check), f"{table_name}.{column_name}"


def test_passed_quality_rows_require_no_defect_code(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    quality = production_data["ProductionQualityResult"]
    row_index = quality[quality["FailedQuantity"] == 0].index[0]
    production_data["ProductionQualityResult"].loc[row_index, "DefectCode"] = "None"

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_QUALITY_STATUS_FAILED_ZERO")


def test_failed_quality_rows_require_real_defect_code(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    quality = production_data["ProductionQualityResult"]
    row_index = quality[quality["TestedQuantity"] > 1].index[0]
    production_data["ProductionQualityResult"].loc[row_index, "FailedQuantity"] = 1
    production_data["ProductionQualityResult"].loc[row_index, "PassedQuantity"] = float(quality.loc[row_index, "TestedQuantity"]) - 1
    production_data["ProductionQualityResult"].loc[row_index, "DefectCode"] = "NoDefect"
    production_data["ProductionQualityResult"].loc[row_index, "DefectSeverity"] = "Low"
    production_data["ProductionQualityResult"].loc[row_index, "ResultStatus"] = "PartiallyFailed"

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_QUALITY_FAILED_DEFECT_REQUIRED")


def test_date_outside_2025_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["ProductionOrderHdr"].loc[0, "OrderDate"] = "2026-01-01"

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_DATE_OUTSIDE_2025")


def test_countable_uom_decimal_quantity_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    countable_component = upstream["ComponentMaster"][upstream["ComponentMaster"]["UOM"].isin(["EA", "Set", "Unit"])].iloc[0]
    row_index = production_data["BOMLine"][production_data["BOMLine"]["ComponentID"] == countable_component.ComponentID].index[0]
    production_data["BOMLine"].loc[row_index, "ComponentQuantity"] = 1.5

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_COUNTABLE_UOM_DECIMAL_QUANTITY")


def test_lower_row_counts_warn_without_errors_when_otherwise_valid(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    targets = {table: len(df) + 100 for table, df in production_data.items()}

    result = reconcile_production_data(production_data, upstream, target_row_counts=targets)

    assert result.is_valid
    assert result.warnings
    assert any(warning.check_type == "PROD_ROW_COUNT_BELOW_TARGET" for warning in result.warnings)


def test_operating_scope_shift_b_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["ProductionShift"].loc[0, "ShiftCode"] = "B"

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_OPERATING_SCOPE_SHIFT_CODE")
    assert _has_error(result, "PROD_OPERATING_SCOPE_OPERATION_SHIFT_CODE")


def test_operating_scope_shift_c_fails(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["ProductionShift"].loc[0, "ShiftCode"] = "C"

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_OPERATING_SCOPE_SHIFT_CODE")


def test_operating_scope_rejects_wrong_production_plant_reference(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["ProductionOrderHdr"].loc[0, "PlantID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_OPERATING_SCOPE_PLANT_REFERENCE")


def test_operating_scope_rejects_wrong_production_warehouse_reference(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    production_data["MaterialIssueHeader"].loc[0, "WarehouseID"] = 999999

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_OPERATING_SCOPE_WAREHOUSE_REFERENCE")


def test_operating_scope_allows_multiple_workcenters(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)

    result = reconcile_production_data(production_data, upstream)

    assert production_data["WorkCenter"]["WorkCenterID"].nunique() > 1
    assert not _has_error(result, "PROD_OPERATING_SCOPE_WORKCENTER_COUNT")


def test_operation_execution_must_reference_valid_shift_a_workcenter(tmp_path) -> None:
    production_data, upstream = _valid_data(tmp_path)
    operation = production_data["OperationExecution"].iloc[0]
    shift_row = production_data["ProductionShift"][production_data["ProductionShift"]["ShiftID"] == operation.ShiftID].iloc[0]
    replacement = production_data["ProductionShift"][production_data["ProductionShift"]["WorkCenterID"] != shift_row.WorkCenterID].iloc[0]
    production_data["OperationExecution"].loc[0, "ShiftID"] = replacement.ShiftID

    result = reconcile_production_data(production_data, upstream)

    assert _has_error(result, "PROD_OPERATING_SCOPE_OPERATION_SHIFT_WORKCENTER")


def _valid_data(tmp_path):
    tx_data, report, master, upstream = _generate(tmp_path, seed=42)
    assert report.is_valid
    production_data = {**master, **tx_data}
    assert set(PRODUCTION_TABLES).issubset(production_data)
    return deepcopy(production_data), deepcopy(upstream)


def _has_error(result, check_type: str) -> bool:
    return any(issue.check_type == check_type for issue in result.errors)
