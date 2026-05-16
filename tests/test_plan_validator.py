from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = ROOT / "input" / "procurement_v2_erd.mmd"
VALID_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"


def test_valid_procurement_v2_plan_passes_semantic_validation() -> None:
    result = _validate(_load_plan_payload())

    assert result.report.is_valid
    assert result.summary.rejected_formula_rules == 0


def test_procurement_v2_plan_missing_required_table_fails() -> None:
    plan = _load_plan_payload()
    plan["generation_order"].remove("InventoryReceiptDetail")
    plan["table_role_mapping"] = [
        item for item in plan["table_role_mapping"] if item["table_name"] != "InventoryReceiptDetail"
    ]
    plan["row_count_plan"] = [
        item for item in plan["row_count_plan"] if item["table_name"] != "InventoryReceiptDetail"
    ]

    result = _validate(plan)

    assert not result.report.is_valid
    assert _has_issue(result, "InventoryReceiptDetail")


def test_procurement_v2_plan_rejects_inventory_balance_table() -> None:
    plan = _load_plan_payload()
    plan["generation_order"].append("InventoryBalance")
    plan["table_role_mapping"].append(
        {
            "table_name": "InventoryBalance",
            "table_role": "inventory_balance",
            "area": "Inventory",
            "confidence": "high",
            "reasoning": "Deprecated table.",
        }
    )

    result = _validate(plan)

    assert not result.report.is_valid
    assert _has_issue(result, "InventoryBalance")


def test_procurement_v2_plan_rejects_wrong_lifecycle_order() -> None:
    plan = _load_plan_payload()
    order = plan["generation_order"]
    order[order.index("InventoryReceiptDetail")], order[order.index("InspectionResult")] = (
        order[order.index("InspectionResult")],
        order[order.index("InventoryReceiptDetail")],
    )

    result = _validate(plan)

    assert not result.report.is_valid
    assert _has_issue(result, "order")


def test_procurement_v2_plan_rejects_unknown_formula_target() -> None:
    plan = _load_plan_payload()
    plan["formula_rules"][0]["target_table"] = "MissingTable"

    result = _validate(plan)

    assert not result.report.is_valid
    assert result.summary.rejected_formula_rules >= 1


def test_plan_validator_rejects_procurement_v1_model_version() -> None:
    schema_result = load_metadata_schema(METADATA)
    assert schema_result.schema is not None
    plan = LLMGenerationPlan.model_validate(_load_plan_payload())

    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        validate_generation_plan(
            plan,
            schema_result.schema,
            parse_mermaid_erd_file(ERD),
            model_version="v1",
        )


def _validate(plan_payload: dict):
    schema_result = load_metadata_schema(METADATA)
    assert schema_result.schema is not None
    plan = LLMGenerationPlan.model_validate(plan_payload)
    return validate_generation_plan(
        plan,
        schema_result.schema,
        parse_mermaid_erd_file(ERD),
        model_version="v2",
    )


def _load_plan_payload() -> dict:
    result = load_llm_plan_json(VALID_PLAN)
    assert result.plan is not None
    return deepcopy(result.plan.model_dump())


def _has_issue(result, text: str) -> bool:
    return any(text in issue.message for issue in [*result.report.errors, *result.report.warnings])
