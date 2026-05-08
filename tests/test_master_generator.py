from __future__ import annotations

import re

import pandas as pd
import pandas.testing as pdt

from procurement_data_generator.core.contracts.llm_plan_contract import DomainProfile, LLMGenerationPlan, MaterialCategory
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator


ARTIFICIAL_SUFFIX_PATTERN = re.compile(r"\s(?:[1-9]|[1-9][0-9])$")


def test_generates_exactly_four_master_tables_by_role() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert set(dataframes) == {"Vendor", "RawMaterial", "Plant", "Warehouse"}


def test_row_counts_match_plan_target_rows() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert len(dataframes["Vendor"]) == 5
    assert len(dataframes["RawMaterial"]) == 8
    assert len(dataframes["Plant"]) == 2
    assert len(dataframes["Warehouse"]) == 4


def test_primary_keys_are_unique_and_non_null() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    for table_name, pk_name in {"Vendor": "VendorID", "RawMaterial": "RawMaterialID", "Plant": "PlantID", "Warehouse": "WarehouseID"}.items():
        series = dataframes[table_name][pk_name]
        assert series.notna().all()
        assert series.is_unique


def test_warehouse_plant_fk_references_valid_plant_pk() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert set(dataframes["Warehouse"]["PlantID"]).issubset(set(dataframes["Plant"]["PlantID"]))


def test_warehouse_name_location_matches_assigned_plant_name_location() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    plant_lookup = dict(zip(dataframes["Plant"]["PlantID"], dataframes["Plant"]["PlantName"]))
    for _, warehouse in dataframes["Warehouse"].iterrows():
        plant_name = plant_lookup[warehouse["PlantID"]]
        plant_location = plant_name.split()[0]
        assert warehouse["WarehouseName"].startswith(f"{plant_location} ")


def test_vendor_names_are_unique() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert dataframes["Vendor"]["VendorName"].is_unique


def test_material_names_are_unique() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert dataframes["RawMaterial"]["RawMaterialName"].is_unique


def test_plant_names_are_unique() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert dataframes["Plant"]["PlantName"].is_unique


def test_warehouse_names_are_unique() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert dataframes["Warehouse"]["WarehouseName"].is_unique


def test_allowed_values_are_respected_for_category_and_status() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert set(dataframes["Vendor"]["VendorCategory"]).issubset({"Battery", "Metal", "Electronics"})
    assert set(dataframes["Vendor"]["Status"]).issubset({"Active", "Inactive"})


def test_numeric_range_values_respect_min_max() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    assert dataframes["Vendor"]["LeadTimeDays"].between(3, 45).all()
    assert dataframes["RawMaterial"]["StandardCost"].between(10.0, 250.0).all()


def test_date_range_values_respect_min_max() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    dates = pd.to_datetime(dataframes["Plant"]["StartDate"])
    assert (dates >= pd.Timestamp("2025-01-01")).all()
    assert (dates <= pd.Timestamp("2025-01-31")).all()


def test_nullable_no_columns_contain_no_nulls() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    for dataframe in dataframes.values():
        assert not dataframe.isna().any().any()


def test_no_artificial_numeric_suffixes_in_generated_names() -> None:
    dataframes, report = _generate()

    assert report.is_valid
    name_values = []
    for dataframe in dataframes.values():
        for column_name in dataframe.columns:
            if "name" in column_name.lower():
                name_values.extend(str(value) for value in dataframe[column_name])
    assert not any(ARTIFICIAL_SUFFIX_PATTERN.search(value) for value in name_values)


def test_same_seed_produces_same_generated_master_data() -> None:
    first, first_report = _generate(seed=42)
    second, second_report = _generate(seed=42)

    assert first_report.is_valid
    assert second_report.is_valid
    for table_name in first:
        pdt.assert_frame_equal(first[table_name], second[table_name])


def test_different_seed_changes_some_generated_values() -> None:
    first, first_report = _generate(seed=42)
    second, second_report = _generate(seed=99)

    assert first_report.is_valid
    assert second_report.is_valid
    assert not first["Vendor"].equals(second["Vendor"])


def test_missing_parent_fk_table_returns_error() -> None:
    schema = SchemaContract(tables={"Warehouse": _schema().tables["Warehouse"]})
    dataframes, report = ProcurementMasterDataGenerator().generate_master_data(schema, _plan(), seed=42)

    assert "Warehouse" in dataframes
    assert not report.is_valid
    assert any("Parent table Plant.PlantID is not generated yet" in issue.message for issue in report.errors)


def test_unsupported_non_null_generation_type_returns_error() -> None:
    schema = _schema()
    vendor = schema.tables["Vendor"]
    bad_column = vendor.columns[1].model_copy(update={"generation_type": "unsupported_kind", "column_name": "UnsupportedColumn"})
    schema.tables["Vendor"] = vendor.model_copy(update={"columns": [vendor.columns[0], bad_column]})

    _, report = ProcurementMasterDataGenerator().generate_master_data(schema, _plan(), seed=42)

    assert not report.is_valid
    assert any("unsupported" in issue.message.lower() for issue in report.errors)


def test_payment_terms_net_30_does_not_trigger_artificial_suffix_validation() -> None:
    schema = _single_table_schema(
        "Vendor",
        "vendor_dimension",
        [
            _col("VendorID", "int", "sequence_id", "No", key_type="PK"),
            _col("PaymentTerms", "varchar(20)", "category", "No"),
        ],
    )
    dataframe = pd.DataFrame({"VendorID": [1], "PaymentTerms": ["Net 30"]})
    report = ValidationReport()

    ProcurementMasterDataGenerator().validate_generated_master_data({"Vendor": dataframe}, schema, _single_table_plan("Vendor"), report)

    assert report.is_valid


def test_vendor_name_vendor_1_triggers_artificial_suffix_validation() -> None:
    schema = _single_table_schema(
        "Vendor",
        "vendor_dimension",
        [
            _col("VendorID", "int", "sequence_id", "No", key_type="PK"),
            _col("VendorName", "varchar(200)", "vendor_name", "No"),
        ],
    )
    dataframe = pd.DataFrame({"VendorID": [1], "VendorName": ["Vendor 1"]})
    report = ValidationReport()

    ProcurementMasterDataGenerator().validate_generated_master_data({"Vendor": dataframe}, schema, _single_table_plan("Vendor"), report)

    assert not report.is_valid
    assert any("artificial numeric suffix" in issue.message for issue in report.errors)


def test_material_name_with_real_spec_number_passes_artificial_suffix_validation() -> None:
    schema = _single_table_schema(
        "RawMaterial",
        "material_dimension",
        [
            _col("RawMaterialID", "int", "sequence_id", "No", key_type="PK"),
            _col("MaterialName", "varchar(200)", "material_name", "No"),
        ],
    )
    dataframe = pd.DataFrame({"RawMaterialID": [1], "MaterialName": ["Lithium-Ion Cell 21700"]})
    report = ValidationReport()

    ProcurementMasterDataGenerator().validate_generated_master_data({"RawMaterial": dataframe}, schema, _single_table_plan("RawMaterial"), report)

    assert report.is_valid


def test_raw_material_name_material_2_triggers_artificial_suffix_validation() -> None:
    schema = _single_table_schema(
        "RawMaterial",
        "material_dimension",
        [
            _col("RawMaterialID", "int", "sequence_id", "No", key_type="PK"),
            _col("RawMaterialName", "varchar(200)", "material_name", "No"),
        ],
    )
    dataframe = pd.DataFrame({"RawMaterialID": [1], "RawMaterialName": ["Material 2"]})
    report = ValidationReport()

    ProcurementMasterDataGenerator().validate_generated_master_data({"RawMaterial": dataframe}, schema, _single_table_plan("RawMaterial"), report)

    assert not report.is_valid
    assert any("artificial numeric suffix" in issue.message for issue in report.errors)


def test_warehouse_type_quality_hold_1_is_not_checked_as_name_column() -> None:
    schema = _single_table_schema(
        "Warehouse",
        "warehouse_dimension",
        [
            _col("WarehouseID", "int", "sequence_id", "No", key_type="PK"),
            _col("WarehouseType", "varchar(50)", "category", "No"),
        ],
    )
    dataframe = pd.DataFrame({"WarehouseID": [1], "WarehouseType": ["Quality Hold 1"]})
    report = ValidationReport()

    ProcurementMasterDataGenerator().validate_generated_master_data({"Warehouse": dataframe}, schema, _single_table_plan("Warehouse"), report)

    assert report.is_valid


def _generate(seed: int = 42):
    return ProcurementMasterDataGenerator().generate_master_data(_schema(), _plan(), seed=seed)


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "Vendor": TableContract(
                table_name="Vendor",
                process_order=1,
                area="Master",
                table_role="vendor_dimension",
                target_rows=5,
                columns=[
                    _col("VendorID", "int", "sequence_id", "No", key_type="PK"),
                    _col("VendorName", "varchar(200)", "vendor_name", "No"),
                    _col("VendorCategory", "varchar(50)", "category", "No", allowed_values=["Battery", "Metal", "Electronics"]),
                    _col("ContactPerson", "varchar(100)", "faker_person", "No"),
                    _col("LeadTimeDays", "int", "integer_range", "No", min_value=3, max_value=45),
                    _col("Status", "varchar(20)", "status", "No", allowed_values=["Active", "Inactive"]),
                ],
            ),
            "RawMaterial": TableContract(
                table_name="RawMaterial",
                process_order=2,
                area="Master",
                table_role="material_dimension",
                target_rows=8,
                columns=[
                    _col("RawMaterialID", "int", "sequence_id", "No", key_type="PK"),
                    _col("RawMaterialName", "varchar(200)", "material_name", "No"),
                    _col("MaterialCategory", "varchar(50)", "category", "No"),
                    _col("UOM", "varchar(20)", "category", "No", allowed_values=["PCS", "KG", "Litre"]),
                    _col("StandardCost", "decimal(18,2)", "decimal_range", "No", min_value=10.0, max_value=250.0),
                ],
            ),
            "Plant": TableContract(
                table_name="Plant",
                process_order=3,
                area="Master",
                table_role="plant_dimension",
                target_rows=2,
                columns=[
                    _col("PlantID", "int", "sequence_id", "No", key_type="PK"),
                    _col("PlantName", "varchar(200)", "plant_name", "No"),
                    _col("City", "varchar(100)", "faker_company", "No"),
                    _col("Country", "varchar(100)", "faker_company", "No"),
                    _col("StartDate", "date", "date_range", "No", min_value="2025-01-01", max_value="2025-01-31"),
                    _col("Status", "varchar(20)", "status", "No", allowed_values=["Active", "Inactive"]),
                ],
            ),
            "Warehouse": TableContract(
                table_name="Warehouse",
                process_order=4,
                area="Master",
                table_role="warehouse_dimension",
                target_rows=4,
                columns=[
                    _col("WarehouseID", "int", "sequence_id", "No", key_type="PK"),
                    _col("PlantID", "int", "foreign_key", "No", key_type="FK", related_table="Plant", related_column="PlantID"),
                    _col("WarehouseName", "varchar(200)", "warehouse_name", "No"),
                    _col("WarehouseType", "varchar(50)", "category", "No", allowed_values=["Raw Material", "Quality Hold"]),
                    _col("Status", "varchar(20)", "status", "No", allowed_values=["Active", "Inactive"]),
                ],
            ),
            "PurchaseOrderHeader": TableContract(
                table_name="PurchaseOrderHeader",
                process_order=5,
                area="Procurement",
                table_role="purchase_order_header",
                target_rows=2,
                columns=[
                    _col("PurchaseOrderID", "int", "sequence_id", "No", key_type="PK"),
                ],
            ),
        }
    )


def _plan() -> LLMGenerationPlan:
    return LLMGenerationPlan(
        module="procurement",
        business_summary="Master data generation test plan.",
        domain_profile=DomainProfile(
            industry="EV manufacturing",
            business_context="Procurement master data test.",
            vendor_categories=["Battery", "Metal", "Electronics"],
            material_categories=[
                MaterialCategory(
                    category_name="Battery Components",
                    material_examples=["Lithium-Ion Cell", "Battery PCB", "Thermal Pad", "Copper Busbar"],
                    specification_patterns=["21700", "Prismatic", "Grade A", "2mm"],
                )
            ],
            warehouse_types=["Raw Material", "Quality Hold"],
            plant_locations=["Bengaluru", "Pune"],
            carrier_name_patterns=[],
            inspection_test_categories=[],
        ),
        table_role_mapping=[],
        generation_order=["Vendor", "RawMaterial", "Plant", "Warehouse"],
        row_count_plan=[
            {"table_name": "Vendor", "target_rows": 5, "source": "metadata", "reasoning": None},
            {"table_name": "RawMaterial", "target_rows": 8, "source": "metadata", "reasoning": None},
            {"table_name": "Plant", "target_rows": 2, "source": "metadata", "reasoning": None},
            {"table_name": "Warehouse", "target_rows": 4, "source": "metadata", "reasoning": None},
        ],
        column_generation_rules=[],
        formula_rules=[],
        date_rules=[],
        quantity_rules=[],
        status_rules=[],
        validation_rules=[],
        assumptions=[],
        warnings=[],
    )


def _single_table_schema(table_name: str, table_role: str, columns: list[ColumnContract]) -> SchemaContract:
    area = {
        "vendor_dimension": "Master",
        "material_dimension": "Master",
        "warehouse_dimension": "Master",
        "plant_dimension": "Master",
    }[table_role]
    return SchemaContract(
        tables={
            table_name: TableContract(
                table_name=table_name,
                process_order=1,
                area=area,
                table_role=table_role,
                target_rows=1,
                columns=columns,
            )
        }
    )


def _single_table_plan(table_name: str) -> LLMGenerationPlan:
    return LLMGenerationPlan(
        module="procurement",
        business_summary="Single table validation test plan.",
        domain_profile=DomainProfile(industry="General manufacturing"),
        table_role_mapping=[],
        generation_order=[table_name],
        row_count_plan=[{"table_name": table_name, "target_rows": 1, "source": "metadata", "reasoning": None}],
        column_generation_rules=[],
        formula_rules=[],
        date_rules=[],
        quantity_rules=[],
        status_rules=[],
        validation_rules=[],
        assumptions=[],
        warnings=[],
    )


def _col(
    name: str,
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
        column_name=name,
        data_type=data_type,
        key_type=key_type,
        related_table=related_table,
        related_column=related_column,
        nullable=nullable,
        generation_type=generation_type,
        allowed_values=allowed_values or [],
        min_value=min_value,
        max_value=max_value,
    )
