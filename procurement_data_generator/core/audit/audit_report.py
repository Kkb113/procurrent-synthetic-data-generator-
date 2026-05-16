"""Final audit report builder for the procurement data generation pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


MASTER_ROLES = {
    "vendor_dimension",
    "material_dimension",
    "supplier_master",
    "supplier_component",
    "component_master",
    "plant_dimension",
    "warehouse_dimension",
}


@dataclass
class AuditReportResult:
    """Generated audit report and output file paths."""

    report: dict[str, Any]
    json_path: Path
    markdown_path: Path


class AuditReportBuilder:
    """Build JSON and Markdown audit reports from existing pipeline artifacts."""

    def build_audit_report(
        self,
        metadata_path: str | None = None,
        erd_path: str | None = None,
        scenario_path: str | None = None,
        llm_plan_path: str | None = None,
        data_quality_report_path: str | None = None,
        sql_load_report_path: str | None = None,
        data_folders: list[str] | None = None,
        formula_report_path: str | None = None,
        output_folder: str = "output",
        model_version: str = "v2",
    ) -> AuditReportResult:
        plan = self.load_json_report(llm_plan_path)
        data_quality = self.load_json_report(data_quality_report_path)
        sql_load = self.load_json_report(sql_load_report_path)
        formula_report = self.load_json_report(formula_report_path)
        row_counts = self.collect_table_row_counts(data_folders or [])
        schema_summary = self._schema_summary(metadata_path, row_counts)
        scenario_preview = self._scenario_preview(scenario_path)
        formula_summary = self.summarize_formula_execution_report(plan, formula_report)
        data_quality_summary = self.summarize_data_quality_report(data_quality)
        sql_summary = self.summarize_sql_load_report(sql_load)
        final_status = self.determine_final_status(data_quality, sql_load, data_quality_report_path)
        assumptions_risks = self._assumptions_and_risks(plan, data_quality_report_path, sql_load_report_path, sql_load)

        report = {
            "report_metadata": {
                "report_generated_at": datetime.now(timezone.utc).isoformat(),
                "tool_name": "Procurement Data Generation Tool",
                "module": "procurement",
                "model_version": model_version,
                "report_version": "1.0",
            },
            "input_summary": {
                "metadata_file": metadata_path,
                "erd_file": erd_path,
                "scenario_file": scenario_path,
                "llm_plan_file": llm_plan_path,
                "data_folders": data_folders or [],
                "quality_report_file": data_quality_report_path,
                "sql_load_report_file": sql_load_report_path,
                "formula_report_file": formula_report_path,
            },
            "business_summary": {
                "scenario_text_preview": scenario_preview,
                "industry": _get(plan, "domain_profile", "industry"),
                "business_context": _get(plan, "domain_profile", "business_context"),
            },
            "schema_summary": schema_summary,
            "generation_summary": self._generation_summary(row_counts, schema_summary),
            "formula_summary": formula_summary,
            "data_quality_summary": data_quality_summary,
            "sql_load_summary": sql_summary,
            "final_status": final_status,
            "assumptions_and_risks": assumptions_risks,
        }

        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        json_path = output_path / "audit_report.json"
        markdown_path = output_path / "audit_report.md"
        self.write_json_report(report, json_path)
        self.write_markdown_report(report, markdown_path)
        return AuditReportResult(report=report, json_path=json_path, markdown_path=markdown_path)

    def load_json_report(self, path: str | None) -> dict[str, Any] | None:
        if not path:
            return None
        report_path = Path(path)
        if not report_path.exists():
            return None
        return json.loads(report_path.read_text(encoding="utf-8"))

    def collect_table_row_counts(self, data_folders: list[str]) -> dict[str, int]:
        row_counts: dict[str, int] = {}
        for folder in data_folders:
            folder_path = Path(folder)
            if not folder_path.exists():
                continue
            for csv_path in sorted(folder_path.glob("*.csv")):
                row_counts[csv_path.stem] = len(pd.read_csv(csv_path))
        return row_counts

    def summarize_data_quality_report(self, report: dict[str, Any] | None) -> dict[str, Any]:
        if report is None:
            return {
                "overall_status": "missing",
                "tables_checked": 0,
                "checks_run": 0,
                "checks_passed": 0,
                "checks_failed": 0,
                "error_count": 0,
                "warning_count": 0,
                "top_errors": [],
                "top_warnings": [],
            }
        issues = report.get("issues", [])
        return {
            "overall_status": report.get("overall_status"),
            "tables_checked": len(report.get("table_summaries", {})),
            "checks_run": report.get("checks_run", 0),
            "checks_passed": report.get("checks_passed", 0),
            "checks_failed": report.get("checks_failed", 0),
            "error_count": report.get("error_count", 0),
            "warning_count": report.get("warning_count", 0),
            "top_errors": [issue for issue in issues if issue.get("level") == "error"][:5],
            "top_warnings": [issue for issue in issues if issue.get("level") == "warning"][:5],
        }

    def summarize_sql_load_report(self, report: dict[str, Any] | None) -> dict[str, Any]:
        if report is None:
            return {
                "sql_load_attempted": False,
                "sql_load_status": "not_attempted",
                "database": None,
                "schema": None,
                "tables_created": 0,
                "tables_loaded": 0,
                "total_rows_inserted": 0,
                "pk_constraints_created": 0,
                "fk_constraints_created": 0,
                "warnings": [],
                "errors": [],
            }
        return {
            "sql_load_attempted": True,
            "sql_load_status": report.get("status"),
            "database": report.get("database"),
            "schema": report.get("schema"),
            "tables_created": len(report.get("tables_created", [])),
            "tables_loaded": len(report.get("tables_loaded", [])),
            "total_rows_inserted": report.get("total_rows_inserted", 0),
            "pk_constraints_created": report.get("pk_constraints_created_count", len(report.get("pk_constraints_created", []))),
            "fk_constraints_created": report.get("fk_constraints_created_count", len(report.get("fk_constraints_created", []))),
            "warnings": report.get("warnings", []),
            "errors": report.get("errors", []),
        }

    def summarize_formula_execution_report(self, plan: dict[str, Any] | None, formula_report: dict[str, Any] | None) -> dict[str, Any]:
        if formula_report:
            return {
                "total_formula_rules": formula_report.get("total_rules", 0),
                "applied_rules": formula_report.get("applied_count", 0),
                "skipped_rules": formula_report.get("skipped_count", 0),
                "failed_rules": formula_report.get("failed_count", 0),
                "formula_status": formula_report.get("status"),
                "warnings": formula_report.get("warnings", []),
                "errors": formula_report.get("errors", []),
            }
        rules = plan.get("formula_rules", []) if plan else []
        return {
            "total_formula_rules": len(rules),
            "applied_rules": None,
            "skipped_rules": None,
            "failed_rules": None,
            "formula_status": "not_reported" if rules else "not_applicable",
            "warnings": [],
            "errors": [],
        }

    def determine_final_status(
        self,
        data_quality_report: dict[str, Any] | None,
        sql_load_report: dict[str, Any] | None,
        data_quality_report_path: str | None,
    ) -> dict[str, Any]:
        blocking_errors: list[str] = []
        non_blocking_warnings: list[str] = []

        if not data_quality_report_path or data_quality_report is None:
            return {
                "status": "incomplete",
                "blocking_errors": ["Data quality report is missing."],
                "non_blocking_warnings": [],
                "ready_for_sql_load": False,
                "ready_for_user_review": True,
            }

        quality_status = data_quality_report.get("overall_status")
        if quality_status == "failed":
            blocking_errors.append("Data quality report failed.")
            status = "failed"
        elif quality_status == "passed_with_warnings":
            non_blocking_warnings.append("Data quality passed with warnings.")
            status = "passed_with_warnings"
        elif quality_status == "passed":
            status = "passed"
        else:
            blocking_errors.append(f"Unknown data quality status: {quality_status}.")
            status = "incomplete"

        if sql_load_report is not None and sql_load_report.get("status") == "failed" and quality_status in {"passed", "passed_with_warnings"}:
            non_blocking_warnings.append("Data generation passed, but SQL load failed. Review SQL load report.")
            status = "passed_with_warnings"

        return {
            "status": status,
            "blocking_errors": blocking_errors,
            "non_blocking_warnings": non_blocking_warnings,
            "ready_for_sql_load": quality_status in {"passed", "passed_with_warnings"},
            "ready_for_user_review": status in {"passed", "passed_with_warnings", "incomplete"},
        }

    def write_json_report(self, report: dict[str, Any], path: Path) -> None:
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def write_markdown_report(self, report: dict[str, Any], path: Path) -> None:
        path.write_text(render_markdown_report(report), encoding="utf-8")

    def _schema_summary(self, metadata_path: str | None, row_counts: dict[str, int]) -> dict[str, Any]:
        if not metadata_path or not Path(metadata_path).exists():
            return {
                "total_tables": len(row_counts),
                "total_columns": None,
                "master_tables": [],
                "transaction_tables": [],
                "table_roles_present": [],
                "tables": [{"table_name": name, "table_role": None, "area": None, "rows": rows} for name, rows in sorted(row_counts.items())],
            }
        result = load_metadata_schema(metadata_path)
        if result.schema is None:
            return {
                "total_tables": len(row_counts),
                "total_columns": None,
                "master_tables": [],
                "transaction_tables": [],
                "table_roles_present": [],
                "tables": [{"table_name": name, "table_role": None, "area": None, "rows": rows} for name, rows in sorted(row_counts.items())],
            }
        tables = []
        master_tables = []
        transaction_tables = []
        roles = []
        for table in result.schema.ordered_tables:
            roles.append(table.table_role)
            entry = {
                "table_name": table.table_name,
                "table_role": table.table_role,
                "area": table.area,
                "rows": row_counts.get(table.table_name, 0),
            }
            tables.append(entry)
            if table.table_role in MASTER_ROLES:
                master_tables.append(table.table_name)
            else:
                transaction_tables.append(table.table_name)
        return {
            "total_tables": len(result.schema.tables),
            "total_columns": sum(len(table.columns) for table in result.schema.tables.values()),
            "master_tables": master_tables,
            "transaction_tables": transaction_tables,
            "table_roles_present": roles,
            "tables": tables,
        }

    def _generation_summary(self, row_counts: dict[str, int], schema_summary: dict[str, Any]) -> dict[str, Any]:
        master_tables = set(schema_summary.get("master_tables", []))
        transaction_tables = set(schema_summary.get("transaction_tables", []))
        return {
            "tables_generated": len(row_counts),
            "total_rows_generated": sum(row_counts.values()),
            "row_counts_by_table": dict(sorted(row_counts.items())),
            "master_row_count": sum(rows for table, rows in row_counts.items() if table in master_tables),
            "transaction_row_count": sum(rows for table, rows in row_counts.items() if table in transaction_tables),
        }

    def _scenario_preview(self, scenario_path: str | None, limit: int = 500) -> str | None:
        if not scenario_path or not Path(scenario_path).exists():
            return None
        text = Path(scenario_path).read_text(encoding="utf-8").strip()
        return text[:limit]

    def _assumptions_and_risks(
        self,
        plan: dict[str, Any] | None,
        data_quality_report_path: str | None,
        sql_load_report_path: str | None,
        sql_load_report: dict[str, Any] | None,
    ) -> dict[str, list[str]]:
        assumptions = list(plan.get("assumptions", [])) if plan else []
        risks = []
        next_steps = []
        if not data_quality_report_path:
            risks.append("Data quality report was not provided; audit status is incomplete.")
        if not sql_load_report_path:
            risks.append("SQL load report was not provided; SQL load is treated as not attempted.")
            next_steps.append("Run Phase 12 SQL loading when a local SQL Server is available.")
        elif sql_load_report and sql_load_report.get("status") == "failed":
            risks.append("SQL load failed; generated data may still be valid but was not loaded to the database.")
            next_steps.append("Review local SQL Server connectivity and rerun Phase 12.")
        next_steps.append("Review warnings before using the generated dataset downstream.")
        return {
            "assumptions": assumptions,
            "risks": risks,
            "recommended_next_steps": next_steps,
        }


def render_markdown_report(report: dict[str, Any]) -> str:
    final_status = report["final_status"]
    generation = report["generation_summary"]
    data_quality = report["data_quality_summary"]
    sql_load = report["sql_load_summary"]
    schema = report["schema_summary"]
    formula = report["formula_summary"]

    lines = [
        "# Procurement Data Generation Audit Report",
        "",
        "## 1. Executive Summary",
        "",
        f"- Final status: **{final_status['status']}**",
        f"- Model version: {report.get('report_metadata', {}).get('model_version', 'v2')}",
        f"- Total tables: {schema.get('total_tables')}",
        f"- Total rows: {generation.get('total_rows_generated')}",
        f"- Data quality status: {data_quality.get('overall_status')}",
        f"- SQL load status: {sql_load.get('sql_load_status')}",
        "",
        "## 2. Input Files",
        "",
    ]
    if report.get("report_metadata", {}).get("model_version") == "v2":
        lines[9:9] = [
            "- Procurement v2: 25 generated tables with a full-received 2025 lifecycle.",
            "- InventoryReceiptDetail: receipt-level traceability between inspection and inventory posting.",
            "- InventoryTransaction: inbound StockIn ledger sourced from InventoryReceiptDetail.",
            "- Inventory: calculated stock balance by component, plant, and warehouse.",
            "- InventoryBalance: excluded from Procurement v2.",
        ]
    for key, value in report["input_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## 3. Business Scenario Summary",
            "",
            f"- Industry/domain: {report['business_summary'].get('industry')}",
            f"- Business context: {report['business_summary'].get('business_context')}",
            f"- Scenario preview: {report['business_summary'].get('scenario_text_preview')}",
            "",
            "## 4. Schema and Table Summary",
            "",
            "| Table | Role | Area | Rows |",
            "|---|---|---|---:|",
        ]
    )
    for table in schema.get("tables", []):
        lines.append(f"| {table['table_name']} | {table.get('table_role')} | {table.get('area')} | {table.get('rows', 0)} |")
    lines.extend(
        [
            "",
            "## 5. Formula Execution Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Total Rules | {formula.get('total_formula_rules')} |",
            f"| Applied | {formula.get('applied_rules')} |",
            f"| Skipped | {formula.get('skipped_rules')} |",
            f"| Failed | {formula.get('failed_rules')} |",
            "",
            "## 6. Data Quality Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Checks Run | {data_quality.get('checks_run')} |",
            f"| Passed | {data_quality.get('checks_passed')} |",
            f"| Failed | {data_quality.get('checks_failed')} |",
            f"| Errors | {data_quality.get('error_count')} |",
            f"| Warnings | {data_quality.get('warning_count')} |",
            "",
            "## 7. Top Warnings",
            "",
        ]
    )
    lines.extend(_issue_lines(data_quality.get("top_warnings", [])))
    lines.extend(["", "## 8. Top Errors", ""])
    lines.extend(_issue_lines(data_quality.get("top_errors", [])))
    lines.extend(
        [
            "",
            "## 9. SQL Load Summary",
            "",
            f"- SQL load attempted: {sql_load.get('sql_load_attempted')}",
            f"- SQL load status: {sql_load.get('sql_load_status')}",
            f"- Tables created: {sql_load.get('tables_created')}",
            f"- Tables loaded: {sql_load.get('tables_loaded')}",
            f"- Total rows inserted: {sql_load.get('total_rows_inserted')}",
            "",
            "## 10. Assumptions, Risks, and Next Steps",
            "",
            "### Assumptions",
        ]
    )
    lines.extend(f"- {item}" for item in report["assumptions_and_risks"].get("assumptions", []) or ["None recorded."])
    lines.append("")
    lines.append("### Risks")
    lines.extend(f"- {item}" for item in report["assumptions_and_risks"].get("risks", []) or ["None recorded."])
    lines.append("")
    lines.append("### Recommended Next Steps")
    lines.extend(f"- {item}" for item in report["assumptions_and_risks"].get("recommended_next_steps", []) or ["None recorded."])
    return "\n".join(lines)


def _issue_lines(issues: list[dict[str, Any]]) -> list[str]:
    if not issues:
        return ["- None."]
    return [f"- `{issue.get('check_type')}` {issue.get('table_name') or ''}: {issue.get('message')}" for issue in issues]


def _get(payload: dict[str, Any] | None, *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
