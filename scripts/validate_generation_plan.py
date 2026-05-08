"""CLI script for semantic validation of an LLM generation plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.erd.erd_validator import format_erd_validation_result, validate_erd_relationships
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.core.llm.plan_validator import (
    format_plan_validation_result,
    validate_generation_plan,
)
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.modules.procurement.role_validator import (
    format_procurement_role_validation_result,
    validate_procurement_roles,
)


def main() -> int:
    """Run Phase 1-4 checks, then Phase 6 semantic plan validation."""

    parser = argparse.ArgumentParser(description="Validate LLM generation plan against metadata and ERD.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--erd", required=True, help="Path to Mermaid ERD file.")
    parser.add_argument("--plan", required=True, help="Path to LLM generation plan JSON file.")
    parser.add_argument("--model-version", default="v1", choices=["v1", "v2"], help="Procurement model version for role and semantic validation.")
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
    if not erd_path.exists():
        print(f"ERD file does not exist: {erd_path}")
        return 1
    relationships = parse_mermaid_erd_file(erd_path)
    erd_result = validate_erd_relationships(metadata_result.schema, relationships)
    if not erd_result.report.is_valid:
        print(format_erd_validation_result(erd_result))
        return 1

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    validation_result = validate_generation_plan(plan_result.plan, metadata_result.schema, relationships, model_version=args.model_version)
    print(format_plan_validation_result(validation_result))
    return 0 if validation_result.report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
