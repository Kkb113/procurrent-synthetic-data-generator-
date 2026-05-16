from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.llm.plan_normalizer import (
    get_legacy_module_plan,
    normalize_llm_generation_plan,
)
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PRODUCTION_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
PROCUREMENT_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_ERD = ROOT / "input" / "procurement_v2_erd.mmd"


def test_legacy_procurement_plan_dict_normalizes_to_one_module_envelope() -> None:
    legacy = _load_json(PROCUREMENT_PLAN)

    normalized = normalize_llm_generation_plan(legacy)

    assert normalized.module_set == ["procurement"]
    assert normalized.module_versions == {"procurement": "v2"}
    assert normalized.industry == legacy["domain_profile"]["industry"]
    assert normalized.modules["procurement"]["legacy_plan"]["module"] == "procurement"
    assert normalized.global_assumptions == legacy["assumptions"]


def test_legacy_production_plan_dict_normalizes_to_one_module_envelope() -> None:
    legacy = _load_json(PRODUCTION_PLAN)

    normalized = normalize_llm_generation_plan(legacy)

    assert normalized.module_set == ["production"]
    assert normalized.module_versions == {"production": "v1"}
    assert normalized.modules["production"]["legacy_plan"]["module"] == "production"


def test_legacy_plan_object_normalizes_and_can_extract_legacy_payload() -> None:
    load_result = load_llm_plan_json(PROCUREMENT_PLAN)
    assert load_result.plan is not None

    normalized = normalize_llm_generation_plan(load_result.plan)
    legacy = get_legacy_module_plan(normalized, "procurement")

    assert legacy is not None
    assert legacy.module == "procurement"
    assert legacy.generation_order == load_result.plan.generation_order


def test_normalized_one_module_plan_passes_through_with_default_module_payload() -> None:
    normalized = normalize_llm_generation_plan(
        {
            "plan_id": "quality_plan",
            "module_set": ["quality"],
            "module_versions": {"quality": "v1"},
            "modules": {},
        }
    )

    assert normalized.module_set == ["quality"]
    assert normalized.modules["quality"] == {}


def test_normalized_multi_module_plan_passes_contract_level_validation() -> None:
    normalized = normalize_llm_generation_plan(
        {
            "plan_id": "mes_plan",
            "module_set": ["procurement", "production", "quality"],
            "module_versions": {"procurement": "v2", "production": "v1", "quality": "v1"},
            "modules": {
                "procurement": {"legacy_plan": _load_json(PROCUREMENT_PLAN)},
                "production": {"legacy_plan": _load_json(PRODUCTION_PLAN)},
                "quality": {"rules": []},
            },
            "global_assumptions": ["Single plant scope remains in effect."],
        }
    )

    assert normalized.module_set == ["procurement", "production", "quality"]
    assert normalized.modules["quality"] == {"rules": []}


def test_normalized_plan_rejects_empty_module_set() -> None:
    with pytest.raises(ValueError, match="module_set"):
        normalize_llm_generation_plan({"module_set": [], "modules": {}})


def test_normalized_plan_rejects_duplicate_module_ids() -> None:
    with pytest.raises(ValueError, match="duplicate module ids"):
        normalize_llm_generation_plan({"module_set": ["procurement", " Procurement "], "modules": {}})


def test_unknown_module_is_allowed_at_contract_level() -> None:
    normalized = normalize_llm_generation_plan(
        {
            "module_set": ["maintenance"],
            "module_versions": {"maintenance": "v1"},
            "modules": {"maintenance": {"planning_rules": []}},
        }
    )

    assert normalized.module_set == ["maintenance"]


@pytest.mark.integration
def test_semantic_validator_accepts_normalized_legacy_procurement_plan() -> None:
    schema_result = load_metadata_schema(PROCUREMENT_METADATA)
    assert schema_result.schema is not None
    normalized = normalize_llm_generation_plan(
        {
            "module_set": ["procurement"],
            "module_versions": {"procurement": "v2"},
            "modules": {"procurement": {"legacy_plan": _load_json(PROCUREMENT_PLAN)}},
        }
    )

    result = validate_generation_plan(
        normalized,
        schema_result.schema,
        parse_mermaid_erd_file(PROCUREMENT_ERD),
        model_version="v2",
    )

    assert result.report.is_valid


@pytest.mark.integration
def test_semantic_validator_reports_normalized_plan_without_current_legacy_payload() -> None:
    schema_result = load_metadata_schema(PROCUREMENT_METADATA)
    assert schema_result.schema is not None
    normalized = normalize_llm_generation_plan({"module_set": ["procurement"], "modules": {"procurement": {}}})

    result = validate_generation_plan(
        normalized,
        schema_result.schema,
        parse_mermaid_erd_file(PROCUREMENT_ERD),
        model_version="v2",
    )

    assert not result.report.is_valid
    assert any("legacy procurement payload" in issue.message for issue in result.report.errors)


def _load_json(path: Path) -> dict:
    return deepcopy(json.loads(path.read_text(encoding="utf-8")))
