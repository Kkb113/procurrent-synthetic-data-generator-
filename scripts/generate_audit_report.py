"""CLI script for Phase 13 final audit report generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.audit.audit_report import AuditReportBuilder


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate final procurement data generation audit report.")
    parser.add_argument("--metadata", help="Path to metadata XLSX file.")
    parser.add_argument("--erd", help="Path to Mermaid ERD file.")
    parser.add_argument("--scenario", help="Path to business scenario text file.")
    parser.add_argument("--plan", help="Path to LLM generation plan JSON.")
    parser.add_argument("--data-quality-report", help="Path to Phase 11 data_quality_report.json.")
    parser.add_argument("--sql-load-report", help="Path to Phase 12 sql_load_report.json.")
    parser.add_argument("--formula-report", help="Optional formula execution report JSON.")
    parser.add_argument("--data-folder", action="append", default=[], help="Generated CSV folder. May be repeated; later folders override earlier tables.")
    parser.add_argument("--output", default="output", help="Output folder for audit reports.")
    args = parser.parse_args()

    result = AuditReportBuilder().build_audit_report(
        metadata_path=args.metadata,
        erd_path=args.erd,
        scenario_path=args.scenario,
        llm_plan_path=args.plan,
        data_quality_report_path=args.data_quality_report,
        sql_load_report_path=args.sql_load_report,
        data_folders=args.data_folder,
        formula_report_path=args.formula_report,
        output_folder=args.output,
    )

    report = result.report
    print("Audit report generated.")
    print(f"Final status: {report['final_status']['status']}")
    print(f"Tables generated: {report['generation_summary']['tables_generated']}")
    print(f"Total rows generated: {report['generation_summary']['total_rows_generated']}")
    print(f"Data quality status: {report['data_quality_summary']['overall_status']}")
    print(f"SQL load status: {report['sql_load_summary']['sql_load_status']}")
    print(f"JSON report: {result.json_path}")
    print(f"Markdown report: {result.markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
