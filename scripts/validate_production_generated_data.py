"""CLI script for Production/MES v1 data quality validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.modules.production.data_validator import (
    validate_production_generated_data,
    write_production_quality_reports,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated Production/MES v1 data.")
    parser.add_argument("--metadata", required=True, help="Path to production_v1 metadata XLSX file.")
    parser.add_argument("--plan", required=True, help="Path to production_v1 plan JSON.")
    parser.add_argument("--master-data", required=True, help="Folder containing Production master CSV files.")
    parser.add_argument("--transaction-data", required=True, help="Folder containing Production transaction CSV files.")
    parser.add_argument("--upstream-data", required=True, help="Procurement v2 final_data folder.")
    parser.add_argument("--output", required=True, help="Output folder for validation reports.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    result = validate_production_generated_data(
        metadata_result.schema,
        args.master_data,
        args.transaction_data,
        args.upstream_data,
    )
    json_path, md_path = write_production_quality_reports(result, args.output)
    print("Production validation completed.")
    print(f"Status: {result.status}")
    print(f"Errors: {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
