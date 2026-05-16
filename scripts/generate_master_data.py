"""CLI script for Phase 8 procurement master data generation."""

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
from procurement_data_generator.core.llm.plan_validator import format_plan_validation_result, validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import (
    ProcurementMasterDataGenerator,
    format_master_generation_report,
)
from procurement_data_generator.modules.procurement.role_validator import (
    format_procurement_role_validation_result,
    validate_procurement_roles,
)
from procurement_data_generator.modules.shared.industry_profiles import (
    DEFAULT_INDUSTRY_PROFILE_ID,
    get_supported_industry_profile_ids,
    load_industry_profile_from_json,
)


def main() -> int:
    """Validate inputs, generate master tables, and export CSV files."""

    parser = argparse.ArgumentParser(description="Generate procurement master data CSV files.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--plan", required=True, help="Path to validated LLM generation plan JSON.")
    parser.add_argument("--output", required=True, help="Output folder for generated CSV files.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic random seed.")
    parser.add_argument("--erd", required=False, help="Optional Mermaid ERD file for Phase 6 semantic validation.")
    parser.add_argument("--model-version", default="v2", choices=["v2"], help="Procurement model version. Procurement v2 is the only active Procurement model.")
    parser.add_argument("--industry-profile", default=DEFAULT_INDUSTRY_PROFILE_ID, choices=get_supported_industry_profile_ids(), help="Internal static industry profile for catalog content.")
    parser.add_argument("--industry-profile-file", help="Optional generated industry profile JSON file. Overrides --industry-profile.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    role_result = validate_procurement_roles(metadata_result.schema, model_version=args.model_version)
    if not role_result.report.is_valid:
        print(format_procurement_role_validation_result(role_result))
        return 1

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    if args.erd:
        relationships = parse_mermaid_erd_file(args.erd)
        erd_result = validate_erd_relationships(metadata_result.schema, relationships)
        if not erd_result.report.is_valid:
            print(format_erd_validation_result(erd_result))
            return 1
        validation_result = validate_generation_plan(
            plan_result.plan,
            metadata_result.schema,
            relationships,
            model_version=args.model_version,
        )
        if not validation_result.report.is_valid:
            print(format_plan_validation_result(validation_result))
            return 1

    industry_profile = load_industry_profile_from_json(args.industry_profile_file) if args.industry_profile_file else None
    generator = ProcurementMasterDataGenerator(industry_profile=industry_profile, profile_id=args.industry_profile)
    dataframes, report = generator.generate_master_data(
        metadata_result.schema,
        plan_result.plan,
        seed=args.seed,
        model_version=args.model_version,
    )
    if report.is_valid:
        generator.export_master_data(dataframes, args.output)

    print(format_master_generation_report(dataframes, report, args.output, model_version=args.model_version))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
