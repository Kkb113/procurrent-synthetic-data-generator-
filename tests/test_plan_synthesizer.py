from __future__ import annotations

from pathlib import Path

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.industry_scenario_contract import IndustryScenarioPlan
from procurement_data_generator.core.llm.plan_synthesizer import PlanSynthesizer
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_METADATA = PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_ERD = PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"
PRODUCTION_METADATA = PROJECT_ROOT / "input" / "production_v1_metadata.xlsx"
PRODUCTION_ERD = PROJECT_ROOT / "input" / "production_v1_erd.mmd"


def _scenario() -> IndustryScenarioPlan:
    return IndustryScenarioPlan.model_validate(
        {
            "industry_id": "pharma",
            "industry_name": "Pharma Manufacturing",
            "business_summary": "Sterile medicine manufacturing with hospitals and distributors.",
            "supported_domains": ["procurement", "production", "sales"],
            "procurement": {
                "supplier_types": ["API supplier", "sterile packaging supplier"],
                "component_categories": ["active ingredients", "excipients", "sterile packaging"],
            },
            "production": {"product_families": ["injectables", "tablets"]},
            "sales": {"customer_types": ["hospital", "pharmacy distributor"]},
            "shared": {"geography_terms": ["USA"], "currency": "USD"},
        }
    )


def test_plan_synthesizer_builds_valid_procurement_plan_from_metadata() -> None:
    schema = load_metadata_schema(PROCUREMENT_METADATA).schema
    relationships = parse_mermaid_erd_file(PROCUREMENT_ERD)

    plan = PlanSynthesizer().synthesize(schema, relationships, _scenario(), model_version="v2")
    validation = validate_generation_plan(plan, schema, relationships, model_version="v2")

    assert validation.report.is_valid
    assert plan.module == "procurement"
    assert len(plan.generation_order) == len(schema.tables)
    assert {row.table_name: row.target_rows for row in plan.row_count_plan} == {
        table.table_name: table.target_rows for table in schema.ordered_tables
    }


def test_plan_synthesizer_does_not_use_llm_table_names() -> None:
    schema = load_metadata_schema(PROCUREMENT_METADATA).schema
    relationships = parse_mermaid_erd_file(PROCUREMENT_ERD)
    scenario = IndustryScenarioPlan.model_validate(
        {
            "industry_id": "bad_tables",
            "industry_name": "Bad Table Names",
            "business_summary": "Scenario mentions HallucinatedSalesTable and FakeInventoryFact.",
            "supported_domains": ["procurement", "production", "sales"],
        }
    )

    plan = PlanSynthesizer().synthesize(schema, relationships, scenario, model_version="v2")

    assert "HallucinatedSalesTable" not in plan.generation_order
    assert "FakeInventoryFact" not in plan.generation_order
    assert set(plan.generation_order) == set(schema.tables)


def test_plan_synthesizer_builds_valid_production_plan() -> None:
    schema = load_metadata_schema(PRODUCTION_METADATA).schema
    relationships = parse_mermaid_erd_file(PRODUCTION_ERD)

    plan = PlanSynthesizer().synthesize(schema, relationships, _scenario(), model_version="production_v1")
    validation = validate_generation_plan(plan, schema, relationships, model_version="production_v1")

    assert validation.report.is_valid
    assert plan.module == "production"
    assert len(plan.generation_order) == len(schema.tables)
