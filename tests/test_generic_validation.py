from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.validation.generic_validator import GenericGeneratedDataValidator


@pytest.mark.unit
def test_generic_validator_checks_missing_table() -> None:
    report = GenericGeneratedDataValidator().validate_dataset({}, _schema())

    assert _has_issue(report, "TABLE_EXISTENCE")


@pytest.mark.unit
def test_generic_validator_checks_required_columns() -> None:
    data = _valid_data()
    data["Child"] = data["Child"].drop(columns=["Status"])

    report = GenericGeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "COLUMN_EXISTENCE")


@pytest.mark.unit
def test_generic_validator_checks_primary_key_uniqueness() -> None:
    data = _valid_data()
    data["Child"].loc[1, "ChildID"] = data["Child"].loc[0, "ChildID"]

    report = GenericGeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "PK_UNIQUE")


@pytest.mark.unit
def test_generic_validator_checks_foreign_key_integrity() -> None:
    data = _valid_data()
    data["Child"].loc[0, "ParentID"] = 999

    report = GenericGeneratedDataValidator().validate_dataset(data, _schema())

    assert _has_issue(report, "FK_INTEGRITY")


@pytest.mark.unit
def test_generic_validator_does_not_apply_procurement_v2_expected_table_rules() -> None:
    schema = SchemaContract(
        tables={
            "SupplierMaster": TableContract(
                table_name="SupplierMaster",
                process_order=1,
                area="Master",
                table_role="supplier_master",
                target_rows=1,
                columns=[_col("SupplierID", "int", "sequence_id", "No", key_type="PK")],
            )
        }
    )
    data = {"SupplierMaster": pd.DataFrame({"SupplierID": [1]})}

    report = GenericGeneratedDataValidator().validate_dataset(data, schema)

    assert not _has_issue(report, "V2_EXPECTED_TABLE")


@pytest.mark.unit
def test_generic_validation_file_has_no_module_specific_imports_or_lifecycle_rules() -> None:
    source = Path("procurement_data_generator/core/validation/generic_validator.py").read_text(encoding="utf-8")

    assert "modules.procurement" not in source
    assert "modules.production" not in source
    assert "ProcurementGeneratedDataValidator" not in source
    assert "V2_EXPECTED_TABLE" not in source
    assert "production_genealogy_traceability" not in source


def _valid_data() -> dict[str, pd.DataFrame]:
    return {
        "Parent": pd.DataFrame({"ParentID": [1, 2]}),
        "Child": pd.DataFrame(
            {
                "ChildID": [1, 2],
                "ParentID": [1, 2],
                "Status": ["Active", "Inactive"],
            }
        ),
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
                area="MES",
                table_role="child_transaction",
                target_rows=2,
                columns=[
                    _col("ChildID", "int", "sequence_id", "No", key_type="PK"),
                    _col("ParentID", "int", "foreign_key", "No", key_type="FK", related_table="Parent", related_column="ParentID"),
                    _col("Status", "varchar(20)", "status", "No", allowed_values=["Active", "Inactive"]),
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
        formula=None,
    )


def _has_issue(report, check_type: str, level: str = "error") -> bool:
    return any(issue.check_type == check_type and issue.level == level for issue in report.issues)
