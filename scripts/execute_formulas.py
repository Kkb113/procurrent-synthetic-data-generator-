"""CLI script for Phase 10 safe formula execution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.formulas.formula_engine import SafeFormulaEngine, format_formula_execution_report
from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute safe structured formula rules against generated CSV files.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--plan", required=True, help="Path to LLM generation plan JSON containing formula_rules.")
    parser.add_argument("--input-folder", required=True, help="Folder containing generated CSV files.")
    parser.add_argument("--output-folder", required=True, help="Folder to write updated CSV files.")
    parser.add_argument("--strict", action="store_true", help="Stop after the first failed formula rule.")
    parser.add_argument("--model-version", default="v2", choices=["v2"], help="Procurement model version. Procurement v2 is the only active Procurement model.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    input_folder = Path(args.input_folder)
    dataframes, missing = _load_required_csvs(input_folder, plan_result.plan)
    if missing:
        print("Transaction data folder not found or required CSV files missing.")
        print("Missing CSV files: " + ", ".join(missing))
        print("Run Phase 9 generation first:")
        print(
            "python scripts/generate_transaction_data.py --metadata input/procurement_v2_metadata.xlsx "
            "--plan input/sample_generation_plan_v2_valid.json --erd input/procurement_v2_erd.mmd "
            "--output output/transaction_data --seed 42"
        )
        return 1

    engine = SafeFormulaEngine()
    updated, report = engine.execute_formulas(dataframes, plan_result.plan, metadata_result.schema, strict=args.strict)
    output_folder = Path(args.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    for table_name, dataframe in updated.items():
        dataframe.to_csv(output_folder / f"{table_name}.csv", index=False)

    print(format_formula_execution_report(report, str(output_folder), model_version=args.model_version))
    return 0 if report.status in {"passed", "passed_with_warnings"} else 1


def _load_required_csvs(input_folder: Path, plan) -> tuple[dict[str, pd.DataFrame], list[str]]:
    required_tables = {
        rule.target_table for rule in plan.formula_rules
    } | {
        rule.source_table for rule in plan.formula_rules if rule.source_table
    }
    if not input_folder.exists():
        return {}, [f"{table}.csv" for table in sorted(required_tables)]

    dataframes: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for table_name in sorted(required_tables):
        path = input_folder / f"{table_name}.csv"
        if not path.exists():
            missing.append(path.name)
            continue
        dataframes[table_name] = pd.read_csv(path)
    return dataframes, missing


if __name__ == "__main__":
    raise SystemExit(main())
