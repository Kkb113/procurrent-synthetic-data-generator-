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
