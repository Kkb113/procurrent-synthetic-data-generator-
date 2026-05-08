"""Validate parsed Mermaid ERD relationships against metadata FKs."""

from __future__ import annotations

from dataclasses import dataclass

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport


@dataclass(frozen=True)
class MetadataFkRelationship:
    """A parent-child relationship inferred from a metadata FK column."""

    parent_table: str
    child_table: str
    child_column: str
    parent_column: str


@dataclass(frozen=True)
class ErdValidationSummary:
    """Counts produced by ERD validation."""

    relationships_detected: int
    unknown_erd_tables: int
    metadata_fk_relationships_checked: int
    matched_relationships: int


@dataclass(frozen=True)
class ErdValidationResult:
    """ERD validation result and shared validation report."""

    summary: ErdValidationSummary
    report: ValidationReport


def validate_erd_relationships(
    schema: SchemaContract,
    relationships: list[RelationshipContract],
    report: ValidationReport | None = None,
) -> ErdValidationResult:
    """Validate ERD relationships against the metadata SchemaContract."""

    validation_report = report or ValidationReport(
        total_tables_detected=len(schema.tables),
        total_columns_detected=sum(len(table.columns) for table in schema.tables.values()),
    )

    metadata_relationships = _metadata_fk_relationships(schema)
    known_tables = set(schema.tables)
    unknown_tables = _validate_erd_tables(relationships, known_tables, validation_report)
    _validate_duplicate_erd_relationships(relationships, validation_report)

    erd_pairs = {
        (relationship.parent_table, relationship.child_table)
        for relationship in relationships
        if relationship.parent_table in known_tables and relationship.child_table in known_tables
    }
    metadata_pairs = {
        (relationship.parent_table, relationship.child_table)
        for relationship in metadata_relationships
    }

    matched_relationships = sum(
        1
        for metadata_relationship in metadata_relationships
        if (metadata_relationship.parent_table, metadata_relationship.child_table) in erd_pairs
    )

    _validate_metadata_fk_coverage(metadata_relationships, erd_pairs, validation_report)
    _validate_erd_fk_coverage(relationships, metadata_pairs, known_tables, validation_report)

    summary = ErdValidationSummary(
        relationships_detected=len(relationships),
        unknown_erd_tables=len(unknown_tables),
        metadata_fk_relationships_checked=len(metadata_relationships),
        matched_relationships=matched_relationships,
    )
    return ErdValidationResult(summary=summary, report=validation_report)


def format_erd_validation_result(result: ErdValidationResult) -> str:
    """Format ERD validation output for CLI usage."""

    report = result.report
    summary = result.summary
    lines = [
        "ERD validation completed.",
        f"Relationships detected: {summary.relationships_detected}",
        f"Unknown ERD tables: {summary.unknown_erd_tables}",
        f"Metadata FK relationships checked: {summary.metadata_fk_relationships_checked}",
        f"Matched relationships: {summary.matched_relationships}",
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


def _metadata_fk_relationships(schema: SchemaContract) -> list[MetadataFkRelationship]:
    relationships: list[MetadataFkRelationship] = []
    for table in schema.tables.values():
        for column in table.columns:
            if column.key_type == "FK" and column.related_table and column.related_column:
                relationships.append(
                    MetadataFkRelationship(
                        parent_table=column.related_table,
                        child_table=table.table_name,
                        child_column=column.column_name,
                        parent_column=column.related_column,
                    )
                )
    return relationships


def _validate_erd_tables(
    relationships: list[RelationshipContract],
    known_tables: set[str],
    report: ValidationReport,
) -> set[str]:
    unknown_tables: set[str] = set()
    for relationship in relationships:
        for table_name in (relationship.parent_table, relationship.child_table):
            if table_name not in known_tables:
                unknown_tables.add(table_name)

    for table_name in sorted(unknown_tables):
        report.add_error(
            table_name=table_name,
            message=f"ERD references table {table_name}, but it does not exist in metadata.",
            suggested_fix="Add the table to metadata or correct the ERD table name.",
        )
    return unknown_tables


def _validate_duplicate_erd_relationships(
    relationships: list[RelationshipContract],
    report: ValidationReport,
) -> None:
    seen: set[tuple[str, str, str]] = set()
    warned: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        key = (relationship.parent_table, relationship.child_table, relationship.relationship_type)
        if key in seen and key not in warned:
            report.add_warning(
                table_name=relationship.child_table,
                message=(
                    "Duplicate ERD relationship detected: "
                    f"{relationship.parent_table} -> {relationship.child_table}."
                ),
                suggested_fix="Keep one relationship line for each parent-child relationship in the ERD.",
            )
            warned.add(key)
        seen.add(key)


def _validate_metadata_fk_coverage(
    metadata_relationships: list[MetadataFkRelationship],
    erd_pairs: set[tuple[str, str]],
    report: ValidationReport,
) -> None:
    for relationship in metadata_relationships:
        if (relationship.parent_table, relationship.child_table) not in erd_pairs:
            report.add_warning(
                table_name=relationship.child_table,
                column_name=relationship.child_column,
                message=(
                    "Metadata FK relationship "
                    f"{relationship.parent_table} -> {relationship.child_table} is missing from ERD."
                ),
                suggested_fix=(
                    f"Add {relationship.parent_table} ||--o{{ "
                    f"{relationship.child_table} : contains to the ERD."
                ),
            )


def _validate_erd_fk_coverage(
    relationships: list[RelationshipContract],
    metadata_pairs: set[tuple[str, str]],
    known_tables: set[str],
    report: ValidationReport,
) -> None:
    warned_pairs: set[tuple[str, str]] = set()
    for relationship in relationships:
        pair = (relationship.parent_table, relationship.child_table)
        if pair in warned_pairs:
            continue
        if relationship.parent_table not in known_tables or relationship.child_table not in known_tables:
            continue
        if pair not in metadata_pairs:
            report.add_warning(
                table_name=relationship.child_table,
                message=(
                    "ERD relationship has no matching metadata FK: "
                    f"{relationship.parent_table} -> {relationship.child_table}."
                ),
                suggested_fix="Add the FK to metadata or remove/correct this ERD relationship.",
            )
            warned_pairs.add(pair)


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
