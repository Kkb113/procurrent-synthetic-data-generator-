from __future__ import annotations

import pandas as pd
import pytest

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.modules.procurement.data_quality import ProcurementDataQualityEngine, ProcurementReconciler
from procurement_data_generator.modules.procurement.validation_rules import (
    ProcurementGeneratedDataValidator,
    get_procurement_validation_rules,
)


@pytest.mark.unit
def test_procurement_validation_rules_are_module_owned() -> None:
    rules = get_procurement_validation_rules()

    assert "generic_metadata" in rules
    assert "procurement_v2_expected_tables" in rules
    assert "procurement_v2_quantity_precision" in rules


@pytest.mark.unit
def test_procurement_validator_preserves_v2_country_rule() -> None:
    data = {"SupplierMaster": pd.DataFrame({"SupplierID": [1], "SupplierCountry": ["Canada"]})}

    report = ProcurementGeneratedDataValidator().validate_dataset(data, _supplier_schema(), model_version="v2")

    assert _has_issue(report, "V2_USA_SUPPLIER_COUNTRY")


@pytest.mark.unit
def test_procurement_validator_uses_metadata_allowed_country_for_v2_rule() -> None:
    data = {"SupplierMaster": pd.DataFrame({"SupplierID": [1], "SupplierCountry": ["India"]})}

    report = ProcurementGeneratedDataValidator().validate_dataset(data, _supplier_schema(country_values=["India"]), model_version="v2")

    assert not _has_issue(report, "V2_USA_SUPPLIER_COUNTRY")


@pytest.mark.unit
def test_procurement_validator_preserves_v1_deprecation_behavior() -> None:
    data = {"SupplierMaster": pd.DataFrame({"SupplierID": [1], "SupplierCountry": ["USA"]})}

    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        ProcurementGeneratedDataValidator().validate_dataset(data, _supplier_schema(), model_version="v1")


@pytest.mark.unit
def test_procurement_data_quality_engine_uses_module_owned_components() -> None:
    engine = ProcurementDataQualityEngine()

    assert isinstance(engine.validator, ProcurementGeneratedDataValidator)
    assert isinstance(engine.reconciler, ProcurementReconciler)


def _supplier_schema(country_values: list[str] | None = None) -> SchemaContract:
    return SchemaContract(
        tables={
            "SupplierMaster": TableContract(
                table_name="SupplierMaster",
                process_order=1,
                area="Master",
                table_role="supplier_master",
                target_rows=1,
                columns=[
                    _col("SupplierID", "int", "sequence_id", "No", key_type="PK"),
                    _col("SupplierCountry", "varchar(80)", "category", "No", allowed_values=country_values),
                ],
            )
        }
    )


def _col(
    column_name: str,
    data_type: str,
    generation_type: str,
    nullable: str,
    key_type: str | None = None,
    allowed_values: list[str] | None = None,
) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type=data_type,
        key_type=key_type,
        nullable=nullable,
        generation_type=generation_type,
        allowed_values=allowed_values or [],
        formula=None,
    )


def _has_issue(report, check_type: str, level: str = "error") -> bool:
    return any(issue.check_type == check_type and issue.level == level for issue in report.issues)
