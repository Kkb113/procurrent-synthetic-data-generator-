from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.formulas.formula_engine import SafeFormulaEngine
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.core.validation.reconciler import ProcurementDataQualityEngine, ProcurementReconciler
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_po_line_amount_mismatch_is_detected() -> None:
    data = _valid_data()
    data["PurchaseOrderLine"].loc[0, "LineAmount"] = 19.0

    report = _reconcile(data)

    assert _has_issue(report, "PO_LINE_AMOUNT_RECONCILIATION")


def test_po_header_total_mismatch_is_detected() -> None:
    data = _valid_data()
    data["PurchaseOrderHeader"].loc[0, "TotalAmount"] = 0.0

    report = _reconcile(data)

    assert _has_issue(report, "PO_HEADER_TOTAL_RECONCILIATION")


def test_po_amount_reconciliation_uses_default_tolerance_when_plan_declares_none() -> None:
    data = _valid_data()
    data["PurchaseOrderHeader"].loc[0, "TotalAmount"] = 52292.8
    data["PurchaseOrderLine"].loc[0, "OrderedQuantity"] = 224
    data["PurchaseOrderLine"].loc[0, "UnitPrice"] = 233.45
    data["PurchaseOrderLine"].loc[0, "LineAmount"] = 52292.8

    plan_result = load_llm_plan_json(PROJECT_ROOT / "input" / "sample_formula_plan_phase10.json")
    assert plan_result.plan is not None
    formula_rules = [
        rule.model_copy(update={"tolerance_type": "none", "tolerance_value": 0.0})
        if rule.target_table in {"PurchaseOrderLine", "PurchaseOrderHeader"}
        else rule
        for rule in plan_result.plan.formula_rules
    ]
    plan = plan_result.plan.model_copy(update={"formula_rules": formula_rules})

    report = ProcurementReconciler().reconcile_dataset(data, _schema(), plan)

    assert not _has_issue(report, "PO_LINE_AMOUNT_RECONCILIATION")
    assert not _has_issue(report, "PO_HEADER_TOTAL_RECONCILIATION")


def test_shipped_quantity_greater_than_ordered_is_detected() -> None:
    data = _valid_data()
    data["ShipmentLine"].loc[0, "ShippedQuantity"] = 3

    report = _reconcile(data)

    assert _has_issue(report, "SHIPPED_LE_ORDERED")


def test_received_quantity_greater_than_shipped_is_detected() -> None:
    data = _valid_data()
    data["GoodsReceiptLine"].loc[0, "ReceivedQuantity"] = 3

    report = _reconcile(data)

    assert _has_issue(report, "RECEIVED_LE_SHIPPED")


def test_accepted_plus_rejected_mismatch_is_detected() -> None:
    data = _valid_data()
    data["QualityInspectionLine"].loc[0, "RejectedQuantity"] = 1

    report = _reconcile(data)

    assert _has_issue(report, "QUALITY_ACCEPT_REJECT_TOTAL")


def test_inventory_transaction_quantity_mismatch_is_detected() -> None:
    data = _valid_data()
    data["InventoryTransaction"].loc[0, "TransactionQuantity"] = 1

    report = _reconcile(data)

    assert _has_issue(report, "INVENTORY_TRANSACTION_ACCEPTED_QTY")


def test_inventory_balance_on_hand_mismatch_is_detected() -> None:
    data = _valid_data()
    data["InventoryBalance"].loc[0, "OnHandQuantity"] = 99

    report = _reconcile(data)

    assert _has_issue(report, "INVENTORY_BALANCE_ON_HAND")


def test_warehouse_plant_mismatch_is_detected() -> None:
    data = _valid_data()
    data["Warehouse"].loc[0, "PlantID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "WAREHOUSE_PLANT_ALIGNMENT")


def test_po_requisition_plant_mismatch_is_detected() -> None:
    data = _valid_data()
    data["PurchaseOrderHeader"].loc[0, "PlantID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "PLANT_REQUISITION_TO_PO")


def test_date_lifecycle_violation_is_detected() -> None:
    data = _valid_data()
    data["ShipmentHeader"].loc[0, "ShipmentDate"] = "2024-12-31"

    report = _reconcile(data)

    assert _has_issue(report, "DATE_ORDER_TO_SHIPMENT")


def test_suspicious_lifecycle_status_is_warning() -> None:
    data = _valid_data()
    data["QualityInspectionLine"].loc[0, "RejectedQuantity"] = 1
    data["QualityInspectionLine"].loc[0, "AcceptedQuantity"] = 1
    data["QualityInspectionLine"].loc[0, "ResultStatus"] = "Passed"

    report = _reconcile(data)

    assert _has_issue(report, "QUALITY_REJECTION_STATUS", level="warning")


def test_valid_generated_dataset_passes_or_passes_with_expected_warnings() -> None:
    schema_result = load_metadata_schema(PROJECT_ROOT / "input" / "sample_procurement_metadata_phase9.xlsx")
    plan_result = load_llm_plan_json(PROJECT_ROOT / "input" / "sample_generation_plan_phase9.json")
    formula_plan_result = load_llm_plan_json(PROJECT_ROOT / "input" / "sample_formula_plan_phase10.json")
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    assert formula_plan_result.plan is not None

    master, master_report = ProcurementMasterDataGenerator().generate_master_data(schema_result.schema, plan_result.plan, seed=42)
    transactions, transaction_report = ProcurementTransactionGenerator().generate_transaction_data(schema_result.schema, plan_result.plan, master, seed=42)
    assert master_report.is_valid
    assert transaction_report.is_valid
    formula_input = {**transactions}
    formula_updated, formula_report = SafeFormulaEngine().execute_formulas(formula_input, formula_plan_result.plan, schema_result.schema)
    assert formula_report.failed_count == 0

    final_data = {**master, **transactions, **formula_updated}
    report = ProcurementDataQualityEngine().validate_and_reconcile(final_data, schema_result.schema, formula_plan_result.plan)

    assert report.overall_status in {"passed", "passed_with_warnings"}
    assert report.error_count == 0
    assert _has_issue(report, "ROW_COUNT", level="warning")


def _reconcile(data):
    return ProcurementReconciler().reconcile_dataset(data, _schema())


def _valid_data() -> dict[str, pd.DataFrame]:
    return {
        "PurchaseRequisitionHeader": pd.DataFrame({"RequisitionID": [1], "PlantID": [1], "RequisitionDate": ["2025-01-01"]}),
        "PurchaseOrderHeader": pd.DataFrame(
            {"PurchaseOrderID": [10], "RequisitionID": [1], "PlantID": [1], "OrderDate": ["2025-01-02"], "TotalAmount": [20.0]}
        ),
        "PurchaseOrderLine": pd.DataFrame(
            {"PurchaseOrderLineID": [100], "PurchaseOrderID": [10], "OrderedQuantity": [2], "UnitPrice": [10.0], "LineAmount": [20.0]}
        ),
        "ShipmentHeader": pd.DataFrame({"ShipmentID": [20], "PurchaseOrderID": [10], "ShipmentDate": ["2025-01-03"]}),
        "ShipmentLine": pd.DataFrame({"ShipmentLineID": [200], "ShipmentID": [20], "PurchaseOrderLineID": [100], "ShippedQuantity": [2]}),
        "GoodsReceiptHeader": pd.DataFrame(
            {"GoodsReceiptID": [30], "ShipmentID": [20], "PlantID": [1], "WarehouseID": [5], "ReceiptDate": ["2025-01-04"], "ReceiptStatus": ["Received"]}
        ),
        "GoodsReceiptLine": pd.DataFrame(
            {
                "GoodsReceiptLineID": [300],
                "GoodsReceiptID": [30],
                "ShipmentLineID": [200],
                "ShippedQuantity": [2],
                "ReceivedQuantity": [2],
                "DamagedQuantity": [0],
                "ShortQuantity": [0],
            }
        ),
        "QualityInspectionHeader": pd.DataFrame({"InspectionID": [40], "GoodsReceiptLineID": [300], "InspectionDate": ["2025-01-05"]}),
        "QualityInspectionLine": pd.DataFrame(
            {"InspectionLineID": [400], "InspectionID": [40], "InspectedQuantity": [2], "AcceptedQuantity": [2], "RejectedQuantity": [0], "ResultStatus": ["Passed"]}
        ),
        "InventoryTransaction": pd.DataFrame(
            {"InventoryTransactionID": [500], "InspectionLineID": [400], "RawMaterialID": [7], "PlantID": [1], "WarehouseID": [5], "TransactionDate": ["2025-01-06"], "TransactionQuantity": [2]}
        ),
        "InventoryBalance": pd.DataFrame(
            {"InventoryBalanceID": [600], "RawMaterialID": [7], "PlantID": [1], "WarehouseID": [5], "OnHandQuantity": [2], "AvailableQuantity": [2]}
        ),
        "Warehouse": pd.DataFrame({"WarehouseID": [5], "PlantID": [1]}),
    }


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "Warehouse": _table("Warehouse", "Master", "warehouse_dimension", [_col("WarehouseID", "int", "sequence_id", "No", "PK"), _col("PlantID", "int", "foreign_key", "No", "FK")]),
            "PurchaseRequisitionHeader": _table("PurchaseRequisitionHeader", "Procurement", "purchase_requisition_header", [_col("RequisitionID", "int", "sequence_id", "No", "PK"), _col("PlantID", "int", "foreign_key", "No", "FK"), _col("RequisitionDate", "date", "date_range", "No")]),
            "PurchaseOrderHeader": _table("PurchaseOrderHeader", "Procurement", "purchase_order_header", [_col("PurchaseOrderID", "int", "sequence_id", "No", "PK"), _col("RequisitionID", "int", "foreign_key", "No", "FK"), _col("PlantID", "int", "foreign_key", "No", "FK"), _col("OrderDate", "date", "date_range", "No"), _col("TotalAmount", "decimal(18,2)", "calculated", "No")]),
            "PurchaseOrderLine": _table("PurchaseOrderLine", "Procurement", "purchase_order_line", [_col("PurchaseOrderLineID", "int", "sequence_id", "No", "PK"), _col("PurchaseOrderID", "int", "foreign_key", "No", "FK"), _col("OrderedQuantity", "int", "integer_range", "No"), _col("UnitPrice", "decimal(18,2)", "decimal_range", "No"), _col("LineAmount", "decimal(18,2)", "calculated", "No")]),
            "ShipmentHeader": _table("ShipmentHeader", "Logistics", "shipment_header", [_col("ShipmentID", "int", "sequence_id", "No", "PK"), _col("PurchaseOrderID", "int", "foreign_key", "No", "FK"), _col("ShipmentDate", "date", "date_range", "No")]),
            "ShipmentLine": _table("ShipmentLine", "Logistics", "shipment_line", [_col("ShipmentLineID", "int", "sequence_id", "No", "PK"), _col("ShipmentID", "int", "foreign_key", "No", "FK"), _col("PurchaseOrderLineID", "int", "foreign_key", "No", "FK"), _col("ShippedQuantity", "int", "integer_range", "No")]),
            "GoodsReceiptHeader": _table("GoodsReceiptHeader", "Receiving", "goods_receipt_header", [_col("GoodsReceiptID", "int", "sequence_id", "No", "PK"), _col("ShipmentID", "int", "foreign_key", "No", "FK"), _col("PlantID", "int", "foreign_key", "No", "FK"), _col("WarehouseID", "int", "foreign_key", "No", "FK"), _col("ReceiptDate", "date", "date_range", "No"), _col("ReceiptStatus", "varchar(20)", "status", "No")]),
            "GoodsReceiptLine": _table("GoodsReceiptLine", "Receiving", "goods_receipt_line", [_col("GoodsReceiptLineID", "int", "sequence_id", "No", "PK"), _col("GoodsReceiptID", "int", "foreign_key", "No", "FK"), _col("ShipmentLineID", "int", "foreign_key", "No", "FK"), _col("ShippedQuantity", "int", "integer_range", "No"), _col("ReceivedQuantity", "int", "integer_range", "No"), _col("DamagedQuantity", "int", "integer_range", "No"), _col("ShortQuantity", "int", "calculated", "No")]),
            "QualityInspectionHeader": _table("QualityInspectionHeader", "Quality", "quality_inspection_header", [_col("InspectionID", "int", "sequence_id", "No", "PK"), _col("GoodsReceiptLineID", "int", "foreign_key", "No", "FK"), _col("InspectionDate", "date", "date_range", "No")]),
            "QualityInspectionLine": _table("QualityInspectionLine", "Quality", "quality_inspection_line", [_col("InspectionLineID", "int", "sequence_id", "No", "PK"), _col("InspectionID", "int", "foreign_key", "No", "FK"), _col("InspectedQuantity", "int", "integer_range", "No"), _col("AcceptedQuantity", "int", "integer_range", "No"), _col("RejectedQuantity", "int", "calculated", "No"), _col("ResultStatus", "varchar(20)", "status", "No")]),
            "InventoryTransaction": _table("InventoryTransaction", "Inventory", "inventory_transaction", [_col("InventoryTransactionID", "int", "sequence_id", "No", "PK"), _col("InspectionLineID", "int", "foreign_key", "No", "FK"), _col("RawMaterialID", "int", "foreign_key", "No", "FK"), _col("PlantID", "int", "foreign_key", "No", "FK"), _col("WarehouseID", "int", "foreign_key", "No", "FK"), _col("TransactionDate", "date", "date_range", "No"), _col("TransactionQuantity", "int", "integer_range", "No")]),
            "InventoryBalance": _table("InventoryBalance", "Inventory", "inventory_balance", [_col("InventoryBalanceID", "int", "sequence_id", "No", "PK"), _col("RawMaterialID", "int", "foreign_key", "No", "FK"), _col("PlantID", "int", "foreign_key", "No", "FK"), _col("WarehouseID", "int", "foreign_key", "No", "FK"), _col("OnHandQuantity", "int", "calculated", "No"), _col("AvailableQuantity", "int", "calculated", "No")]),
        }
    )


def _table(table_name, area, role, columns):
    return TableContract(table_name=table_name, process_order=1, area=area, table_role=role, target_rows=1, columns=columns)


def _col(column_name, data_type, generation_type, nullable, key_type=None):
    return ColumnContract(column_name=column_name, data_type=data_type, key_type=key_type, related_table=None, related_column=None, nullable=nullable, generation_type=generation_type)


def _has_issue(report, check_type: str, level: str = "error") -> bool:
    return any(issue.check_type == check_type and issue.level == level for issue in report.issues)
