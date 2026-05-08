"""Validation and contract-building for metadata XLSX rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from pydantic import ValidationError

from procurement_data_generator.core.contracts.schema_contract import (
    ColumnContract,
    SchemaContract,
    TableContract,
)
from procurement_data_generator.core.contracts.validation_report import ValidationReport


REQUIRED_METADATA_COLUMNS = [
    "TableName",
    "ProcessOrder",
    "Area",
    "TableRole",
    "TargetRows",
    "ColumnName",
    "DataType",
    "KeyType",
    "RelatedTable",
    "RelatedColumn",
    "Nullable",
    "GenerationType",
    "AllowedValues",
    "MinValue",
    "MaxValue",
    "Formula",
]

REQUIRED_VALUE_COLUMNS = [
    "TableName",
    "ProcessOrder",
    "Area",
    "TableRole",
    "TargetRows",
    "ColumnName",
    "DataType",
    "Nullable",
    "GenerationType",
]

SUPPORTED_AREAS = {"Master", "Procurement", "Logistics", "Receiving", "Quality", "Inventory", "Finance"}
SUPPORTED_KEY_TYPES = {"PK", "FK"}
SUPPORTED_NULLABLE_VALUES = {"Yes", "No"}
SUPPORTED_GENERATION_TYPES = {
    "sequence_id",
    "foreign_key",
    "vendor_name",
    "material_name",
    "plant_name",
    "warehouse_name",
    "faker_company",
    "faker_person",
    "category",
    "status",
    "integer_range",
    "decimal_range",
    "date_range",
    "date_offset",
    "calculated",
}


@dataclass(frozen=True)
class MetadataValidationResult:
    """Result of validating metadata rows."""

    schema: Optional[SchemaContract]
    report: ValidationReport


def validate_metadata_dataframe(metadata_df: pd.DataFrame) -> MetadataValidationResult:
    """Validate a metadata DataFrame and build a SchemaContract when valid."""

    report = ValidationReport()
    missing_columns = [column for column in REQUIRED_METADATA_COLUMNS if column not in metadata_df.columns]
    if missing_columns:
        for column in missing_columns:
            report.add_error(
                message=f"Required metadata column '{column}' is missing.",
                suggested_fix=f"Add the '{column}' column to the Metadata sheet.",
            )
        return MetadataValidationResult(schema=None, report=report)

    df = metadata_df[REQUIRED_METADATA_COLUMNS].copy()
    normalized_rows = [_normalize_row(row) for row in df.to_dict(orient="records")]
    report.total_tables_detected = len({row["TableName"] for row in normalized_rows if row["TableName"]})
    report.total_columns_detected = len(
        {(row["TableName"], row["ColumnName"]) for row in normalized_rows if row["TableName"] and row["ColumnName"]}
    )

    _validate_rows(normalized_rows, report)

    if report.errors:
        return MetadataValidationResult(schema=None, report=report)

    schema = _build_schema_contract(normalized_rows, report)
    if report.errors:
        return MetadataValidationResult(schema=None, report=report)

    return MetadataValidationResult(schema=schema, report=report)


def _validate_rows(rows: list[dict[str, Any]], report: ValidationReport) -> None:
    for row in rows:
        table_name = row.get("TableName")
        column_name = row.get("ColumnName")

        for required_column in REQUIRED_VALUE_COLUMNS:
            if _is_blank(row.get(required_column)):
                report.add_error(
                    table_name=table_name,
                    column_name=column_name,
                    message=f"Required field '{required_column}' is blank.",
                    suggested_fix=f"Provide a value for '{required_column}' in every metadata row.",
                )

        _validate_positive_int(row, "ProcessOrder", table_name, column_name, report)
        _validate_positive_int(row, "TargetRows", table_name, column_name, report)

        area = row.get("Area")
        if not _is_blank(area) and area not in SUPPORTED_AREAS:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"Area '{area}' is not supported.",
                suggested_fix=f"Use one of: {', '.join(sorted(SUPPORTED_AREAS))}.",
            )

        key_type = row.get("KeyType")
        if not _is_blank(key_type) and key_type not in SUPPORTED_KEY_TYPES:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"KeyType '{key_type}' is not supported.",
                suggested_fix="Use 'PK', 'FK', or leave KeyType blank.",
            )

        nullable = row.get("Nullable")
        if not _is_blank(nullable) and nullable not in SUPPORTED_NULLABLE_VALUES:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"Nullable value '{nullable}' is not supported.",
                suggested_fix="Use 'Yes' or 'No'.",
            )

        generation_type = row.get("GenerationType")
        if not _is_blank(generation_type) and generation_type not in SUPPORTED_GENERATION_TYPES:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"GenerationType '{generation_type}' is not supported.",
                suggested_fix=f"Use one of: {', '.join(sorted(SUPPORTED_GENERATION_TYPES))}.",
            )

        if key_type == "FK" and (_is_blank(row.get("RelatedTable")) or _is_blank(row.get("RelatedColumn"))):
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message="FK column is missing RelatedTable or RelatedColumn.",
                suggested_fix="Provide RelatedTable and RelatedColumn for FK columns.",
            )

    _validate_primary_keys(rows, report)


def _validate_primary_keys(rows: list[dict[str, Any]], report: ValidationReport) -> None:
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        table_name = row.get("TableName")
        if not _is_blank(table_name):
            rows_by_table.setdefault(table_name, []).append(row)

    for table_name, table_rows in rows_by_table.items():
        primary_keys = [row for row in table_rows if row.get("KeyType") == "PK"]
        if len(primary_keys) != 1:
            report.add_error(
                table_name=table_name,
                message=f"Table has {len(primary_keys)} primary key columns; exactly one is required.",
                suggested_fix="Mark exactly one column as KeyType 'PK' for this table.",
            )


def _build_schema_contract(rows: list[dict[str, Any]], report: ValidationReport) -> Optional[SchemaContract]:
    tables: dict[str, TableContract] = {}
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_table.setdefault(row["TableName"], []).append(row)

    for table_name, table_rows in rows_by_table.items():
        first_row = table_rows[0]
        columns = [_build_column_contract(row) for row in table_rows]
        try:
            tables[table_name] = TableContract(
                table_name=table_name,
                process_order=_to_positive_int(first_row["ProcessOrder"]),
                area=first_row["Area"],
                table_role=first_row["TableRole"],
                target_rows=_to_positive_int(first_row["TargetRows"]),
                columns=columns,
            )
        except ValidationError as exc:
            report.add_error(
                table_name=table_name,
                message=f"Metadata contract validation failed: {exc.errors()}",
                suggested_fix="Review the metadata values for this table.",
            )

    if report.errors:
        return None

    return SchemaContract(tables=tables)


def _build_column_contract(row: dict[str, Any]) -> ColumnContract:
    return ColumnContract(
        column_name=row["ColumnName"],
        data_type=row["DataType"],
        key_type=row["KeyType"],
        related_table=row["RelatedTable"],
        related_column=row["RelatedColumn"],
        nullable=row["Nullable"],
        generation_type=row["GenerationType"],
        allowed_values=_parse_allowed_values(row["AllowedValues"]),
        min_value=row["MinValue"],
        max_value=row["MaxValue"],
        formula=row["Formula"],
    )


def _validate_positive_int(
    row: dict[str, Any],
    field_name: str,
    table_name: Optional[str],
    column_name: Optional[str],
    report: ValidationReport,
) -> None:
    value = row.get(field_name)
    if _is_blank(value):
        return

    try:
        int_value = _to_positive_int(value)
    except (TypeError, ValueError):
        report.add_error(
            table_name=table_name,
            column_name=column_name,
            message=f"{field_name} must be numeric.",
            suggested_fix=f"Provide a numeric value greater than 0 for {field_name}.",
        )
        return

    if int_value <= 0:
        report.add_error(
            table_name=table_name,
            column_name=column_name,
            message=f"{field_name} must be greater than 0.",
            suggested_fix=f"Provide a numeric value greater than 0 for {field_name}.",
        )


def _to_positive_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid integers.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("Decimal values are not valid integers.")
        return int(value)
    text = str(value).strip()
    if "." in text:
        float_value = float(text)
        if not float_value.is_integer():
            raise ValueError("Decimal values are not valid integers.")
        return int(float_value)
    return int(text)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in row.items()}


def _normalize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _parse_allowed_values(value: Any) -> list[str]:
    if _is_blank(value):
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
