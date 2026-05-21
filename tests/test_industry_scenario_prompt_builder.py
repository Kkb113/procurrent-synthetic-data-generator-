from __future__ import annotations

from pathlib import Path

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.industry_scenario_prompt_builder import build_industry_scenario_prompt
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"


def test_industry_scenario_prompt_limits_llm_to_scenario_hints() -> None:
    schema = load_metadata_schema(METADATA).schema
    relationships = parse_mermaid_erd_file(ERD)

    prompt = build_industry_scenario_prompt(
        schema,
        relationships,
        "Food manufacturing for frozen meals and retail distributors.",
    )

    assert "Food manufacturing for frozen meals" in prompt
    assert "You are not generating data rows." in prompt
    assert "You are not generating an executable plan." in prompt
    assert "You are not generating formulas." in prompt
    assert "The result must support Procurement, Production, and Sales." in prompt
    assert "Do not invent table names or column names." in prompt
    assert "row-level" not in prompt.lower()
