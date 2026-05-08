from __future__ import annotations

import numpy as np
import pandas as pd

from procurement_data_generator.core.contracts.llm_plan_contract import DomainProfile, FormulaRule, LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.formulas.formula_engine import SafeFormulaEngine


def test_supplier_quotation_line_amount_formula() -> None:
    updated, report = _execute([_rule("QUOTE_LINE_AMOUNT")])

    assert report.status == "passed"
    assert list(updated["SupplierQuotationLn"]["QuotedLineAmount"]) == [25.0, 90.0]


def test_purchase_order_line_amount_formula() -> None:
    updated, report = _execute([_rule("PO_LINE_AMOUNT")])

    assert report.status == "passed"
    assert list(updated["PurchaseOrderLine"]["LineAmount"]) == [20.0, 60.0, 20.0]


def test_purchase_order_header_total_aggregate_formula() -> None:
    updated, report = _execute([_rule("PO_LINE_AMOUNT"), _rule("PO_HEADER_TOTAL")])

    assert report.status == "passed"
    assert list(updated["PurchaseOrderHdr"]["TotalAmount"]) == [80.0, 20.0]


def test_goods_receipt_short_quantity_formula() -> None:
    updated, report = _execute([_rule("SHORT_QTY")])

    assert report.status == "passed"
    assert list(updated["GoodsReceiptLine"]["ShortQuantity"]) == [2.0, 0.0]


def test_inspection_rejected_quantity_formula() -> None:
    updated, report = _execute([_rule("REJECTED_QTY")])

    assert report.status == "passed"
    assert list(updated["InspectionResult"]["RejectedQuantity"]) == [2.0, 0.0, 0.0]


def test_inspection_rejection_rate_formula() -> None:
    updated, report = _execute([_rule("REJECTED_QTY"), _rule("REJECTION_RATE")])

    assert report.status == "passed"
    assert list(updated["InspectionResult"]["RejectionRatePct"].dropna()) == [20.0, 0.0]


def test_rejection_rate_denominator_zero_returns_null_not_infinity() -> None:
    updated, report = _execute([_rule("REJECTED_QTY"), _rule("REJECTION_RATE_DIVIDE")])
    value = updated["InspectionResult"].loc[2, "RejectionRatePct"]

    assert report.status == "passed"
    assert pd.isna(value)
    assert not _has_infinity(updated["InspectionResult"]["RejectionRatePct"])


def test_supplier_invoice_total_amount_adds_three_columns() -> None:
    updated, report = _execute([_rule("INVOICE_TOTAL")])

    assert report.status == "passed"
    assert list(updated["SupplierInvoice"]["TotalInvoiceAmount"]) == [108.0, 216.0]


def test_inventory_transaction_value_formula_uses_decimal_money_rounding() -> None:
    updated, report = _execute([_rule("INVENTORY_VALUE")])

    assert report.status == "passed"
    assert list(updated["InventoryTransaction"]["InventoryValue"]) == [1359444.70, 2066116.18]


def test_formula_ordering_places_line_amount_before_header_total() -> None:
    updated, report = _execute([_rule("PO_HEADER_TOTAL"), _rule("PO_LINE_AMOUNT")])

    assert report.status == "passed"
    assert list(updated["PurchaseOrderHdr"]["TotalAmount"]) == [80.0, 20.0]


def test_formula_ordering_places_rejected_quantity_before_rejection_rate() -> None:
    updated, report = _execute([_rule("REJECTION_RATE"), _rule("REJECTED_QTY")])

    assert report.status == "passed"
    assert list(updated["InspectionResult"]["RejectedQuantity"]) == [2.0, 0.0, 0.0]
    assert list(updated["InspectionResult"]["RejectionRatePct"].dropna()) == [20.0, 0.0]


def test_unsupported_invoice_amount_cross_table_formula_fails_gracefully() -> None:
    updated, report = _execute([_rule("UNSUPPORTED_INVOICE_AMOUNT")])

    assert report.failed_count == 1
    assert "Missing required column" in report.failed_rules[0].message
    assert "SupplierInvoice" in updated


def test_formula_report_counts_applied_skipped_failed() -> None:
    updated, report = _execute([_rule("PO_LINE_AMOUNT"), _rule("VALIDATION_ONLY"), _rule("UNSUPPORTED_INVOICE_AMOUNT")])

    assert updated["PurchaseOrderLine"]["LineAmount"].iloc[0] == 20.0
    assert report.total_rules == 3
    assert report.applied_count == 1
    assert report.skipped_count == 1
    assert report.failed_count == 1
    assert report.status == "failed"


def test_no_infinity_in_v2_formula_outputs() -> None:
    updated, report = _execute([_rule("REJECTED_QTY"), _rule("REJECTION_RATE_DIVIDE"), _rule("INVOICE_TOTAL")])

    assert report.status == "passed"
    for dataframe in updated.values():
        for column in dataframe.columns:
            assert not _has_infinity(dataframe[column])


def _execute(rules: list[FormulaRule]):
    return SafeFormulaEngine().execute_formulas(_dataframes(), _plan(rules), _schema())


def _dataframes() -> dict[str, pd.DataFrame]:
    return {
        "SupplierQuotationLn": pd.DataFrame(
            {
                "QuotationLineID": [1, 2],
                "QuotedQuantity": [2, 3],
                "QuotedUnitPrice": [12.5, 30.0],
                "QuotedLineAmount": [0.0, 0.0],
            }
        ),
        "PurchaseOrderHdr": pd.DataFrame({"PurchaseOrderID": [10, 11], "TotalAmount": [0.0, 0.0]}),
        "PurchaseOrderLine": pd.DataFrame(
            {
                "PurchaseOrderLineID": [1, 2, 3],
                "PurchaseOrderID": [10, 10, 11],
                "OrderedQuantity": [2, 3, 4],
                "UnitPrice": [10.0, 20.0, 5.0],
                "LineAmount": [0.0, 0.0, 0.0],
            }
        ),
        "GoodsReceiptLine": pd.DataFrame(
            {"GoodsReceiptLineID": [1, 2], "ShippedQuantity": [10.0, 5.0], "ReceivedQuantity": [8.0, 5.0], "ShortQuantity": [0.0, 0.0]}
        ),
        "InspectionResult": pd.DataFrame(
            {
                "InspectionResultID": [1, 2, 3],
                "InspectedQuantity": [10.0, 5.0, 0.0],
                "AcceptedQuantity": [8.0, 5.0, 0.0],
                "RejectedQuantity": [0.0, 0.0, 0.0],
                "RejectionRatePct": [0.0, 0.0, 0.0],
            }
        ),
        "SupplierInvoice": pd.DataFrame(
            {
                "SupplierInvoiceID": [1, 2],
                "GoodsReceiptID": [100, 101],
                "InvoiceAmount": [100.0, 200.0],
                "TaxAmount": [5.0, 10.0],
                "FreightAmount": [3.0, 6.0],
                "TotalInvoiceAmount": [0.0, 0.0],
            }
        ),
        "InventoryTransaction": pd.DataFrame(
            {
                "InventoryTransactionID": [1, 2],
                "TransactionQuantity": [283.38, 882.39],
                "UnitPrice": [4797.25, 2341.50],
                "InventoryValue": [0.0, 0.0],
            }
        ),
        "GoodsReceiptLineForInvoice": pd.DataFrame(
            {"GoodsReceiptID": [100], "ReceivedQuantity": [4.0], "PurchaseOrderLineID": [1]}
        ),
    }


def _rule(rule_id: str) -> FormulaRule:
    rules = {
        "QUOTE_LINE_AMOUNT": FormulaRule(
            rule_id="quote_line_amount",
            rule_type="row_level",
            operation="multiply",
            target_table="SupplierQuotationLn",
            target_column="QuotedLineAmount",
            input_columns=["QuotedQuantity", "QuotedUnitPrice"],
            formula="QuotedQuantity * QuotedUnitPrice",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "PO_LINE_AMOUNT": FormulaRule(
            rule_id="po_line_amount",
            rule_type="row_level",
            operation="multiply",
            target_table="PurchaseOrderLine",
            target_column="LineAmount",
            input_columns=["OrderedQuantity", "UnitPrice"],
            formula="OrderedQuantity * UnitPrice",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "PO_HEADER_TOTAL": FormulaRule(
            rule_id="po_header_total",
            rule_type="aggregate",
            operation="sum",
            target_table="PurchaseOrderHdr",
            target_column="TotalAmount",
            input_columns=[],
            source_table="PurchaseOrderLine",
            source_column="LineAmount",
            relationship_key="PurchaseOrderID",
            formula="SUM(PurchaseOrderLine.LineAmount)",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "SHORT_QTY": FormulaRule(
            rule_id="short_qty",
            rule_type="row_level",
            operation="subtract",
            target_table="GoodsReceiptLine",
            target_column="ShortQuantity",
            input_columns=["ShippedQuantity", "ReceivedQuantity"],
            formula="ShippedQuantity - ReceivedQuantity",
            tolerance_type="absolute",
            tolerance_value=0.0001,
        ),
        "REJECTED_QTY": FormulaRule(
            rule_id="rejected_qty",
            rule_type="row_level",
            operation="subtract",
            target_table="InspectionResult",
            target_column="RejectedQuantity",
            input_columns=["InspectedQuantity", "AcceptedQuantity"],
            formula="InspectedQuantity - AcceptedQuantity",
            tolerance_type="absolute",
            tolerance_value=0.0001,
        ),
        "REJECTION_RATE": FormulaRule(
            rule_id="rejection_rate",
            rule_type="percentage",
            operation="percentage",
            target_table="InspectionResult",
            target_column="RejectionRatePct",
            input_columns=["RejectedQuantity", "InspectedQuantity"],
            denominator_column="InspectedQuantity",
            denominator_guard=True,
            formula="RejectedQuantity / InspectedQuantity * 100",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "REJECTION_RATE_DIVIDE": FormulaRule(
            rule_id="rejection_rate_divide",
            rule_type="percentage",
            operation="divide",
            target_table="InspectionResult",
            target_column="RejectionRatePct",
            input_columns=["RejectedQuantity", "InspectedQuantity"],
            denominator_column="InspectedQuantity",
            denominator_guard=True,
            formula="RejectedQuantity / InspectedQuantity * 100",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "INVOICE_TOTAL": FormulaRule(
            rule_id="invoice_total",
            rule_type="row_level",
            operation="add",
            target_table="SupplierInvoice",
            target_column="TotalInvoiceAmount",
            input_columns=["InvoiceAmount", "TaxAmount", "FreightAmount"],
            formula="InvoiceAmount + TaxAmount + FreightAmount",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "INVENTORY_VALUE": FormulaRule(
            rule_id="formula_inventory_transaction_value",
            rule_type="row_level",
            operation="multiply",
            target_table="InventoryTransaction",
            target_column="InventoryValue",
            input_columns=["TransactionQuantity", "UnitPrice"],
            formula="TransactionQuantity * UnitPrice",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "UNSUPPORTED_INVOICE_AMOUNT": FormulaRule(
            rule_id="invoice_amount_complex",
            rule_type="row_level",
            operation="multiply",
            target_table="SupplierInvoice",
            target_column="InvoiceAmount",
            input_columns=["ReceivedQuantity", "UnitPrice"],
            formula="SUM(GoodsReceiptLine.ReceivedQuantity * PurchaseOrderLine.UnitPrice)",
            tolerance_type="absolute",
            tolerance_value=0.01,
        ),
        "VALIDATION_ONLY": FormulaRule(
            rule_id="payment_lte_invoice",
            rule_type="quantity_reconciliation",
            operation="less_than_or_equal",
            target_table="SupplierInvoice",
            target_column="TotalInvoiceAmount",
            input_columns=["PaymentAmount", "TotalInvoiceAmount"],
            formula="PaymentAmount <= TotalInvoiceAmount",
        ),
    }
    return rules[rule_id]


def _plan(rules: list[FormulaRule]) -> LLMGenerationPlan:
    return LLMGenerationPlan(
        module="procurement",
        business_summary="v2 formula test plan",
        domain_profile=DomainProfile(industry="EV manufacturing"),
        generation_order=["SupplierQuotationLn", "PurchaseOrderHdr", "PurchaseOrderLine", "GoodsReceiptLine", "InspectionResult", "SupplierInvoice"],
        formula_rules=rules,
    )


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "SupplierQuotationLn": _table("SupplierQuotationLn", "supplier_quotation_line", [_col("QuotationLineID", "int", "sequence_id", "No", "PK"), _col("QuotedQuantity", "decimal(18,2)", "decimal_range", "No"), _col("QuotedUnitPrice", "decimal(18,2)", "decimal_range", "No"), _col("QuotedLineAmount", "decimal(18,2)", "calculated", "No")]),
            "PurchaseOrderHdr": _table("PurchaseOrderHdr", "purchase_order_header", [_col("PurchaseOrderID", "int", "sequence_id", "No", "PK"), _col("TotalAmount", "decimal(18,2)", "calculated", "No")]),
            "PurchaseOrderLine": _table("PurchaseOrderLine", "purchase_order_line", [_col("PurchaseOrderLineID", "int", "sequence_id", "No", "PK"), _col("PurchaseOrderID", "int", "foreign_key", "No"), _col("OrderedQuantity", "decimal(18,2)", "decimal_range", "No"), _col("UnitPrice", "decimal(18,2)", "decimal_range", "No"), _col("LineAmount", "decimal(18,2)", "calculated", "No")]),
            "GoodsReceiptLine": _table("GoodsReceiptLine", "goods_receipt_line", [_col("GoodsReceiptLineID", "int", "sequence_id", "No", "PK"), _col("ShippedQuantity", "decimal(18,2)", "decimal_range", "No"), _col("ReceivedQuantity", "decimal(18,2)", "decimal_range", "No"), _col("ShortQuantity", "decimal(18,2)", "calculated", "No")]),
            "InspectionResult": _table("InspectionResult", "inspection_result", [_col("InspectionResultID", "int", "sequence_id", "No", "PK"), _col("InspectedQuantity", "decimal(18,2)", "decimal_range", "No"), _col("AcceptedQuantity", "decimal(18,2)", "decimal_range", "No"), _col("RejectedQuantity", "decimal(18,2)", "calculated", "No"), _col("RejectionRatePct", "decimal(5,2)", "calculated", "Yes")]),
            "SupplierInvoice": _table("SupplierInvoice", "supplier_invoice", [_col("SupplierInvoiceID", "int", "sequence_id", "No", "PK"), _col("InvoiceAmount", "decimal(18,2)", "calculated", "No"), _col("TaxAmount", "decimal(18,2)", "decimal_range", "No"), _col("FreightAmount", "decimal(18,2)", "decimal_range", "No"), _col("TotalInvoiceAmount", "decimal(18,2)", "calculated", "No")]),
            "InventoryTransaction": _table("InventoryTransaction", "inventory_transaction", [_col("InventoryTransactionID", "int", "sequence_id", "No", "PK"), _col("TransactionQuantity", "decimal(18,2)", "decimal_range", "No"), _col("UnitPrice", "decimal(18,2)", "decimal_range", "No"), _col("InventoryValue", "decimal(18,2)", "calculated", "No")]),
        }
    )


def _table(name: str, role: str, columns: list[ColumnContract]) -> TableContract:
    return TableContract(table_name=name, process_order=1, area="Procurement" if name != "SupplierInvoice" else "Finance", table_role=role, target_rows=1, columns=columns)


def _col(name: str, data_type: str, generation_type: str, nullable: str, key_type: str | None = None) -> ColumnContract:
    return ColumnContract(column_name=name, data_type=data_type, generation_type=generation_type, nullable=nullable, key_type=key_type)


def _has_infinity(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return bool(np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any())
