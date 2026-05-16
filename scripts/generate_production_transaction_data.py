"""CLI script for Production/MES v1 transaction/execution data generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.modules.production.transaction_generator import (
    ProductionTransactionGenerator,
    format_production_transaction_generation_report,
)


def main() -> int:
    """Generate Production/MES v1 transaction/execution CSV files."""

    parser = argparse.ArgumentParser(description="Generate Production/MES v1 transaction data CSV files.")
    parser.add_argument("--metadata", required=True, help="Path to production_v1 metadata XLSX file.")
    parser.add_argument("--plan", required=True, help="Path to production_v1 LLM generation plan JSON.")
    parser.add_argument("--master-data", required=True, help="Folder containing seven Production master/setup CSV files.")
    parser.add_argument("--upstream-data", required=True, help="Procurement v2 final_data folder with inventory and traceability CSVs.")
    parser.add_argument("--output", required=True, help="Output folder for generated transaction CSV files.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic random seed.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    generator = ProductionTransactionGenerator()
    master = generator.load_master_data(args.master_data)
    upstream = generator.load_upstream_data(args.upstream_data, master)
    dataframes, report = generator.generate_transaction_data(
        metadata_result.schema,
        plan_result.plan,
        master,
        upstream,
        seed=args.seed,
    )
    if report.is_valid:
        generator.export_transaction_data(dataframes, args.output)

    print(format_production_transaction_generation_report(dataframes, report, args.output))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
