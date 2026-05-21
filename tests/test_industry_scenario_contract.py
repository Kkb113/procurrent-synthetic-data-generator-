from __future__ import annotations

import pytest
from pydantic import ValidationError

from procurement_data_generator.core.llm.industry_scenario_contract import (
    IndustryScenarioPlan,
    fallback_industry_scenario_plan,
)


def _valid_payload() -> dict:
    return {
        "industry_id": "EV Manufacturing",
        "industry_name": "EV Manufacturing",
        "business_summary": "Electric vehicle component manufacturing.",
        "supported_domains": ["procurement", "production", "sales"],
        "procurement": {"supplier_types": ["battery supplier", "motor supplier"]},
        "production": {"product_families": ["battery packs", "drive units"]},
        "sales": {"customer_types": ["OEM", "fleet operator"]},
        "shared": {"geography_terms": ["USA"], "currency": "USD"},
    }


def test_industry_scenario_plan_valid_payload_passes() -> None:
    plan = IndustryScenarioPlan.model_validate(_valid_payload())

    assert plan.industry_id == "ev_manufacturing"
    assert plan.industry_name == "EV Manufacturing"
    assert set(plan.supported_domains) == {"procurement", "production", "sales"}


def test_industry_scenario_plan_optional_fields_use_defaults() -> None:
    payload = {
        "industry_id": "food",
        "industry_name": "Food Manufacturing",
        "business_summary": "Packaged food manufacturing.",
    }

    plan = IndustryScenarioPlan.model_validate(payload)

    assert plan.supported_domains == ["procurement", "production", "sales"]
    assert plan.row_volume_intent == "standard"
    assert plan.shared.currency == "USD"


def test_industry_scenario_plan_rejects_missing_lifecycle_domain() -> None:
    payload = _valid_payload()
    payload["supported_domains"] = ["procurement", "sales"]

    with pytest.raises(ValidationError):
        IndustryScenarioPlan.model_validate(payload)


def test_industry_scenario_plan_extra_content_is_ignored_safely() -> None:
    payload = _valid_payload()
    payload["table_mappings"] = {"HallucinatedTable": "not allowed to drive execution"}

    plan = IndustryScenarioPlan.model_validate(payload)

    assert not hasattr(plan, "table_mappings")


def test_fallback_industry_scenario_plan_is_valid_and_warns() -> None:
    plan = fallback_industry_scenario_plan("invalid json")

    assert plan.industry_id == "general_manufacturing"
    assert set(plan.supported_domains) == {"procurement", "production", "sales"}
    assert any("Fallback" in warning for warning in plan.warnings)
