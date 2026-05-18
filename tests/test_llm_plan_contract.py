from __future__ import annotations

from copy import deepcopy

import pytest

from procurement_data_generator.core.contracts.llm_plan_contract import NormalizedLLMGenerationPlan
from procurement_data_generator.core.llm.plan_loader import validate_llm_plan_data


def test_valid_llm_plan_json_passes() -> None:
    result = validate_llm_plan_data(_valid_plan())

    assert result.report.is_valid
    assert result.plan is not None
    assert result.plan.module == "procurement"
    assert len(result.plan.generation_order) == 1


def test_invalid_module_fails() -> None:
    plan = _valid_plan()
    plan["module"] = "sales"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("module" in (issue.table_name or "") for issue in result.report.errors)


def test_unsupported_generation_type_fails() -> None:
    plan = _valid_plan()
    plan["column_generation_rules"][0]["generation_type"] = "unsafe_generator"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("column_generation_rules[0].generation_type" in (issue.table_name or "") for issue in result.report.errors)


def test_unsupported_formula_operation_fails() -> None:
    plan = _valid_plan()
    plan["formula_rules"][0]["operation"] = "unsafe_eval"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("formula_rules[0].operation" in (issue.table_name or "") for issue in result.report.errors)


def test_unsupported_formula_rule_type_fails() -> None:
    plan = _valid_plan()
    plan["formula_rules"][0]["rule_type"] = "unsafe_rule"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("formula_rules[0].rule_type" in (issue.table_name or "") for issue in result.report.errors)


def test_live_plan_drops_unsupported_inventory_balance_formula_aliases() -> None:
    plan = _valid_plan()
    plan["formula_rules"].append(
        {
            "rule_id": "live_available_quantity",
            "rule_type": "inventory_balance",
            "target_table": "Inventory",
            "target_column": "AvailableQuantity",
            "operation": "subtract",
            "input_columns": ["OnHandQuantity", "ReservedQuantity"],
            "description": "Live plan alias; Python inventory logic owns this field.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.formula_rules] == ["formula_line_amount"]


def test_live_plan_drops_unsupported_inventory_available_value_formula_alias() -> None:
    plan = _valid_plan()
    plan["formula_rules"].append(
        {
            "rule_id": "live_available_value",
            "rule_type": "row_level",
            "target_table": "Inventory",
            "target_column": "AvailableValue",
            "operation": "multiply",
            "input_columns": ["AvailableQuantity"],
            "formula": "AvailableQuantity * (OnHandValue / OnHandQuantity)",
            "denominator_column": "OnHandQuantity",
            "denominator_guard": True,
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
            "description": "Live plan alias; Python inventory logic owns this field.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.formula_rules] == ["formula_line_amount"]


def test_live_plan_drops_non_date_table_local_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_bad_short_quantity_date",
            "table_name": "GoodsReceiptLine",
            "date_columns": ["ShortQuantity"],
            "description": "Bad live alias; ShortQuantity is not a date field.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.date_rules] == ["date_req_before_order"]


def test_live_plan_drops_global_all_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_global_2025_scope",
            "rule_type": "date_order",
            "table_name": "All",
            "date_columns": ["RequisitionDate", "RequiredDate", "OrderDate", "PaymentDate"],
            "operator": "less_than_or_equal",
            "description": "All generated dates must remain within calendar year 2025 where applicable.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.date_rules] == ["date_req_before_order"]


def test_live_plan_drops_conceptual_date_guidance_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "procurement_date_sequence",
            "description": "Enforce procurement lifecycle dates in order within 2025.",
            "severity": "error",
            "confidence": "high",
            "applies_to_tables": ["PurchaseRequisition", "RFQHeader", "SupplierQuotation"],
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.date_rules] == ["date_req_before_order"]


def test_live_plan_normalizes_target_table_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_po_date_sequence",
            "target_table": "PurchaseOrderHdr",
            "date_columns": ["OrderDate", "ExpectedDeliveryDate"],
            "rule_type": "date_order",
            "operation": "less_than_or_equal",
            "formula": "OrderDate <= ExpectedDeliveryDate",
            "description": "Live plan alias; normalize to the strict date rule contract.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.date_rules[-1]
    assert normalized.rule_id == "live_po_date_sequence"
    assert normalized.earlier_table == "PurchaseOrderHdr"
    assert normalized.earlier_column == "OrderDate"
    assert normalized.later_table == "PurchaseOrderHdr"
    assert normalized.later_column == "ExpectedDeliveryDate"


def test_live_plan_normalizes_target_columns_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_rfq_date_sequence",
            "target_table": "RFQHeader",
            "target_columns": ["RFQDate", "RFQDueDate"],
            "rule_type": "date_order",
            "operation": "less_than_or_equal",
            "tolerance_type": "absolute",
            "tolerance_value": 0,
            "source_table": None,
            "source_column": None,
            "description": "Live Azure alias; normalize to strict date rule fields.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.date_rules[-1]
    assert normalized.rule_id == "live_rfq_date_sequence"
    assert normalized.earlier_table == "RFQHeader"
    assert normalized.earlier_column == "RFQDate"
    assert normalized.later_table == "RFQHeader"
    assert normalized.later_column == "RFQDueDate"


def test_live_plan_normalizes_source_target_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_receipt_after_shipment",
            "target_table": "GoodsReceiptHeader",
            "target_columns": ["ReceiptDate"],
            "rule_type": "date_order",
            "operation": "greater_than_or_equal",
            "source_table": "ShipmentHdr",
            "source_column": "ShipmentDate",
            "description": "Live Azure alias; normalize cross-table date order.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.date_rules[-1]
    assert normalized.rule_id == "live_receipt_after_shipment"
    assert normalized.earlier_table == "ShipmentHdr"
    assert normalized.earlier_column == "ShipmentDate"
    assert normalized.later_table == "GoodsReceiptHeader"
    assert normalized.later_column == "ReceiptDate"


def test_live_plan_normalizes_source_target_column_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_payment_after_invoice",
            "rule_type": "date_diff",
            "source_table": "SupplierInvoice",
            "target_table": "PaymentTransaction",
            "source_column": "InvoiceDate",
            "target_column": "PaymentDate",
            "relationship_key": "SupplierInvoiceID",
            "allowed_sequence": ["InvoiceDate", "PaymentDate"],
            "min_offset_days": 0,
            "max_offset_days": 60,
            "tolerance_days": 0,
            "severity": "error",
            "confidence": "high",
            "description": "Live Azure alias uses source/target date columns.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.date_rules[-1]
    assert normalized.rule_id == "live_payment_after_invoice"
    assert normalized.earlier_table == "SupplierInvoice"
    assert normalized.earlier_column == "InvoiceDate"
    assert normalized.later_table == "PaymentTransaction"
    assert normalized.later_column == "PaymentDate"


def test_live_plan_drops_source_target_date_alias_when_source_is_not_date() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_transaction_after_inspection_id",
            "target_table": "InventoryTransaction",
            "target_columns": ["TransactionDate"],
            "rule_type": "date_order",
            "operation": "greater_than_or_equal",
            "source_table": "InspectionResult",
            "source_column": "InspectionID",
            "description": "Live Azure alias uses an ID as a date source; drop it.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.date_rules] == ["date_req_before_order"]


def test_live_plan_normalizes_start_end_date_aliases() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_required_after_requisition",
            "rule_type": "date_order",
            "table_name": "PurchaseRequisition",
            "start_column": "RequisitionDate",
            "end_column": "RequiredDate",
            "operator": "less_than_or_equal",
            "description": "Live plan alias; normalize start/end columns.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.date_rules[-1]
    assert normalized.rule_id == "live_required_after_requisition"
    assert normalized.earlier_table == "PurchaseRequisition"
    assert normalized.earlier_column == "RequisitionDate"
    assert normalized.later_table == "PurchaseRequisition"
    assert normalized.later_column == "RequiredDate"


def test_live_plan_drops_start_end_aliases_when_columns_are_not_dates() -> None:
    plan = _valid_plan()
    plan["date_rules"].append(
        {
            "rule_id": "live_lineage_id_alias",
            "rule_type": "date_order",
            "table_name": "RFQHeader",
            "start_column": "RequisitionID",
            "end_column": "RFQDate",
            "operator": "less_than_or_equal",
            "description": "Live plan alias for lineage; Python validation owns this.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.date_rules] == ["date_req_before_order"]


def test_live_plan_drops_flag_columns_from_status_aliases() -> None:
    plan = _valid_plan()
    plan["status_rules"].append(
        {
            "rule_id": "live_cross_year_flag",
            "table_name": "InventoryReceiptDetail",
            "column_name": "CrossYearDeliveryFlag",
            "allowed_values": ["0"],
            "description": "Live plan alias; numeric flags are not status rules.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.status_rules] == ["status_po"]


def test_live_plan_drops_conceptual_status_guidance_aliases() -> None:
    plan = _valid_plan()
    plan["status_rules"].append(
        {
            "rule_id": "inventory_transaction_stockin_only",
            "description": "InventoryTransaction.TransactionType must be StockIn only.",
            "severity": "error",
            "confidence": "high",
            "applies_to_tables": ["InventoryTransaction"],
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert [rule.rule_id for rule in result.plan.status_rules] == ["status_po"]


def test_live_plan_normalizes_target_table_status_aliases() -> None:
    plan = _valid_plan()
    plan["status_rules"][0] = {
        "rule_id": "live_po_status",
        "target_table": "PurchaseOrderHdr",
        "status_column": "POStatus",
        "allowed_values": ["Received"],
        "description": "Live plan alias; normalize to the strict status rule contract.",
    }

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.status_rules[0]
    assert normalized.table_name == "PurchaseOrderHdr"
    assert normalized.status_values == ["Received"]
    assert normalized.derivation_logic == "Live plan alias; normalize to the strict status rule contract."


def test_live_plan_normalizes_target_column_status_aliases() -> None:
    plan = _valid_plan()
    plan["status_rules"][0] = {
        "rule_id": "live_po_status",
        "target_table": "PurchaseOrderHdr",
        "target_column": "POStatus",
        "allowed_values": ["Received"],
        "description": "Live Azure alias uses target_column for the status field.",
    }

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    normalized = result.plan.status_rules[0]
    assert normalized.table_name == "PurchaseOrderHdr"
    assert normalized.status_column == "POStatus"
    assert normalized.status_values == ["Received"]


def test_invalid_confidence_fails() -> None:
    plan = _valid_plan()
    plan["table_role_mapping"][0]["confidence"] = "certain"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("table_role_mapping[0].confidence" in (issue.table_name or "") for issue in result.report.errors)


def test_target_rows_less_than_or_equal_to_zero_fails() -> None:
    plan = _valid_plan()
    plan["row_count_plan"][0]["target_rows"] = 0

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("row_count_plan[0].target_rows" in (issue.table_name or "") for issue in result.report.errors)


def test_invalid_validation_severity_fails() -> None:
    plan = _valid_plan()
    plan["validation_rules"][0]["severity"] = "critical"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("validation_rules[0].severity" in (issue.table_name or "") for issue in result.report.errors)


def test_live_plan_accepts_generic_validation_rule_type() -> None:
    plan = _valid_plan()
    plan["validation_rules"].append(
        {
            "rule_id": "live_supplier_component_eligibility",
            "rule_type": "validation",
            "severity": "error",
            "table_name": "SupplierComponent",
            "column_name": "ComponentID",
            "related_table": "SupplierMaster",
            "related_column": "SupplierCategory",
            "description": "Supplier-component mapping must respect supplier category and component category compatibility.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    generic_rule = result.plan.validation_rules[-1]
    assert generic_rule.rule_type == "validation"
    assert "Supplier-component mapping must respect supplier category" in generic_rule.condition


def test_live_plan_normalizes_validation_type_alias() -> None:
    plan = _valid_plan()
    plan["validation_rules"].append(
        {
            "rule_id": "live_pk_presence",
            "validation_type": "pk_check",
            "severity": "error",
            "confidence": "high",
            "description": "All primary keys must be present and unique across each table.",
        }
    )

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    generic_rule = result.plan.validation_rules[-1]
    assert generic_rule.rule_type == "pk_check"
    assert "All primary keys" in generic_rule.condition


def test_empty_generation_order_fails() -> None:
    plan = _valid_plan()
    plan["generation_order"] = []

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    assert any("generation_order" in (issue.table_name or "") for issue in result.report.errors)


def test_assumptions_and_warnings_must_be_lists() -> None:
    plan = _valid_plan()
    plan["assumptions"] = "not a list"
    plan["warnings"] = "not a list"

    result = validate_llm_plan_data(plan)

    assert not result.report.is_valid
    fields = [issue.table_name for issue in result.report.errors]
    assert "Field: assumptions" in fields
    assert "Field: warnings" in fields


def test_assumptions_and_warnings_lists_are_accepted() -> None:
    plan = _valid_plan()
    plan["assumptions"] = []
    plan["warnings"] = []

    result = validate_llm_plan_data(plan)

    assert result.report.is_valid
    assert result.plan is not None
    assert result.plan.assumptions == []
    assert result.plan.warnings == []


def test_normalized_one_module_plan_contract_accepts_unknown_future_module() -> None:
    plan = NormalizedLLMGenerationPlan.model_validate(
        {
            "plan_id": "quality_v1_default",
            "plan_version": "1.0",
            "industry": "Discrete manufacturing",
            "module_set": ["quality"],
            "module_versions": {"quality": "v1"},
            "modules": {"quality": {"planning_rules": []}},
            "global_assumptions": ["Future module contract test."],
            "validation_rules": [],
        }
    )

    assert plan.module_set == ["quality"]
    assert plan.modules["quality"] == {"planning_rules": []}


def test_normalized_multi_module_plan_contract_accepts_multiple_modules() -> None:
    plan = NormalizedLLMGenerationPlan.model_validate(
        {
            "plan_id": "mes_plan",
            "module_set": ["procurement", "production", "quality"],
            "module_versions": {"procurement": "v2", "production": "v1", "quality": "v1"},
            "operating_scope": {
                "plant_count": 1,
                "warehouse_count": 1,
                "shift_codes": ["A"],
                "calendar_year": 2025,
            },
            "modules": {
                "procurement": {"legacy_plan": _valid_plan()},
                "production": {"planning_rules": []},
            },
        }
    )

    assert plan.module_set == ["procurement", "production", "quality"]
    assert plan.modules["quality"] == {}
    assert plan.operating_scope is not None
    assert plan.operating_scope.shift_codes == ["A"]


def test_normalized_plan_rejects_empty_module_set() -> None:
    with pytest.raises(ValueError, match="module_set"):
        NormalizedLLMGenerationPlan.model_validate({"module_set": [], "modules": {}})


def test_normalized_plan_rejects_duplicate_module_ids() -> None:
    with pytest.raises(ValueError, match="duplicate module ids"):
        NormalizedLLMGenerationPlan.model_validate({"module_set": ["procurement", "Procurement"], "modules": {}})


def _valid_plan() -> dict[str, object]:
    return deepcopy(
        {
            "module": "procurement",
            "business_summary": "EV manufacturing procurement plan.",
            "domain_profile": {
                "industry": "EV manufacturing",
                "business_context": "Battery and motor component procurement.",
                "vendor_categories": ["Battery suppliers"],
                "material_categories": [
                    {
                        "category_name": "Battery Components",
                        "material_examples": ["Lithium-Ion Cell"],
                        "specification_patterns": ["21700"],
                    }
                ],
                "warehouse_types": ["Raw Material"],
                "plant_locations": ["Bengaluru"],
                "carrier_name_patterns": ["regional freight carrier"],
                "inspection_test_categories": ["Electrical continuity"],
            },
            "table_role_mapping": [
                {
                    "table_name": "SupplierMaster",
                    "table_role": "supplier_master",
                    "area": "Master",
                    "confidence": "high",
                    "reasoning": "Supplier master table.",
                }
            ],
            "generation_order": ["SupplierMaster"],
            "row_count_plan": [
                {
                    "table_name": "SupplierMaster",
                    "target_rows": 10,
                    "source": "metadata",
                    "reasoning": "Use metadata row count.",
                }
            ],
            "column_generation_rules": [
                {
                    "table_name": "SupplierMaster",
                    "column_name": "SupplierName",
                    "generation_type": "vendor_name",
                    "strategy": "Generate realistic supplier names.",
                    "allowed_values": [],
                    "min_value": None,
                    "max_value": None,
                    "nullable_strategy": "never_null",
                    "depends_on_columns": [],
                    "notes": None,
                }
            ],
            "formula_rules": [
                {
                    "rule_id": "formula_line_amount",
                    "rule_type": "row_level",
                    "target_table": "PurchaseOrderLine",
                    "target_column": "LineAmount",
                    "operation": "multiply",
                    "input_columns": ["OrderedQuantity", "UnitPrice"],
                    "source_table": None,
                    "source_column": None,
                    "relationship_key": None,
                    "group_by_columns": [],
                    "formula": "OrderedQuantity * UnitPrice",
                    "denominator_column": None,
                    "denominator_guard": False,
                    "tolerance_type": "none",
                    "tolerance_value": None,
                    "description": "Line amount calculation.",
                }
            ],
            "date_rules": [
                {
                    "rule_id": "date_req_before_order",
                    "earlier_table": "PurchaseRequisition",
                    "earlier_column": "RequisitionDate",
                    "later_table": "PurchaseOrderHdr",
                    "later_column": "OrderDate",
                    "min_offset_days": 0,
                    "max_offset_days": 14,
                    "description": "Requisition before order.",
                }
            ],
            "quantity_rules": [
                {
                    "rule_id": "qty_ship_lte_order",
                    "left_table": "ShipmentLine",
                    "left_column": "ShippedQuantity",
                    "operator": "<=",
                    "right_table": "PurchaseOrderLine",
                    "right_column": "OrderedQuantity",
                    "description": "Shipment cannot exceed order.",
                }
            ],
            "status_rules": [
                {
                    "rule_id": "status_po",
                    "table_name": "PurchaseOrderHdr",
                    "status_column": "POStatus",
                    "status_values": ["Received"],
                    "derivation_logic": "Derive from order lifecycle.",
                    "description": "Lifecycle status.",
                }
            ],
            "validation_rules": [
                {
                    "rule_id": "validate_pk",
                    "rule_type": "pk_check",
                    "table_name": "SupplierMaster",
                    "column_name": "SupplierID",
                    "condition": "SupplierID is unique and non-null",
                    "severity": "error",
                    "description": "PK validation.",
                }
            ],
            "assumptions": ["Metadata is source of truth."],
            "warnings": ["Partial lifecycle records are allowed."],
        }
    )
