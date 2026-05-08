"""CLI script for Phase 11 final generated data validation/reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.core.validation.reconciler import ProcurementDataQualityEngine, format_data_quality_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and reconcile generated procurement CSV data.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--data-folder", action="append", required=True, help="Folder containing generated CSV files. May be repeated; later folders override earlier tables.")
    parser.add_argument("--plan", required=False, help="Optional LLM generation/formula plan JSON.")
    parser.add_argument("--report-folder", default="output", help="Folder to write data_quality_report files.")
    parser.add_argument("--model-version", choices=["v1", "v2"], default="v1", help="Procurement model version for validation/reconciliation.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    plan = None
    if args.plan:
        plan_result = load_llm_plan_json(args.plan)
        if not plan_result.report.is_valid:
            print(format_llm_plan_validation_result(plan_result))
            return 1
        plan = plan_result.plan

    dataframes = _load_dataframes([Path(folder) for folder in args.data_folder])
    engine = ProcurementDataQualityEngine()
    report = engine.validate_and_reconcile(dataframes, metadata_result.schema, plan, model_version=args.model_version)

    report_folder = Path(args.report_folder)
    report_folder.mkdir(parents=True, exist_ok=True)
    json_path = report_folder / "data_quality_report.json"
    markdown_path = report_folder / "data_quality_report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report, args.model_version), encoding="utf-8")

    print(format_data_quality_report(report, str(json_path), str(markdown_path), model_version=args.model_version))
    return 0 if report.overall_status in {"passed", "passed_with_warnings"} else 1


def _load_dataframes(folders: list[Path]) -> dict[str, pd.DataFrame]:
    dataframes: dict[str, pd.DataFrame] = {}
    for folder in folders:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.csv")):
            dataframes[path.stem] = pd.read_csv(path)
    return dataframes


def _markdown_report(report, model_version: str) -> str:
    lines = [
        "# Data Quality Report",
        "",
        f"- Model version: {model_version}",
        f"- Overall status: {report.overall_status}",
        f"- Checks run: {report.checks_run}",
        f"- Checks passed: {report.checks_passed}",
        f"- Checks failed: {report.checks_failed}",
        f"- Errors: {report.error_count}",
        f"- Warnings: {report.warning_count}",
        "",
        "## Table Summaries",
        "",
        "| Table | Rows | Target | Errors | Warnings |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for summary in report.table_summaries.values():
        lines.append(f"| {summary.table_name} | {summary.row_count} | {summary.target_rows} | {summary.errors} | {summary.warnings} |")
    lines.extend(["", "## Issues", ""])
    if not report.issues:
        lines.append("No issues found.")
    else:
        for issue in report.issues:
            lines.append(f"- **{issue.level.upper()}** `{issue.check_type}` {issue.table_name or ''}.{issue.column_name or ''}: {issue.message}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
