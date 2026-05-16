from __future__ import annotations

from copy import deepcopy

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
