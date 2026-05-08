"""CLI script for building the LLM planning prompt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.prompt_builder import build_llm_planning_prompt
from procurement_data_generator.core.metadata.metadata_reader import (
    format_validation_report,
    load_metadata_schema,
)
from procurement_data_generator.modules.procurement.role_validator import (
    format_procurement_role_validation_result,
    validate_procurement_roles,
)


def main() -> int:
    """Build and save an LLM planning prompt from metadata, ERD, and scenario."""

    parser = argparse.ArgumentParser(description="Build LLM planning prompt.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--erd", required=True, help="Path to Mermaid ERD file.")
    parser.add_argument("--scenario", required=True, help="Path to business scenario text file.")
    parser.add_argument("--output", required=True, help="Path where the prompt should be saved.")
    parser.add_argument("--model-version", default="v1", choices=["v1", "v2"], help="Procurement model version for role validation and prompt guidance.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    role_result = validate_procurement_roles(metadata_result.schema, model_version=args.model_version)
    if not role_result.report.is_valid:
        print(format_procurement_role_validation_result(role_result))
        return 1

    erd_path = Path(args.erd)
    scenario_path = Path(args.scenario)
    output_path = Path(args.output)

    if not erd_path.exists():
        print(f"ERD file does not exist: {erd_path}")
        return 1
    if not scenario_path.exists():
        print(f"Scenario file does not exist: {scenario_path}")
        return 1

    relationships = parse_mermaid_erd_file(erd_path)
    scenario_text = scenario_path.read_text(encoding="utf-8")
    prompt = build_llm_planning_prompt(
        schema_contract=metadata_result.schema,
        relationships=relationships,
        business_scenario=scenario_text,
        model_version=args.model_version,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")

    print("LLM planning prompt generated successfully.")
    print(f"Tables included: {len(metadata_result.schema.tables)}")
    print(f"Columns included: {sum(len(table.columns) for table in metadata_result.schema.tables.values())}")
    print(f"ERD relationships included: {len(relationships)}")
    print(f"Scenario file: {args.scenario}")
    print(f"Model version: {args.model_version}")
    print(f"Prompt saved to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
