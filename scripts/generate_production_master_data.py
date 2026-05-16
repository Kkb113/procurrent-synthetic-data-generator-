"""CLI script for Production/MES v1 master/setup data generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.core.llm.plan_validator import format_plan_validation_result, validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.modules.production.master_generator import (
    ProductionMasterDataGenerator,
    format_production_master_generation_report,
)
from procurement_data_generator.modules.production.role_validator import (
    format_production_role_validation_result,
    validate_production_roles,
)
from procurement_data_generator.modules.shared.industry_profiles import (
    DEFAULT_INDUSTRY_PROFILE_ID,
    get_supported_industry_profile_ids,
    load_industry_profile_from_json,
)


def main() -> int:
    """Validate inputs, generate Production master/setup CSV files, and exit with status."""

    parser = argparse.ArgumentParser(description="Generate Production/MES v1 master/setup data CSV files.")
    parser.add_argument("--metadata", required=True, help="Path to production_v1 metadata XLSX file.")
    parser.add_argument("--plan", required=True, help="Path to production_v1 LLM generation plan JSON.")
    parser.add_argument("--output", required=True, help="Output folder for generated CSV files.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic random seed.")
    parser.add_argument("--upstream-data", required=False, help="Optional Procurement data folder containing ComponentMaster, Plant, and Warehouse CSVs.")
    parser.add_argument("--erd", default="input/production_v1_erd.mmd", help="Optional Production v1 Mermaid ERD for semantic plan validation.")
    parser.add_argument("--industry-profile", default=DEFAULT_INDUSTRY_PROFILE_ID, choices=get_supported_industry_profile_ids(), help="Internal static industry profile for catalog content.")
    parser.add_argument("--industry-profile-file", help="Optional generated industry profile JSON file. Overrides --industry-profile.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    role_result = validate_production_roles(metadata_result.schema)
    if not role_result.report.is_valid:
        print(format_production_role_validation_result(role_result))
        return 1

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    erd_path = Path(args.erd)
    if erd_path.exists():
        validation_result = validate_generation_plan(
            plan_result.plan,
            metadata_result.schema,
            parse_mermaid_erd_file(erd_path),
            model_version="production_v1",
        )
        if not validation_result.report.is_valid:
            print(format_plan_validation_result(validation_result))
            return 1

    industry_profile = load_industry_profile_from_json(args.industry_profile_file) if args.industry_profile_file else None
    generator = ProductionMasterDataGenerator(industry_profile=industry_profile, profile_id=args.industry_profile)
    dataframes, report = generator.generate_master_data(
        metadata_result.schema,
        plan_result.plan,
        seed=args.seed,
        upstream_data_folder=args.upstream_data,
    )
    if report.is_valid:
        generator.export_master_data(dataframes, args.output)

    print(format_production_master_generation_report(dataframes, report, args.output))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
