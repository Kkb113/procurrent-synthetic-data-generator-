"""Generate an LLM generation plan JSON using Azure OpenAI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.erd.erd_validator import validate_erd_relationships
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.azure_openai_client import (
    AzureOpenAIClient,
    AzureOpenAIConfig,
    AzureOpenAIConfigError,
)
from procurement_data_generator.core.llm.plan_loader import validate_llm_plan_data
from procurement_data_generator.core.llm.plan_normalizer import normalize_column_generation_dependencies
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.llm.prompt_builder import build_llm_planning_prompt
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.role_validator import validate_procurement_roles


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and validate an LLM plan with Azure OpenAI.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--erd", required=True, help="Path to Mermaid ERD file.")
    parser.add_argument("--scenario", required=True, help="Path to business scenario text file.")
    parser.add_argument("--output", required=True, help="Path for extracted plan JSON.")
    parser.add_argument("--raw-output", required=True, help="Path for raw Azure OpenAI response text.")
    parser.add_argument("--prompt-output", help="Optional path for the planning prompt text.")
    parser.add_argument("--env", help="Optional .env file path.")
    parser.add_argument("--model-version", default="v2", choices=["v2"], help="Procurement model version for role validation and prompt guidance. Procurement v2 is the only active Procurement model.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print("Metadata validation failed.")
        _print_report_errors(metadata_result.report)
        return 1
    schema = metadata_result.schema

    role_result = validate_procurement_roles(schema, model_version=args.model_version)
    if not role_result.report.is_valid:
        print("Procurement role validation failed.")
        _print_report_errors(role_result.report)
        return 1

    relationships = parse_mermaid_erd_file(args.erd)
    erd_result = validate_erd_relationships(schema, relationships)
    if not erd_result.report.is_valid:
        print("ERD validation failed.")
        _print_report_errors(erd_result.report)
        return 1

    scenario = Path(args.scenario).read_text(encoding="utf-8")
    prompt = build_llm_planning_prompt(schema, relationships, scenario, model_version=args.model_version)
    if args.prompt_output:
        _write_text(args.prompt_output, prompt)

    try:
        config = AzureOpenAIConfig.from_env(args.env)
    except AzureOpenAIConfigError as exc:
        print("Azure OpenAI configuration missing.")
        print(f"Missing: {', '.join(exc.missing)}")
        print("Status: failed")
        return 1

    response = AzureOpenAIClient(config).generate_plan(prompt)
    _write_text(args.raw_output, response.raw_text)

    if response.status != "passed" or response.parsed_json is None:
        _write_json(Path(args.raw_output).with_suffix(".report.json"), response.to_dict())
        print("Azure OpenAI plan generation failed.")
        print(f"Provider: {response.provider}")
        print(f"Deployment: {response.deployment}")
        print(f"Raw response: {args.raw_output}")
        print(f"Error: {response.error_message}")
        print("Status: failed")
        return 1

    _write_text(args.output, response.extracted_json_text or json.dumps(response.parsed_json, indent=2))
    _write_json(Path(args.output).with_suffix(".llm_response_report.json"), response.to_dict())

    plan_shape_result = validate_llm_plan_data(response.parsed_json)
    shape_status = "passed" if plan_shape_result.report.is_valid and plan_shape_result.plan is not None else "failed"
    if plan_shape_result.plan is None:
        print("Azure OpenAI plan generation completed.")
        print(f"Provider: {response.provider}")
        print(f"Deployment: {response.deployment}")
        print(f"Raw response: {args.raw_output}")
        print(f"Plan JSON: {args.output}")
        print(f"JSON shape validation: {shape_status}")
        _print_report_errors(plan_shape_result.report)
        print("Status: failed")
        return 1

    normalization_result = normalize_column_generation_dependencies(plan_shape_result.plan, schema)
    semantic_plan = normalization_result.plan
    normalized_path = None
    if normalization_result.warnings:
        normalized_path = _normalized_plan_path(args.output)
        _write_json(normalized_path, semantic_plan.model_dump(mode="json"))

    semantic_result = validate_generation_plan(semantic_plan, schema, relationships, model_version=args.model_version)
    semantic_status = "passed" if semantic_result.report.is_valid else "failed"

    print("Azure OpenAI plan generation completed.")
    print(f"Provider: {response.provider}")
    print(f"Deployment: {response.deployment}")
    print(f"Raw response: {args.raw_output}")
    print(f"Plan JSON: {args.output}")
    if normalized_path:
        print(f"Normalized plan JSON: {normalized_path}")
    print(f"JSON shape validation: {shape_status}")
    if normalization_result.warnings:
        print(f"Plan normalization removed {len(normalization_result.warnings)} invalid depends_on_columns references.")
    print(f"Semantic plan validation: {semantic_status}")
    print(f"Status: {'passed' if semantic_result.report.is_valid else 'failed'}")
    if semantic_result.report.warnings:
        print(f"Semantic warnings: {len(semantic_result.report.warnings)}")
    if semantic_result.report.errors:
        _print_report_errors(semantic_result.report)
        return 1
    return 0


def _write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _normalized_plan_path(path: str | Path) -> Path:
    output = Path(path)
    return output.with_name(f"{output.stem}_normalized{output.suffix}")


def _print_report_errors(report) -> None:
    for index, issue in enumerate(report.errors, start=1):
        print(f"{index}. {issue.message}")
        print(f"   Suggested fix: {issue.suggested_fix}")


if __name__ == "__main__":
    raise SystemExit(main())
