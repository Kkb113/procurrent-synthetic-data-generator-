from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.financial_realism_profiles import get_financial_profile
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.shared.industry_profiles import EV_MANUFACTURING_PROFILE, get_default_industry_profile
from procurement_data_generator.modules.shared.operating_scope import (
    get_expected_plant_count,
    get_expected_warehouse_count,
)


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "input" / "procurement_v2_metadata.xlsx"
PLAN_PATH = ROOT / "input" / "sample_generation_plan_v2_valid.json"
ARTIFICIAL_SUFFIX_PATTERN = re.compile(r"^\s*(Supplier|Component|Warehouse|Plant)\s+[1-9][0-9]?\s*$", re.IGNORECASE)


@pytest.fixture(scope="module")
def generated_v2_master():
    schema_result = load_metadata_schema(METADATA_PATH)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None
    plan_result = load_llm_plan_json(PLAN_PATH)
    assert plan_result.report.is_valid
    assert plan_result.plan is not None

    dataframes, report = ProcurementMasterDataGenerator().generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
        model_version="v2",
    )
    assert report.is_valid, [issue.message for issue in report.errors]
    return dataframes


def test_v2_master_generator_creates_exactly_5_tables(generated_v2_master) -> None:
    assert set(generated_v2_master) == {"SupplierMaster", "ComponentMaster", "Plant", "Warehouse", "SupplierComponent"}


def test_supplier_master_row_count_is_80(generated_v2_master) -> None:
    assert len(generated_v2_master["SupplierMaster"]) == 80


def test_component_master_row_count_is_300(generated_v2_master) -> None:
    assert len(generated_v2_master["ComponentMaster"]) == 300


def test_component_categories_come_from_default_ev_profile(generated_v2_master) -> None:
    profile_categories = set(get_default_industry_profile().procurement.component_category_codes)

    assert set(generated_v2_master["ComponentMaster"]["ComponentCategory"]).issubset(profile_categories)


def test_plant_row_count_uses_shared_operating_scope(generated_v2_master) -> None:
    assert len(generated_v2_master["Plant"]) == get_expected_plant_count()


def test_plant_names_use_default_ev_profile_plant_types(generated_v2_master) -> None:
    plant_types = get_default_industry_profile().procurement.plant_type_names

    assert all(any(plant_type in plant_name for plant_type in plant_types) for plant_name in generated_v2_master["Plant"]["PlantName"])


def test_warehouse_row_count_uses_shared_operating_scope(generated_v2_master) -> None:
    assert len(generated_v2_master["Warehouse"]) == get_expected_warehouse_count()


def test_supplier_component_row_count_is_450(generated_v2_master) -> None:
    assert len(generated_v2_master["SupplierComponent"]) == 450


def test_supplier_master_pk_unique_and_non_null(generated_v2_master) -> None:
    series = generated_v2_master["SupplierMaster"]["SupplierID"]
    assert series.notna().all()
    assert series.is_unique


def test_component_master_pk_unique_and_non_null(generated_v2_master) -> None:
    series = generated_v2_master["ComponentMaster"]["ComponentID"]
    assert series.notna().all()
    assert series.is_unique


def test_warehouse_plant_fk_references_plant(generated_v2_master) -> None:
    assert set(generated_v2_master["Warehouse"]["PlantID"]).issubset(set(generated_v2_master["Plant"]["PlantID"]))
    assert set(generated_v2_master["Warehouse"]["PlantID"]) == set(generated_v2_master["Plant"]["PlantID"])


def test_supplier_component_supplier_fk_references_supplier(generated_v2_master) -> None:
    assert set(generated_v2_master["SupplierComponent"]["SupplierID"]).issubset(set(generated_v2_master["SupplierMaster"]["SupplierID"]))


def test_supplier_component_component_fk_references_component(generated_v2_master) -> None:
    assert set(generated_v2_master["SupplierComponent"]["ComponentID"]).issubset(set(generated_v2_master["ComponentMaster"]["ComponentID"]))


def test_supplier_component_has_no_duplicate_supplier_component_pairs(generated_v2_master) -> None:
    assert not generated_v2_master["SupplierComponent"].duplicated(["SupplierID", "ComponentID"]).any()


def test_every_component_has_at_least_one_supplier(generated_v2_master) -> None:
    mapped = set(generated_v2_master["SupplierComponent"]["ComponentID"])
    components = set(generated_v2_master["ComponentMaster"]["ComponentID"])
    assert components.issubset(mapped)


def test_preferred_supplier_at_most_one_per_component(generated_v2_master) -> None:
    preferred_counts = generated_v2_master["SupplierComponent"].groupby("ComponentID")["PreferredSupplierFlag"].sum()
    assert (preferred_counts <= 1).all()


def test_supplier_names_are_unique(generated_v2_master) -> None:
    assert generated_v2_master["SupplierMaster"]["SupplierName"].is_unique


def test_component_names_are_unique(generated_v2_master) -> None:
    assert generated_v2_master["ComponentMaster"]["ComponentName"].is_unique


def test_warehouse_names_are_unique(generated_v2_master) -> None:
    assert generated_v2_master["Warehouse"]["WarehouseName"].is_unique


def test_warehouse_location_matches_assigned_plant(generated_v2_master) -> None:
    plant_lookup = generated_v2_master["Plant"].set_index("PlantID")[["PlantCity", "PlantState", "PlantZipCode"]]
    for _, warehouse in generated_v2_master["Warehouse"].iterrows():
        plant = plant_lookup.loc[warehouse["PlantID"]]
        assert warehouse["WarehouseCity"] == plant["PlantCity"]
        assert warehouse["WarehouseState"] == plant["PlantState"]
        assert str(warehouse["WarehouseZipCode"]) == str(plant["PlantZipCode"])


def test_country_columns_are_usa(generated_v2_master) -> None:
    assert set(generated_v2_master["SupplierMaster"]["SupplierCountry"]) == {"USA"}
    assert set(generated_v2_master["Plant"]["PlantCountry"]) == {"USA"}
    assert set(generated_v2_master["Warehouse"]["WarehouseCountry"]) == {"USA"}


def test_currency_columns_are_usd(generated_v2_master) -> None:
    assert set(generated_v2_master["ComponentMaster"]["CurrencyCode"]) == {"USD"}
    assert set(generated_v2_master["SupplierComponent"]["CurrencyCode"]) == {"USD"}


def test_status_columns_have_variety(generated_v2_master) -> None:
    checks = [
        ("SupplierMaster", "Status"),
        ("ComponentMaster", "Status"),
        ("Plant", "Status"),
        ("Warehouse", "Status"),
        ("SupplierComponent", "Status"),
    ]
    for table_name, column_name in checks:
        if len(generated_v2_master[table_name]) > 1:
            assert generated_v2_master[table_name][column_name].nunique() > 1


def test_no_artificial_numeric_suffix_in_true_name_columns(generated_v2_master) -> None:
    for table_name, column_name in [
        ("SupplierMaster", "SupplierName"),
        ("ComponentMaster", "ComponentName"),
        ("Plant", "PlantName"),
        ("Warehouse", "WarehouseName"),
    ]:
        assert not any(ARTIFICIAL_SUFFIX_PATTERN.match(str(value)) for value in generated_v2_master[table_name][column_name])


def test_contract_price_is_related_to_component_standard_cost(generated_v2_master) -> None:
    component_cost = generated_v2_master["ComponentMaster"].set_index("ComponentID")["StandardCost"].astype(float)
    merged = generated_v2_master["SupplierComponent"].join(component_cost, on="ComponentID")
    ratio = merged["ContractPrice"].astype(float) / merged["StandardCost"].astype(float)
    assert ratio.between(0.9, 1.25).all()


def test_component_standard_cost_respects_category_financial_profiles(generated_v2_master) -> None:
    components = generated_v2_master["ComponentMaster"]
    for row in components.itertuples(index=False):
        profile = get_financial_profile(row.ComponentCategory)
        assert profile["unit_price_min"] <= float(row.StandardCost) <= profile["unit_price_max"]


def test_ev_component_standard_cost_respects_metadata_numeric_bounds(generated_v2_master) -> None:
    minimum, maximum = _metadata_numeric_bounds("ComponentMaster", "StandardCost")
    standard_cost = generated_v2_master["ComponentMaster"]["StandardCost"].astype(float)

    assert standard_cost.ge(minimum).all()
    assert standard_cost.le(maximum).all()


def test_low_cost_ev_component_categories_are_clamped_to_metadata_bounds(tmp_path: Path) -> None:
    metadata_path = tmp_path / "low_cost_ev_procurement_metadata.xlsx"
    metadata = pd.read_excel(METADATA_PATH, sheet_name="Metadata", engine="openpyxl", dtype=object)
    metadata.loc[
        (metadata["TableName"] == "ComponentMaster") & (metadata["ColumnName"] == "ComponentCategory"),
        "AllowedValues",
    ] = "Fasteners,Packaging"
    with pd.ExcelWriter(metadata_path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)

    low_cost_profile = replace(
        EV_MANUFACTURING_PROFILE,
        procurement=replace(
            EV_MANUFACTURING_PROFILE.procurement,
            component_categories=("Fasteners", "Packaging"),
            component_category_codes=("Fasteners", "Packaging"),
            component_material_examples={
                "Fasteners": ("M4 Bolt", "Panel Clip", "Retaining Washer", "Harness Screw"),
                "Packaging": ("Protective Sleeve", "Carton Insert", "Foam Separator", "Label Pack"),
            },
            component_specification_patterns={
                "Fasteners": ("Zinc Plated", "Grade 8.8", "M6", "M8"),
                "Packaging": ("Reusable", "Printed", "Standard Pack", "ESD Safe"),
            },
            component_financial_profiles={
                "Fasteners": {
                    "unit_price_min": 0.05,
                    "unit_price_max": 0.75,
                    "quantity_min": 100.0,
                    "quantity_max": 5000.0,
                    "line_amount_soft_max": 50000.0,
                    "high_value_probability": 0.0,
                },
                "Packaging": {
                    "unit_price_min": 0.10,
                    "unit_price_max": 0.90,
                    "quantity_min": 100.0,
                    "quantity_max": 5000.0,
                    "line_amount_soft_max": 50000.0,
                    "high_value_probability": 0.0,
                },
            },
            component_category_aliases={
                **EV_MANUFACTURING_PROFILE.procurement.component_category_aliases,
                "fastener": "Fasteners",
                "packaging": "Packaging",
            },
        ),
    )
    schema, plan = _schema_and_plan(metadata_path, PLAN_PATH)

    dataframes, report = ProcurementMasterDataGenerator(industry_profile=low_cost_profile).generate_master_data(
        schema,
        plan,
        seed=42,
        model_version="v2",
    )

    assert report.is_valid, [(error.table_name, error.column_name, error.message) for error in report.errors]
    components = dataframes["ComponentMaster"]
    standard_cost = components["StandardCost"].astype(float)
    minimum, maximum = _metadata_numeric_bounds("ComponentMaster", "StandardCost", metadata_path=metadata_path)

    assert {"Fasteners", "Packaging"}.issubset(set(components["ComponentCategory"]))
    assert standard_cost.ge(minimum).all()
    assert standard_cost.le(maximum).all()
    assert standard_cost.min() == minimum


def test_low_value_component_categories_have_lower_average_standard_cost(generated_v2_master) -> None:
    components = generated_v2_master["ComponentMaster"].copy()
    components["StandardCost"] = components["StandardCost"].astype(float)
    low_value_average = components[components["ComponentCategory"].isin(["Packaging", "Maintenance"])]["StandardCost"].mean()
    high_value_average = components[components["ComponentCategory"].isin(["Battery", "Electrical", "Electronics"])]["StandardCost"].mean()

    assert low_value_average < high_value_average


def test_maintenance_spares_standard_cost_is_moderate(generated_v2_master) -> None:
    components = generated_v2_master["ComponentMaster"].copy()
    maintenance = components[components["ComponentCategory"] == "Maintenance"]["StandardCost"].astype(float)

    assert not maintenance.empty
    assert maintenance.mean() < 450.0
    assert maintenance.max() <= get_financial_profile("Maintenance")["unit_price_max"]


def test_same_seed_gives_deterministic_v2_master_output() -> None:
    first = _generate(seed=42)
    second = _generate(seed=42)
    for table_name in first:
        pdt.assert_frame_equal(first[table_name], second[table_name])


def test_different_seed_changes_some_v2_master_values() -> None:
    first = _generate(seed=42)
    second = _generate(seed=99)
    assert any(not first[table_name].equals(second[table_name]) for table_name in first)


def test_v2_master_generation_has_no_validation_errors(generated_v2_master) -> None:
    assert all(isinstance(dataframe, pd.DataFrame) for dataframe in generated_v2_master.values())


def _generate(seed: int):
    schema_result = load_metadata_schema(METADATA_PATH)
    plan_result = load_llm_plan_json(PLAN_PATH)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    dataframes, report = ProcurementMasterDataGenerator().generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=seed,
        model_version="v2",
    )
    assert report.is_valid, [issue.message for issue in report.errors]
    return dataframes


def _schema_and_plan(metadata_path: Path, plan_path: Path):
    schema_result = load_metadata_schema(metadata_path)
    plan_result = load_llm_plan_json(plan_path)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    return schema_result.schema, plan_result.plan


def _metadata_numeric_bounds(table_name: str, column_name: str, metadata_path: Path = METADATA_PATH) -> tuple[float, float]:
    metadata = pd.read_excel(metadata_path, sheet_name="Metadata", engine="openpyxl", dtype=object)
    row = metadata[(metadata["TableName"] == table_name) & (metadata["ColumnName"] == column_name)].iloc[0]
    return float(row["MinValue"]), float(row["MaxValue"])
