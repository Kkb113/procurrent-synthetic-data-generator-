from __future__ import annotations

import math

import pandas as pd
import pandas.testing as pdt

from procurement_data_generator.core.contracts.llm_plan_contract import DomainProfile, FormulaRule, LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.formulas.formula_engine import SafeFormulaEngine


def test_row_level_multiply_works() -> None:
    dataframes = {"PurchaseOrderLine": _po_lines()}
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("PO_LINE_AMOUNT")]), _schema())

    assert report.status == "passed"
    assert list(updated["PurchaseOrderLine"]["LineAmount"]) == [20.0, 60.0, 0.0]


def test_row_level_subtract_works() -> None:
    dataframes = {"InspectionResult": _inspection_lines()}
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("INSPECTION_REJECTED_QTY")]), _schema())

    assert report.status == "passed"
    assert list(updated["InspectionResult"]["RejectedQuantity"]) == [2, 0, 0]


def test_aggregate_sum_works() -> None:
    dataframes = {"PurchaseOrderHdr": _po_headers(), "PurchaseOrderLine": _po_lines(line_amount=[20.0, 60.0, 10.0])}
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("PO_HEADER_TOTAL")]), _schema())

    assert report.status == "passed"
    assert list(updated["PurchaseOrderHdr"]["TotalAmount"]) == [80.0, 10.0]


def test_aggregate_sum_with_group_by_columns_and_no_relationship_key_works() -> None:
    dataframes = {
        "InventoryTransaction": pd.DataFrame(
            {
                "InventoryTransactionID": [1, 2, 3],
                "ComponentID": [10, 10, 11],
                "PlantID": [1, 1, 1],
                "WarehouseID": [5, 5, 6],
                "TransactionQuantity": [7, 8, 3],
            }
        ),
        "Inventory": pd.DataFrame(
            {
                "InventoryID": [1, 2],
                "ComponentID": [10, 11],
                "PlantID": [1, 1],
                "WarehouseID": [5, 6],
                "OnHandQuantity": [0, 0],
            }
        ),
    }
    rule = FormulaRule(
        rule_id="AGG_INVENTORY_ON_HAND",
        rule_type="aggregate",
        target_table="Inventory",
        target_column="OnHandQuantity",
        operation="sum",
        input_columns=[],
        source_table="InventoryTransaction",
        source_column="TransactionQuantity",
        relationship_key=None,
        group_by_columns=["ComponentID", "PlantID", "WarehouseID"],
        formula="SUM(InventoryTransaction.TransactionQuantity) GROUP BY ComponentID, PlantID, WarehouseID",
    )

    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.status == "passed"
    assert list(updated["Inventory"]["OnHandQuantity"]) == [15, 3]


def test_aggregate_with_neither_relationship_key_nor_group_by_columns_fails() -> None:
    rule = _rule("PO_HEADER_TOTAL").model_copy(update={"relationship_key": None, "group_by_columns": []})
    dataframes = {"PurchaseOrderHdr": _po_headers(), "PurchaseOrderLine": _po_lines(line_amount=[20.0, 60.0, 10.0])}

    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.failed_count == 1
    assert "relationship_key or group_by_columns" in report.failed_rules[0].message


def test_aggregate_count_works() -> None:
    dataframes = {"PurchaseOrderHdr": _po_headers(), "PurchaseOrderLine": _po_lines(line_amount=[20.0, 60.0, 10.0])}
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("PO_LINE_COUNT")]), _schema())

    assert report.status == "passed"
    assert list(updated["PurchaseOrderHdr"]["LineCount"]) == [2, 1]


def test_date_difference_works() -> None:
    dataframes = {
        "GoodsReceiptHeader": pd.DataFrame(
            {
                "GoodsReceiptID": [1, 2],
                "ReceiptDate": ["2025-01-10", "2025-01-12"],
                "ExpectedDeliveryDate": ["2025-01-07", "2025-01-12"],
                "DelayDays": [0, 0],
            }
        )
    }
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("RECEIPT_DELAY_DAYS")]), _schema())

    assert report.status == "passed"
    assert list(updated["GoodsReceiptHeader"]["DelayDays"]) == [3, 0]


def test_percentage_rule_with_percentage_operation_works() -> None:
    dataframes = {"InspectionResult": _inspection_lines()}
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("REJECTION_RATE")]), _schema())

    assert report.status == "passed"
    assert list(updated["InspectionResult"]["RejectionRatePct"].dropna())[:2] == [20.0, 0.0]


def test_percentage_rule_with_divide_operation_works() -> None:
    dataframes = {"InspectionResult": _inspection_lines()}
    rule = _rule("REJECTION_RATE").model_copy(update={"operation": "divide"})
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.status == "passed"
    assert list(updated["InspectionResult"]["RejectionRatePct"].dropna())[:2] == [20.0, 0.0]


def test_percentage_denominator_zero_returns_null_not_infinity() -> None:
    dataframes = {"InspectionResult": _inspection_lines()}
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("REJECTION_RATE")]), _schema())
    value = updated["InspectionResult"].loc[2, "RejectionRatePct"]

    assert report.status == "passed"
    assert pd.isna(value)
    assert not _has_infinity(updated["InspectionResult"]["RejectionRatePct"])


def test_percentage_divide_denominator_zero_returns_null_not_infinity() -> None:
    dataframes = {"InspectionResult": _inspection_lines()}
    rule = _rule("REJECTION_RATE").model_copy(update={"operation": "divide"})
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())
    value = updated["InspectionResult"].loc[2, "RejectionRatePct"]

    assert report.status == "passed"
    assert pd.isna(value)
    assert not _has_infinity(updated["InspectionResult"]["RejectionRatePct"])


def test_divide_denominator_zero_returns_null_not_infinity() -> None:
    dataframes = {
        "InspectionResult": pd.DataFrame(
            {"InspectionResultID": [1], "RejectedQuantity": [3], "InspectedQuantity": [0], "RejectionRatePct": [0.0]}
        )
    }
    rule = FormulaRule(
        rule_id="SAFE_DIVIDE",
        rule_type="row_level",
        target_table="InspectionResult",
        target_column="RejectionRatePct",
        operation="divide",
        input_columns=["RejectedQuantity", "InspectedQuantity"],
        formula="RejectedQuantity / InspectedQuantity",
    )
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.status == "passed"
    assert pd.isna(updated["InspectionResult"].loc[0, "RejectionRatePct"])
    assert not _has_infinity(updated["InspectionResult"]["RejectionRatePct"])


def test_inventory_aggregation_works() -> None:
    dataframes = {
        "InventoryTransaction": pd.DataFrame(
            {
                "InventoryTransactionID": [1, 2, 3],
                "ComponentID": [10, 10, 11],
                "PlantID": [1, 1, 1],
                "WarehouseID": [5, 5, 6],
                "TransactionQuantity": [7, 8, 3],
            }
        ),
        "Inventory": pd.DataFrame(
            {
                "InventoryID": [1, 2],
                "ComponentID": [10, 11],
                "PlantID": [1, 1],
                "WarehouseID": [5, 6],
                "OnHandQuantity": [0, 0],
            }
        ),
    }
    updated, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("INVENTORY_ON_HAND")]), _schema())

    assert report.status == "passed"
    assert list(updated["Inventory"]["OnHandQuantity"]) == [15, 3]


def test_inventory_missing_group_by_columns_fails_clearly() -> None:
    rule = _rule("INVENTORY_ON_HAND").model_copy(update={"group_by_columns": []})
    dataframes = {
        "InventoryTransaction": pd.DataFrame({"InventoryTransactionID": [1], "ComponentID": [10], "PlantID": [1], "WarehouseID": [5], "TransactionQuantity": [7]}),
        "Inventory": pd.DataFrame({"InventoryID": [1], "ComponentID": [10], "PlantID": [1], "WarehouseID": [5], "OnHandQuantity": [0]}),
    }

    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.failed_count == 1
    assert "group_by_columns" in report.failed_rules[0].message


def test_inventory_missing_group_by_column_fails_clearly() -> None:
    rule = _rule("INVENTORY_ON_HAND").model_copy(update={"group_by_columns": ["ComponentID", "PlantID", "MissingWarehouseID"]})
    dataframes = {
        "InventoryTransaction": pd.DataFrame({"InventoryTransactionID": [1], "ComponentID": [10], "PlantID": [1], "WarehouseID": [5], "TransactionQuantity": [7]}),
        "Inventory": pd.DataFrame({"InventoryID": [1], "ComponentID": [10], "PlantID": [1], "WarehouseID": [5], "OnHandQuantity": [0]}),
    }

    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.failed_count == 1
    assert "Missing required column" in report.failed_rules[0].message


def test_missing_target_table_fails_gracefully() -> None:
    updated, report = SafeFormulaEngine().execute_formulas({}, _plan([_rule("PO_LINE_AMOUNT")]), _schema())

    assert updated == {}
    assert report.failed_count == 1
    assert "Target table" in report.failed_rules[0].message


def test_missing_target_column_fails_gracefully() -> None:
    dataframes = {"PurchaseOrderLine": _po_lines().drop(columns=["LineAmount"])}
    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("PO_LINE_AMOUNT")]), _schema())

    assert report.failed_count == 1
    assert "Target column" in report.failed_rules[0].message


def test_missing_input_column_fails_gracefully() -> None:
    dataframes = {"PurchaseOrderLine": _po_lines().drop(columns=["UnitPrice"])}
    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([_rule("PO_LINE_AMOUNT")]), _schema())

    assert report.failed_count == 1
    assert "Missing required column" in report.failed_rules[0].message


def test_unsupported_operation_fails_gracefully() -> None:
    rule = FormulaRule.model_construct(
        rule_id="BAD_OP",
        rule_type="row_level",
        target_table="PurchaseOrderLine",
        target_column="LineAmount",
        operation="unsafe_eval",
        input_columns=["OrderedQuantity", "UnitPrice"],
        source_table=None,
        source_column=None,
        relationship_key=None,
        group_by_columns=[],
        formula="unsafe",
        denominator_column=None,
        denominator_guard=False,
        tolerance_type=None,
        tolerance_value=None,
        description=None,
    )
    _, report = SafeFormulaEngine().execute_formulas({"PurchaseOrderLine": _po_lines()}, _plan([rule]), _schema())

    assert report.failed_count == 1
    assert "Unsupported formula operation" in report.failed_rules[0].message


def test_validation_style_operation_is_skipped() -> None:
    rule = FormulaRule(
        rule_id="QTY_COMPARE",
        rule_type="quantity_reconciliation",
        target_table="ShipmentLine",
        target_column="ShippedQuantity",
        operation="less_than_or_equal",
        input_columns=["ShippedQuantity", "OrderedQuantity"],
        formula="ShippedQuantity <= OrderedQuantity",
    )
    dataframes = {"ShipmentLine": pd.DataFrame({"ShipmentLineID": [1], "ShippedQuantity": [1], "OrderedQuantity": [2]})}
    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.skipped_count == 1
    assert report.status == "passed_with_warnings"


def test_original_dataframes_are_not_mutated() -> None:
    original = {"PurchaseOrderLine": _po_lines()}
    before = original["PurchaseOrderLine"].copy(deep=True)

    SafeFormulaEngine().execute_formulas(original, _plan([_rule("PO_LINE_AMOUNT")]), _schema())

    pdt.assert_frame_equal(original["PurchaseOrderLine"], before)


def test_non_nullable_target_with_null_result_warns_when_schema_is_available() -> None:
    rule = FormulaRule(
        rule_id="NON_NULL_DIVIDE",
        rule_type="row_level",
        target_table="PurchaseOrderLine",
        target_column="LineAmount",
        operation="divide",
        input_columns=["OrderedQuantity", "UnitPrice"],
        formula="OrderedQuantity / UnitPrice",
    )
    dataframes = {"PurchaseOrderLine": pd.DataFrame({"PurchaseOrderLineID": [1], "OrderedQuantity": [1], "UnitPrice": [0], "LineAmount": [0]})}
    _, report = SafeFormulaEngine().execute_formulas(dataframes, _plan([rule]), _schema())

    assert report.applied_count == 1
    assert report.warning_count == 1
    assert "Non-nullable target column" in report.applied_rules[0].warnings[0]


def test_formula_execution_report_counts_are_correct() -> None:
    rules = [_rule("PO_LINE_AMOUNT"), _rule("MISSING_TABLE"), _rule("VALIDATION_ONLY")]
    _, report = SafeFormulaEngine().execute_formulas({"PurchaseOrderLine": _po_lines()}, _plan(rules), _schema())

    assert report.total_rules == 3
    assert report.applied_count == 1
    assert report.failed_count == 1
    assert report.skipped_count == 1
    assert report.status == "failed"


def _po_lines(line_amount=None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "PurchaseOrderLineID": [1, 2, 3],
            "PurchaseOrderID": [100, 100, 101],
            "OrderedQuantity": [2, 3, 5],
            "UnitPrice": [10.0, 20.0, 0.0],
            "LineAmount": line_amount or [0.0, 0.0, 0.0],
        }
    )


def _po_headers() -> pd.DataFrame:
    return pd.DataFrame({"PurchaseOrderID": [100, 101], "TotalAmount": [0.0, 0.0], "LineCount": [0, 0]})


def _inspection_lines() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "InspectionResultID": [1, 2, 3],
            "InspectedQuantity": [10, 5, 0],
            "AcceptedQuantity": [8, 5, 0],
            "RejectedQuantity": [2, 0, 0],
            "RejectionRatePct": [0.0, 0.0, 0.0],
        }
    )


def _rule(rule_id: str) -> FormulaRule:
    rules = {
        "PO_LINE_AMOUNT": FormulaRule(
            rule_id="PO_LINE_AMOUNT",
            rule_type="row_level",
            target_table="PurchaseOrderLine",
            target_column="LineAmount",
            operation="multiply",
            input_columns=["OrderedQuantity", "UnitPrice"],
            formula="OrderedQuantity * UnitPrice",
        ),
        "PO_HEADER_TOTAL": FormulaRule(
            rule_id="PO_HEADER_TOTAL",
            rule_type="aggregate",
            target_table="PurchaseOrderHdr",
            target_column="TotalAmount",
            operation="sum",
            input_columns=[],
            source_table="PurchaseOrderLine",
            source_column="LineAmount",
            relationship_key="PurchaseOrderID",
            formula="SUM(PurchaseOrderLine.LineAmount) GROUP BY PurchaseOrderID",
        ),
        "PO_LINE_COUNT": FormulaRule(
            rule_id="PO_LINE_COUNT",
            rule_type="aggregate",
            target_table="PurchaseOrderHdr",
            target_column="LineCount",
            operation="count",
            input_columns=[],
            source_table="PurchaseOrderLine",
            source_column="PurchaseOrderLineID",
            relationship_key="PurchaseOrderID",
            formula="COUNT(PurchaseOrderLine.PurchaseOrderLineID) GROUP BY PurchaseOrderID",
        ),
        "RECEIPT_DELAY_DAYS": FormulaRule(
            rule_id="RECEIPT_DELAY_DAYS",
            rule_type="date_diff",
            target_table="GoodsReceiptHeader",
            target_column="DelayDays",
            operation="date_diff",
            input_columns=["ReceiptDate", "ExpectedDeliveryDate"],
            formula="ReceiptDate - ExpectedDeliveryDate",
        ),
        "REJECTION_RATE": FormulaRule(
            rule_id="REJECTION_RATE",
            rule_type="percentage",
            target_table="InspectionResult",
            target_column="RejectionRatePct",
            operation="percentage",
            input_columns=["RejectedQuantity", "InspectedQuantity"],
            denominator_column="InspectedQuantity",
            denominator_guard=True,
            formula="RejectedQuantity / InspectedQuantity * 100",
        ),
        "INSPECTION_REJECTED_QTY": FormulaRule(
            rule_id="INSPECTION_REJECTED_QTY",
            rule_type="quantity_reconciliation",
            target_table="InspectionResult",
            target_column="RejectedQuantity",
            operation="subtract",
            input_columns=["InspectedQuantity", "AcceptedQuantity"],
            formula="InspectedQuantity - AcceptedQuantity",
        ),
        "INVENTORY_ON_HAND": FormulaRule(
            rule_id="INVENTORY_ON_HAND",
            rule_type="inventory_balance",
            target_table="Inventory",
            target_column="OnHandQuantity",
            operation="sum",
            input_columns=[],
            source_table="InventoryTransaction",
            source_column="TransactionQuantity",
            group_by_columns=["ComponentID", "PlantID", "WarehouseID"],
            formula="SUM(InventoryTransaction.TransactionQuantity) GROUP BY ComponentID, PlantID, WarehouseID",
        ),
        "MISSING_TABLE": FormulaRule(
            rule_id="MISSING_TABLE",
            rule_type="row_level",
            target_table="MissingTable",
            target_column="SomeColumn",
            operation="add",
            input_columns=["A", "B"],
            formula="A + B",
        ),
        "VALIDATION_ONLY": FormulaRule(
            rule_id="VALIDATION_ONLY",
            rule_type="quantity_reconciliation",
            target_table="PurchaseOrderLine",
            target_column="OrderedQuantity",
            operation="less_than_or_equal",
            input_columns=["OrderedQuantity", "RequestedQuantity"],
            formula="OrderedQuantity <= RequestedQuantity",
        ),
    }
    return rules[rule_id]


def _plan(rules: list[FormulaRule]) -> LLMGenerationPlan:
    return LLMGenerationPlan(
        module="procurement",
        business_summary="Formula engine unit test plan.",
        domain_profile=DomainProfile(industry="Test manufacturing"),
        table_role_mapping=[],
        generation_order=["PurchaseOrderHdr", "PurchaseOrderLine"],
        row_count_plan=[],
        column_generation_rules=[],
        formula_rules=rules,
        date_rules=[],
        quantity_rules=[],
        status_rules=[],
        validation_rules=[],
        assumptions=[],
        warnings=[],
    )


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "PurchaseOrderLine": TableContract(
                table_name="PurchaseOrderLine",
                process_order=1,
                area="Procurement",
                table_role="purchase_order_line",
                target_rows=3,
                columns=[
                    _col("PurchaseOrderLineID", "int", "sequence_id", "No", "PK"),
                    _col("PurchaseOrderID", "int", "foreign_key", "No", "FK"),
                    _col("OrderedQuantity", "int", "integer_range", "No"),
                    _col("UnitPrice", "decimal(18,2)", "decimal_range", "No"),
                    _col("LineAmount", "decimal(18,2)", "calculated", "No"),
                ],
            ),
            "PurchaseOrderHdr": TableContract(
                table_name="PurchaseOrderHdr",
                process_order=2,
                area="Procurement",
                table_role="purchase_order_header",
                target_rows=2,
                columns=[
                    _col("PurchaseOrderID", "int", "sequence_id", "No", "PK"),
                    _col("TotalAmount", "decimal(18,2)", "calculated", "No"),
                    _col("LineCount", "int", "calculated", "No"),
                ],
            ),
            "GoodsReceiptHeader": TableContract(
                table_name="GoodsReceiptHeader",
                process_order=3,
                area="Receiving",
                table_role="goods_receipt_header",
                target_rows=2,
                columns=[
                    _col("GoodsReceiptID", "int", "sequence_id", "No", "PK"),
                    _col("ReceiptDate", "date", "date_range", "No"),
                    _col("ExpectedDeliveryDate", "date", "date_range", "No"),
                    _col("DelayDays", "int", "calculated", "Yes"),
                ],
            ),
            "InspectionResult": TableContract(
                table_name="InspectionResult",
                process_order=4,
                area="Quality",
                table_role="inspection_result",
                target_rows=3,
                columns=[
                    _col("InspectionResultID", "int", "sequence_id", "No", "PK"),
                    _col("InspectedQuantity", "int", "integer_range", "No"),
                    _col("AcceptedQuantity", "int", "integer_range", "No"),
                    _col("RejectedQuantity", "int", "calculated", "No"),
                    _col("RejectionRatePct", "decimal(5,2)", "calculated", "Yes"),
                ],
            ),
            "InventoryTransaction": TableContract(
                table_name="InventoryTransaction",
                process_order=5,
                area="Inventory",
                table_role="inventory_transaction",
                target_rows=3,
                columns=[
                    _col("InventoryTransactionID", "int", "sequence_id", "No", "PK"),
                    _col("ComponentID", "int", "foreign_key", "No", "FK"),
                    _col("PlantID", "int", "foreign_key", "No", "FK"),
                    _col("WarehouseID", "int", "foreign_key", "No", "FK"),
                    _col("TransactionQuantity", "int", "integer_range", "No"),
                ],
            ),
            "Inventory": TableContract(
                table_name="Inventory",
                process_order=6,
                area="Inventory",
                table_role="inventory",
                target_rows=2,
                columns=[
                    _col("InventoryID", "int", "sequence_id", "No", "PK"),
                    _col("ComponentID", "int", "foreign_key", "No", "FK"),
                    _col("PlantID", "int", "foreign_key", "No", "FK"),
                    _col("WarehouseID", "int", "foreign_key", "No", "FK"),
                    _col("OnHandQuantity", "int", "calculated", "No"),
                ],
            ),
        }
    )


def _col(column_name, data_type, generation_type, nullable, key_type=None) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type=data_type,
        key_type=key_type,
        related_table="Parent" if key_type == "FK" else None,
        related_column="ParentID" if key_type == "FK" else None,
        nullable=nullable,
        generation_type=generation_type,
        allowed_values=[],
        min_value=None,
        max_value=None,
        formula=None,
    )


def _has_infinity(series: pd.Series) -> bool:
    return any(math.isinf(value) for value in pd.to_numeric(series, errors="coerce").dropna())
