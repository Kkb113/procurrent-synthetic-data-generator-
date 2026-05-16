from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.validation.data_validator import GeneratedDataValidator


def test_missing_table_produces_error() -> None:
    report = GeneratedDataValidator().validate_dataset({}, _schema())

    assert _has_issue(report, "TABLE_EXISTENCE")


def test_missing_required_column_produces_error() -> None:
    data = _valid_data()
    data["Child"] = data["Child"].drop(columns=["Status"])
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "COLUMN_EXISTENCE")


def test_pk_null_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "ChildID"] = None
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "PK_NON_NULL")


def test_pk_duplicate_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[1, "ChildID"] = data["Child"].loc[0, "ChildID"]
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "PK_UNIQUE")


def test_fk_missing_parent_value_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "ParentID"] = 999
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "FK_INTEGRITY")


def test_nullable_no_with_null_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "RequiredText"] = None
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "NOT_NULL")


def test_allowed_values_violation_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "Status"] = "Bad"
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "ALLOWED_VALUES")


def test_numeric_range_violation_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "Quantity"] = 999
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "NUMERIC_RANGE")


def test_date_range_violation_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "EventDate"] = "2026-01-01"
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "DATE_RANGE")


def test_infinity_value_produces_error() -> None:
    data = _valid_data()
    data["Child"].loc[0, "Amount"] = np.inf
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "INFINITY")


def test_inventory_target_row_mismatch_is_warning_not_error() -> None:
    data = _valid_data()
    data["Inventory"] = pd.DataFrame({"InventoryID": [1], "OnHandQuantity": [10]})
    report = GeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "ROW_COUNT", level="warning")
    assert not report.errors


def test_procurement_v1_data_validation_is_no_longer_supported() -> None:
    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        GeneratedDataValidator().validate_dataset(_valid_data(), _schema(), model_version="v1")


def _valid_data() -> dict[str, pd.DataFrame]:
    return {
        "Parent": pd.DataFrame({"ParentID": [1, 2]}),
        "Child": pd.DataFrame(
            {
                "ChildID": [1, 2],
                "ParentID": [1, 2],
                "RequiredText": ["A", "B"],
                "Status": ["Active", "Inactive"],
                "Quantity": [10, 20],
                "Amount": [25.0, 50.0],
                "EventDate": ["2025-01-01", "2025-01-02"],
            }
        ),
        "Inventory": pd.DataFrame({"InventoryID": [1, 2], "OnHandQuantity": [10, 20]}),
    }


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "Parent": TableContract(
                table_name="Parent",
                process_order=1,
                area="Master",
                table_role="parent_dimension",
                target_rows=2,
                columns=[_col("ParentID", "int", "sequence_id", "No", key_type="PK")],
            ),
            "Child": TableContract(
                table_name="Child",
                process_order=2,
                area="Procurement",
                table_role="child_transaction",
                target_rows=2,
                columns=[
                    _col("ChildID", "int", "sequence_id", "No", key_type="PK"),
                    _col("ParentID", "int", "foreign_key", "No", key_type="FK", related_table="Parent", related_column="ParentID"),
                    _col("RequiredText", "varchar(50)", "category", "No"),
                    _col("Status", "varchar(20)", "status", "No", allowed_values=["Active", "Inactive"]),
                    _col("Quantity", "int", "integer_range", "No", min_value=0, max_value=100),
                    _col("Amount", "decimal(18,2)", "decimal_range", "No", min_value=0, max_value=100),
                    _col("EventDate", "date", "date_range", "No", min_value="2025-01-01", max_value="2025-12-31"),
                ],
            ),
            "Inventory": TableContract(
                table_name="Inventory",
                process_order=3,
                area="Inventory",
                table_role="inventory",
                target_rows=2,
                columns=[
                    _col("InventoryID", "int", "sequence_id", "No", key_type="PK"),
                    _col("OnHandQuantity", "int", "integer_range", "No", min_value=0, max_value=100),
                ],
            ),
        }
    )


def _col(
    column_name: str,
    data_type: str,
    generation_type: str,
    nullable: str,
    key_type: str | None = None,
    related_table: str | None = None,
    related_column: str | None = None,
    allowed_values: list[str] | None = None,
    min_value=None,
    max_value=None,
) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type=data_type,
        key_type=key_type,
        related_table=related_table,
        related_column=related_column,
        nullable=nullable,
        generation_type=generation_type,
        allowed_values=allowed_values or [],
        min_value=min_value,
        max_value=max_value,
        formula=None,
    )


def _has_issue(report, check_type: str, level: str = "error") -> bool:
    return any(issue.check_type == check_type and issue.level == level for issue in report.issues)
