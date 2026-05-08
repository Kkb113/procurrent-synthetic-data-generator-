"""Procurement role validation for metadata SchemaContract objects."""

from __future__ import annotations

from dataclasses import dataclass

from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.modules.procurement.role_catalog import (
    get_procurement_role_catalog,
)


@dataclass(frozen=True)
class ProcurementRoleValidationSummary:
    """Counts produced by procurement role validation."""

    expected_roles: int
    detected_roles: int
    unsupported_roles: int
    duplicate_roles: int


@dataclass(frozen=True)
class ProcurementRoleValidationResult:
    """Procurement role validation result and shared validation report."""

    summary: ProcurementRoleValidationSummary
    report: ValidationReport


def validate_procurement_roles(
    schema: SchemaContract,
    report: ValidationReport | None = None,
    model_version: str = "v1",
) -> ProcurementRoleValidationResult:
    """Validate schema table roles against the procurement role catalog."""

    role_catalog = get_procurement_role_catalog(model_version)
    supported_roles = tuple(role_catalog.keys())
    validation_report = report or ValidationReport(
        total_tables_detected=len(schema.tables),
        total_columns_detected=sum(len(table.columns) for table in schema.tables.values()),
    )

    role_to_tables = _group_tables_by_role(schema)
    detected_supported_roles = {
        role_name for role_name in role_to_tables if role_name in role_catalog
    }
    unsupported_role_count = len(
        [role_name for role_name in role_to_tables if role_name not in role_catalog]
    )
    duplicate_role_count = len(
        [role_name for role_name, tables in role_to_tables.items() if len(tables) > 1]
    )

    _validate_supported_roles(role_to_tables, validation_report, role_catalog)
    _validate_missing_roles(detected_supported_roles, validation_report, supported_roles)
    _validate_duplicate_roles(role_to_tables, validation_report)
    _validate_area_matches(role_to_tables, validation_report, role_catalog)
    _validate_recommended_columns(role_to_tables, validation_report, role_catalog)

    summary = ProcurementRoleValidationSummary(
        expected_roles=len(role_catalog),
        detected_roles=len(detected_supported_roles),
        unsupported_roles=unsupported_role_count,
        duplicate_roles=duplicate_role_count,
    )
    return ProcurementRoleValidationResult(summary=summary, report=validation_report)


def format_procurement_role_validation_result(result: ProcurementRoleValidationResult) -> str:
    """Format role validation output for CLI usage."""

    report = result.report
    summary = result.summary
    lines = [
        "Procurement role validation completed.",
        f"Expected roles: {summary.expected_roles}",
        f"Detected roles: {summary.detected_roles}",
        f"Unsupported roles: {summary.unsupported_roles}",
        f"Duplicate roles: {summary.duplicate_roles}",
        f"Errors: {len(report.errors)}",
        f"Warnings: {len(report.warnings)}",
        f"Validation status: {'passed' if report.is_valid else 'failed'}",
    ]

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


def _group_tables_by_role(schema: SchemaContract) -> dict[str, list[TableContract]]:
    role_to_tables: dict[str, list[TableContract]] = {}
    for table in schema.tables.values():
        role_to_tables.setdefault(table.table_role, []).append(table)
    return role_to_tables


def _validate_supported_roles(
    role_to_tables: dict[str, list[TableContract]],
    report: ValidationReport,
    role_catalog,
) -> None:
    for role_name, tables in role_to_tables.items():
        if role_name not in role_catalog:
            for table in tables:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Unsupported procurement table role: {role_name}.",
                    suggested_fix="Use one of the supported procurement TableRole values.",
                )


def _validate_missing_roles(
    detected_supported_roles: set[str],
    report: ValidationReport,
    supported_roles: tuple[str, ...],
) -> None:
    missing_roles = [role_name for role_name in supported_roles if role_name not in detected_supported_roles]
    for role_name in missing_roles:
        report.add_error(
            message=f"Missing procurement table role: {role_name}.",
            suggested_fix=f"Add one table with TableRole '{role_name}' to the metadata.",
        )


def _validate_duplicate_roles(role_to_tables: dict[str, list[TableContract]], report: ValidationReport) -> None:
    for role_name, tables in role_to_tables.items():
        if len(tables) <= 1:
            continue
        table_names = ", ".join(table.table_name for table in tables)
        for table in tables:
            report.add_error(
                table_name=table.table_name,
                message=f"Duplicate procurement table role: {role_name}. Tables: {table_names}.",
                suggested_fix=f"Use TableRole '{role_name}' on exactly one table.",
            )


def _validate_area_matches(
    role_to_tables: dict[str, list[TableContract]],
    report: ValidationReport,
    role_catalog,
) -> None:
    for role_name, tables in role_to_tables.items():
        role_definition = role_catalog.get(role_name)
        if role_definition is None:
            continue
        for table in tables:
            if table.area != role_definition.expected_area:
                report.add_error(
                    table_name=table.table_name,
                    message=(
                        f"Area mismatch for role {role_name}. "
                        f"Expected {role_definition.expected_area} but found {table.area}."
                    ),
                    suggested_fix=f"Set Area to {role_definition.expected_area} for {role_name}.",
                )


def _validate_recommended_columns(
    role_to_tables: dict[str, list[TableContract]],
    report: ValidationReport,
    role_catalog,
) -> None:
    for role_name, tables in role_to_tables.items():
        role_definition = role_catalog.get(role_name)
        if role_definition is None:
            continue
        for table in tables:
            column_names = {column.column_name for column in table.columns}
            missing_columns = [
                column_name
                for column_name in role_definition.recommended_column_names
                if column_name not in column_names
            ]
            if missing_columns:
                report.add_warning(
                    table_name=table.table_name,
                    message=(
                        f"Recommended columns missing for role {role_name}: "
                        f"{', '.join(missing_columns)}."
                    ),
                    suggested_fix="Add recommended logical columns when they fit your metadata design.",
                )


def _format_issue(
    index: int,
    table_name: str | None,
    column_name: str | None,
    message: str,
    suggested_fix: str,
) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines
