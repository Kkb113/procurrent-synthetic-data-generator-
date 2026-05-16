"""CLI script for Phase 9 procurement transaction data generation."""

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
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.role_validator import (
    format_procurement_role_validation_result,
    validate_procurement_roles,
)
from procurement_data_generator.modules.procurement.transaction_generator import (
    ProcurementTransactionGenerator,
    format_transaction_generation_report,
)


def main() -> int:
    """Generate master data first, then procurement transaction data."""

    parser = argparse.ArgumentParser(description="Generate procurement transaction data CSV files.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--plan", required=True, help="Path to LLM generation plan JSON.")
    parser.add_argument("--output", required=True, help="Output folder for transaction CSV files.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic random seed.")
    parser.add_argument("--erd", required=False, help="Optional Mermaid ERD file for validation.")
    parser.add_argument("--model-version", default="v2", choices=["v2"], help="Procurement model version. Procurement v2 is the only active Procurement model.")
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

    master_generator = ProcurementMasterDataGenerator()
    master_data, master_report = master_generator.generate_master_data(
        metadata_result.schema,
        plan_result.plan,
        seed=args.seed,
        model_version=args.model_version,
    )
    if not master_report.is_valid:
        from procurement_data_generator.modules.procurement.master_generator import format_master_generation_report

        print(format_master_generation_report(master_data, master_report))
        return 1

    transaction_generator = ProcurementTransactionGenerator()
    transaction_data, transaction_report = transaction_generator.generate_transaction_data(
        metadata_result.schema,
        plan_result.plan,
        master_data,
        seed=args.seed,
        model_version=args.model_version,
    )
    if transaction_report.is_valid:
        transaction_generator.export_transaction_data(transaction_data, args.output)

    print(format_transaction_generation_report(transaction_data, transaction_report, args.output, model_version=args.model_version))
    return 0 if transaction_report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
