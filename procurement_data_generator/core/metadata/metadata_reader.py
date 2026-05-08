"""XLSX metadata reader for Phase 1."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd

from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.metadata.metadata_validator import (
    MetadataValidationResult,
    validate_metadata_dataframe,
)


METADATA_SHEET_NAME = "Metadata"


def load_metadata_schema(xlsx_path: str | Path) -> MetadataValidationResult:
    """Read the Metadata sheet from an XLSX file and validate it."""

    path = Path(xlsx_path)
    if not path.exists():
        report = ValidationReport()
        report.add_error(
            message=f"Metadata file does not exist: {path}",
            suggested_fix="Provide a valid path to an XLSX metadata file.",
        )
        return MetadataValidationResult(schema=None, report=report)

    try:
        metadata_df = pd.read_excel(path, sheet_name=METADATA_SHEET_NAME, engine="openpyxl", dtype=object)
    except ValueError:
        report = ValidationReport()
        report.add_error(
            message=f"Required sheet '{METADATA_SHEET_NAME}' was not found.",
            suggested_fix=f"Create a sheet named '{METADATA_SHEET_NAME}' in the XLSX file.",
        )
        return MetadataValidationResult(schema=None, report=report)

    return validate_metadata_dataframe(metadata_df)


def read_metadata_schema(xlsx_path: str | Path) -> SchemaContract:
    """Read metadata and return a SchemaContract, raising ValueError if invalid."""

    result = load_metadata_schema(xlsx_path)
    if not result.report.is_valid or result.schema is None:
        messages = [issue.message for issue in result.report.errors]
        raise ValueError("Invalid metadata: " + "; ".join(messages))
    return result.schema


def format_validation_report(report: ValidationReport, schema: Optional[SchemaContract] = None) -> str:
    """Format a validation report for CLI output."""

    lines: list[str] = []
    if report.is_valid:
        lines.append("Metadata loaded successfully.")
    lines.append(f"Tables detected: {report.total_tables_detected}")
    lines.append(f"Total columns detected: {report.total_columns_detected}")
    lines.append(f"Errors: {len(report.errors)}")
    lines.append(f"Warnings: {len(report.warnings)}")
    lines.append(f"Validation status: {'passed' if report.is_valid else 'failed'}")

    if schema is not None and report.is_valid:
        table_names = ", ".join(table.table_name for table in schema.ordered_tables)
        lines.append(f"Tables: {table_names}")

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, issue in enumerate(report.warnings, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))

    return "\n".join(lines)


def _format_issue(
    index: int,
    table_name: Optional[str],
    column_name: Optional[str],
    message: str,
    suggested_fix: str,
) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines


def main() -> int:
    """CLI entry point for metadata validation."""

    parser = argparse.ArgumentParser(description="Validate procurement metadata XLSX.")
    parser.add_argument("xlsx_path", help="Path to the metadata XLSX file.")
    args = parser.parse_args()

    result = load_metadata_schema(args.xlsx_path)
    print(format_validation_report(result.report, result.schema))
    return 0 if result.report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
