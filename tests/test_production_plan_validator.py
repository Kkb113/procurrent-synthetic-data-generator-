from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


ROOT = Path(__file__).resolve().parents[1]
PROD_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PROD_ERD = ROOT / "input" / "production_v1_erd.mmd"
PROD_VALID_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
PROD_INVALID_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_invalid.json"
PROC_V2_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROC_V2_ERD = ROOT / "input" / "procurement_v2_erd.mmd"
PROC_V2_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"


def test_valid_production_v1_plan_passes() -> None:
    result = _validate_production(_valid_plan())

    assert result.report.is_valid
    assert len(result.report.errors) == 0


def test_invalid_production_v1_sample_plan_fails_contract_or_semantics() -> None:
    load_result = load_llm_plan_json(PROD_INVALID_PLAN)
    if load_result.plan is None:
        assert not load_result.report.is_valid
        return

    result = _validate_production(load_result.plan)
    assert not result.report.is_valid


def test_missing_required_production_table_fails() -> None:
    data = _valid_plan_data()
    data["generation_order"].remove("ProductionCostSummary")
    data["table_role_mapping"] = [
        mapping for mapping in data["table_role_mapping"] if mapping["table_name"] != "ProductionCostSummary"
    ]

    result = _validate_production_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "ProductionCostSummary")


def test_wrong_module_domain_fails() -> None:
    data = _valid_plan_data()
    data["module"] = "procurement"

    result = _validate_production_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "Plan module must be production")


def test_wrong_model_version_fails() -> None:
    result = _validate_with_model_version(_valid_plan(), "v2")

    assert not result.report.is_valid
    assert _has_error(result, "Plan module must be procurement")


def test_date_range_outside_2025_fails() -> None:
    data = _valid_plan_data()
    data["assumptions"].append("Production orders may continue into 2026.")

    result = _validate_production_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "outside the 2025-only scope")


def test_unexpected_out_of_scope_mes_table_fails() -> None:
    data = _valid_plan_data()
    data["generation_order"].append("OEEEvent")

    result = _validate_production_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "out-of-scope MES concept")


def test_invalid_production_lifecycle_order_fails() -> None:
    data = _valid_plan_data()
    order = data["generation_order"]
    line_index = order.index("ProductionOrderLine")
    requirement_index = order.index("ProductionMaterialRequirement")
    order[line_index], order[requirement_index] = order[requirement_index], order[line_index]

    result = _validate_production_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "corrected lifecycle order")


def test_procurement_v2_plan_still_passes() -> None:
    load_result = load_llm_plan_json(PROC_V2_PLAN)
    assert load_result.report.is_valid
    assert load_result.plan is not None
    schema_result = load_metadata_schema(PROC_V2_METADATA)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None

    result = validate_generation_plan(
        load_result.plan,
        schema_result.schema,
        parse_mermaid_erd_file(PROC_V2_ERD),
        model_version="v2",
    )

    assert result.report.is_valid


def _valid_plan() -> LLMGenerationPlan:
    load_result = load_llm_plan_json(PROD_VALID_PLAN)
    assert load_result.report.is_valid
    assert load_result.plan is not None
    return load_result.plan


def _valid_plan_data() -> dict[str, object]:
    return deepcopy(json.loads(PROD_VALID_PLAN.read_text(encoding="utf-8")))


def _validate_production_data(data: dict[str, object]):
    return _validate_production(LLMGenerationPlan.model_validate(data))


def _validate_production(plan: LLMGenerationPlan):
    return _validate_with_model_version(plan, "production_v1")


def _validate_with_model_version(plan: LLMGenerationPlan, model_version: str):
    schema_result = load_metadata_schema(PROD_METADATA)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None
    return validate_generation_plan(
        plan,
        schema_result.schema,
        parse_mermaid_erd_file(PROD_ERD),
        model_version=model_version,
    )


def _has_error(result, text: str) -> bool:
    return any(text in issue.message for issue in result.report.errors)
