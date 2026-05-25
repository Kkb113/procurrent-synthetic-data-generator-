"""Deterministic local scenario planning client for no-Azure product runs."""

from __future__ import annotations

import json

from procurement_data_generator.core.llm.industry_scenario_contract import IndustryScenarioPlan
from procurement_data_generator.core.llm.llm_client_base import LLMClientBase, LLMResponse


class DeterministicIndustryScenarioClient(LLMClientBase):
    """Return local IndustryScenarioPlan JSON without making a network call."""

    uses_azure_openai = False

    def generate_plan(self, prompt: str) -> LLMResponse:
        plan = _scenario_from_prompt(prompt)
        payload = plan.model_dump(mode="json")
        text = json.dumps(payload, indent=2)
        response = LLMResponse(
            provider="Deterministic local scenario planner",
            deployment="local",
            status="passed",
            raw_text=text,
            extracted_json_text=text,
            parsed_json=payload,
        )
        response.complete()
        return response


def _scenario_from_prompt(prompt: str) -> IndustryScenarioPlan:
    text = prompt.lower()
    if any(term in text for term in ["electronics", "pcb", "iot", "sensor", "microcontroller", "smt"]):
        return IndustryScenarioPlan(
            industry_id="electronics_manufacturing",
            industry_name="Electronics Manufacturing",
            business_summary="Electronics manufacturing lifecycle for PCB assemblies, IoT devices, control boards, and sensor modules.",
            supported_domains=["procurement", "production", "sales"],
            row_volume_intent="analytics",
            procurement={
                "supplier_types": ["PCB Supplier", "Semiconductor Supplier", "Connector Supplier", "Electronics Enclosure Supplier"],
                "component_categories": ["PCB", "Semiconductors", "Passive Components", "Connectors", "Sensors", "Enclosures"],
                "raw_material_terms": ["printed circuit board", "microcontroller", "resistor", "capacitor", "connector", "sensor", "chip", "enclosure"],
                "purchasing_patterns": ["planned electronics replenishment", "quality-inspected component receipts"],
                "supplier_risk_factors": ["component shortage", "lead time risk", "quality hold"],
                "inspection_or_quality_hints": ["incoming electronics inspection", "component traceability", "ESD-safe handling"],
            },
            production={
                "product_families": ["IoT Gateway", "Control Board", "Sensor Module", "Electronics Assembly"],
                "production_process_terms": ["SMT assembly", "soldering", "firmware flashing", "functional testing", "burn-in testing"],
                "work_center_terms": ["SMT Line", "Soldering Cell", "Firmware Flash Station", "Functional Test Bench", "Burn-in Rack"],
                "routing_patterns": ["SMT placement", "reflow soldering", "firmware flashing", "functional testing", "final assembly"],
                "scrap_or_yield_hints": ["solder defect", "failed functional test", "firmware rework"],
                "finished_good_terms": ["IoT gateway", "control board", "sensor module"],
            },
            sales={
                "customer_types": ["OEM", "Electronics Distributor", "Industrial Customer", "System Integrator"],
                "customer_industries": ["Industrial Automation", "Electronics Distribution", "OEM Manufacturing"],
                "sales_channels": ["OEM contract", "electronics distributor", "industrial sales", "system integrator channel"],
                "demand_patterns": ["project-based demand", "quarterly OEM release", "distributor replenishment"],
                "payment_terms": ["Net30", "Net45", "Net60"],
                "return_reasons": ["failed functional test", "field failure", "shipping damage"],
                "region_terms": ["North America", "Asia Pacific", "Europe"],
            },
            shared={
                "geography_terms": ["USA", "TAIWAN", "MALAYSIA", "MEXICO", "VIETNAM"],
                "currency": "USD",
                "seasonality": ["quarterly electronics demand cycles"],
                "naming_style": "realistic electronics manufacturing business names",
                "regulatory_or_quality_terms": ["RoHS", "ESD control", "traceability", "functional test"],
            },
            assumptions=["No Azure OpenAI was requested; Python used deterministic local electronics scenario hints."],
            warnings=[],
        )
    from procurement_data_generator.core.llm.industry_scenario_contract import fallback_industry_scenario_plan

    return fallback_industry_scenario_plan("No Azure OpenAI was requested; using deterministic local scenario hints.")
