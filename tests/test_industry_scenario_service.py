from __future__ import annotations

import json

from procurement_data_generator.core.llm.industry_scenario_service import IndustryScenarioPlanningService
from procurement_data_generator.core.llm.llm_client_base import LLMResponse


VALID_SCENARIO = {
    "industry_id": "ev_manufacturing",
    "industry_name": "EV Manufacturing",
    "business_summary": "EV component manufacturing with OEM sales.",
    "supported_domains": ["procurement", "production", "sales"],
    "procurement": {"supplier_types": ["battery supplier"]},
    "production": {"product_families": ["battery packs"]},
    "sales": {"customer_types": ["OEM"]},
}


class FakeLLMClient:
    def __init__(self, payloads: list[LLMResponse]) -> None:
        self.payloads = payloads
        self.prompts: list[str] = []

    def generate_plan(self, prompt: str) -> LLMResponse:
        self.prompts.append(prompt)
        response = self.payloads.pop(0)
        response.complete()
        return response


def _response(raw_text: str, parsed_json: dict | None = None, status: str = "passed") -> LLMResponse:
    return LLMResponse(
        provider="Azure OpenAI",
        deployment="mock",
        status=status,
        raw_text=raw_text,
        extracted_json_text=raw_text,
        parsed_json=parsed_json,
    )


def test_industry_scenario_service_repairs_invalid_json_then_validates() -> None:
    valid_raw = json.dumps(VALID_SCENARIO)
    client = FakeLLMClient(
        [
            _response("{not json"),
            _response(valid_raw, parsed_json=VALID_SCENARIO),
        ]
    )

    result = IndustryScenarioPlanningService(lambda: client, max_repair_attempts=1).generate("original prompt")

    assert result.plan.industry_id == "ev_manufacturing"
    assert result.repair_needed
    assert not result.fallback_used
    assert result.retry_attempts == 1
    assert "Repair the previous response" in client.prompts[1]


def test_industry_scenario_service_falls_back_after_invalid_repair() -> None:
    client = FakeLLMClient([_response("{not json"), _response('{"industry_id": ""}')])

    result = IndustryScenarioPlanningService(lambda: client, max_repair_attempts=1).generate("original prompt")
    report = result.report()

    assert result.plan.industry_id == "general_manufacturing"
    assert result.fallback_used
    assert not result.validation_passed
    assert report["fallback_used"] is True
    assert report["final_industry_name"] == "General Manufacturing"


def test_industry_scenario_service_falls_back_when_client_call_raises() -> None:
    class FailingClient:
        def generate_plan(self, prompt: str) -> LLMResponse:
            raise RuntimeError("network unavailable")

    result = IndustryScenarioPlanningService(lambda: FailingClient(), max_repair_attempts=0).generate("prompt")

    assert result.fallback_used
    assert result.plan.industry_id == "general_manufacturing"
    assert "network unavailable" in result.validation_errors[0]
