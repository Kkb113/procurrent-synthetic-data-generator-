"""Production Execution module within MES context v1 generated data validator."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.modules.production.reconciler_rules import (
    PRODUCTION_MASTER_TABLES,
    PRODUCTION_TABLES,
    PRODUCTION_TRANSACTION_TABLES,
    UPSTREAM_TABLES,
    ProductionQualityResult,
    reconcile_production_data,
)


def validate_production_generated_data(
    schema: SchemaContract,
    master_data_folder: str | Path,
    transaction_data_folder: str | Path,
    upstream_data_folder: str | Path,
) -> ProductionQualityResult:
    """Load generated Production data and upstream Procurement data, then reconcile it."""

    production_data = {}
    production_data.update(_load_tables(master_data_folder, PRODUCTION_MASTER_TABLES))
    production_data.update(_load_tables(transaction_data_folder, PRODUCTION_TRANSACTION_TABLES))
    upstream_data = _load_tables(upstream_data_folder, UPSTREAM_TABLES)
    target_row_counts = {table_name: table.target_rows for table_name, table in schema.tables.items()}
    return reconcile_production_data(production_data, upstream_data, target_row_counts=target_row_counts)


def write_production_quality_reports(result: ProductionQualityResult, output_folder: str | Path) -> tuple[Path, Path]:
    """Write JSON and Markdown Production data quality reports."""

    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "production_data_quality_report.json"
    md_path = output_path / "production_data_quality_report.md"
    json_path.write_text(json.dumps(asdict(result), indent=2, default=str), encoding="utf-8")
    md_path.write_text(format_production_quality_markdown(result), encoding="utf-8")
    return json_path, md_path


def format_production_quality_markdown(result: ProductionQualityResult) -> str:
    """Format a concise manager-facing Production quality report."""

    lines = [
        "# Production v1 Data Quality Report",
        "",
        f"Status: {result.status}",
        f"Errors: {len(result.errors)}",
        f"Warnings: {len(result.warnings)}",
        f"Production tables present: {result.summary_metrics.get('production_tables')}",
        f"Total rows: {result.summary_metrics.get('total_rows')}",
        "",
        "## Scorecard",
    ]
    for check_name, issue_count in result.scorecard.items():
        lines.append(f"- {check_name}: {issue_count}")
    lines.extend(["", "## Table Row Counts"])
    for table_name in PRODUCTION_TABLES:
        lines.append(f"- {table_name}: {result.table_row_counts.get(table_name, 0)}")
    if result.errors:
        lines.extend(["", "## Errors"])
        for issue in result.errors:
            lines.append(f"- {issue.check_type} | {issue.table_name or 'N/A'} | {issue.column_name or 'N/A'}: {issue.message}")
    if result.warnings:
        lines.extend(["", "## Warnings"])
        for issue in result.warnings:
            lines.append(f"- {issue.check_type} | {issue.table_name or 'N/A'}: {issue.message}")
    return "\n".join(lines) + "\n"


def _load_tables(folder: str | Path, table_names: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    path = Path(folder)
    dataframes: dict[str, pd.DataFrame] = {}
    for table_name in table_names:
        csv_path = path / f"{table_name}.csv"
        if csv_path.exists():
            dataframes[table_name] = pd.read_csv(csv_path, keep_default_na=False)
    return dataframes

