"""Production Execution role validation for metadata SchemaContract objects."""

from __future__ import annotations

from dataclasses import dataclass

from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.modules.production.role_catalog import get_production_role_catalog


@dataclass(frozen=True)
class ProductionRoleValidationSummary:
    """Counts produced by Production Execution role validation."""

    expected_roles: int
    detected_roles: int
    unsupported_roles: int
    duplicate_roles: int


@dataclass(frozen=True)
class ProductionRoleValidationResult:
    """Production Execution role validation result."""

    summary: ProductionRoleValidationSummary
    report: ValidationReport


def validate_production_roles(
    schema: SchemaContract,
    report: ValidationReport | None = None,
    model_version: str = "production_v1",
) -> ProductionRoleValidationResult:
    """Validate schema table roles against the Production Execution role catalog."""

    role_catalog = get_production_role_catalog(model_version)
    validation_report = report or ValidationReport(
        total_tables_detected=len(schema.tables),
        total_columns_detected=sum(len(table.columns) for table in schema.tables.values()),
    )
    role_to_tables = _group_tables_by_role(schema)
    detected_supported_roles = {role_name for role_name in role_to_tables if role_name in role_catalog}
    unsupported_role_count = len([role_name for role_name in role_to_tables if role_name not in role_catalog])
    duplicate_role_count = len([role_name for role_name, tables in role_to_tables.items() if len(tables) > 1])

    _validate_supported_roles(role_to_tables, validation_report, role_catalog)
    _validate_missing_roles(detected_supported_roles, validation_report, tuple(role_catalog))
    _validate_duplicate_roles(role_to_tables, validation_report)
    _validate_table_name_area_and_order(role_to_tables, validation_report, role_catalog)
    _validate_required_columns(role_to_tables, validation_report, role_catalog)
    _validate_cross_module_columns(schema, validation_report)

    return ProductionRoleValidationResult(
        summary=ProductionRoleValidationSummary(
            expected_roles=len(role_catalog),
            detected_roles=len(detected_supported_roles),
            unsupported_roles=unsupported_role_count,
            duplicate_roles=duplicate_role_count,
        ),
        report=validation_report,
    )


def format_production_role_validation_result(result: ProductionRoleValidationResult) -> str:
    """Format Production Execution role validation output for CLI usage."""

    report = result.report
    summary = result.summary
    lines = [
        "Production role validation completed.",
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


def _validate_supported_roles(role_to_tables, report: ValidationReport, role_catalog) -> None:
    for role_name, tables in role_to_tables.items():
        if role_name not in role_catalog:
            for table in tables:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Unsupported Production Execution table role: {role_name}.",
                    suggested_fix="Use one of the supported Production Execution TableRole values.",
                )


def _validate_missing_roles(detected_supported_roles: set[str], report: ValidationReport, supported_roles: tuple[str, ...]) -> None:
    for role_name in supported_roles:
        if role_name not in detected_supported_roles:
            report.add_error(
                message=f"Missing Production Execution table role: {role_name}.",
                suggested_fix=f"Add one table with TableRole '{role_name}' to the metadata.",
            )


def _validate_duplicate_roles(role_to_tables, report: ValidationReport) -> None:
    for role_name, tables in role_to_tables.items():
        if len(tables) <= 1:
            continue
        table_names = ", ".join(table.table_name for table in tables)
        for table in tables:
            report.add_error(
                table_name=table.table_name,
                message=f"Duplicate Production Execution table role: {role_name}. Tables: {table_names}.",
                suggested_fix=f"Use TableRole '{role_name}' on exactly one table.",
            )


def _validate_table_name_area_and_order(role_to_tables, report: ValidationReport, role_catalog) -> None:
    for role_name, tables in role_to_tables.items():
        role_definition = role_catalog.get(role_name)
        if role_definition is None:
            continue
        for table in tables:
            if table.table_name != role_definition.expected_table_name:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Role {role_name} must be mapped to table {role_definition.expected_table_name}.",
                    suggested_fix=f"Set TableName to {role_definition.expected_table_name} for role {role_name}.",
                )
            if table.area != role_definition.expected_area:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Area mismatch for role {role_name}. Expected {role_definition.expected_area} but found {table.area}.",
                    suggested_fix=f"Set Area to {role_definition.expected_area} for {role_name}.",
                )
            if table.process_order != role_definition.process_order:
                report.add_warning(
                    table_name=table.table_name,
                    message=f"ProcessOrder differs for role {role_name}. Expected {role_definition.process_order} but found {table.process_order}.",
                    suggested_fix="Use the Production Execution module within MES context v1 lifecycle ProcessOrder unless there is a reviewed reason.",
                )


def _validate_required_columns(role_to_tables, report: ValidationReport, role_catalog) -> None:
    for role_name, tables in role_to_tables.items():
        role_definition = role_catalog.get(role_name)
        if role_definition is None:
            continue
        for table in tables:
            column_names = {column.column_name for column in table.columns}
            missing = [column for column in role_definition.required_column_names if column not in column_names]
            if missing:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Required columns missing for role {role_name}: {', '.join(missing)}.",
                    suggested_fix="Add the required Production Execution columns to the metadata.",
                )


def _validate_cross_module_columns(schema: SchemaContract, report: ValidationReport) -> None:
    expected = [
        ("BOMLine", "ComponentID", "ComponentMaster", "ComponentID"),
        ("BOMHeader", "PlantID", "Plant", "PlantID"),
        ("WorkCenter", "PlantID", "Plant", "PlantID"),
        ("ProductionOrderHdr", "PlantID", "Plant", "PlantID"),
        ("ProductionMaterialRequirement", "InventoryID", "Inventory", "InventoryID"),
        ("MaterialIssueLine", "SourceInventoryTransactionID", "InventoryTransaction", "InventoryTransactionID"),
        ("MaterialIssueLine", "InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"),
        ("ProductionGenealogy", "InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"),
        ("ProductionGenealogy", "SourceInventoryTransactionID", "InventoryTransaction", "InventoryTransactionID"),
        ("ProductionGenealogy", "SupplierID", "SupplierMaster", "SupplierID"),
    ]
    for table_name, column_name, related_table, related_column in expected:
        table = schema.tables.get(table_name)
        column = next((candidate for candidate in table.columns if candidate.column_name == column_name), None) if table else None
        if column is None:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"Production Execution cross-module dependency column {table_name}.{column_name} is missing.",
                suggested_fix="Add the required Procurement integration FK column.",
            )
            continue
        if column.related_table != related_table or column.related_column != related_column:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"{table_name}.{column_name} must reference {related_table}.{related_column}.",
                suggested_fix="Set RelatedTable and RelatedColumn to the required Procurement integration target.",
            )


def _format_issue(index: int, table_name: str | None, column_name: str | None, message: str, suggested_fix: str) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines



