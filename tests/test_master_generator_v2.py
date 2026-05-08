from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.financial_realism_profiles import get_financial_profile
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "input" / "procurement_v2_metadata.xlsx"
PLAN_PATH = ROOT / "input" / "sample_generation_plan_v2_valid.json"
ARTIFICIAL_SUFFIX_PATTERN = re.compile(r"^\s*(Supplier|Vendor|Material|Component|Warehouse|Plant)\s+[1-9][0-9]?\s*$", re.IGNORECASE)


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


def test_plant_row_count_is_3(generated_v2_master) -> None:
    assert len(generated_v2_master["Plant"]) == 3


def test_warehouse_row_count_is_9(generated_v2_master) -> None:
    assert len(generated_v2_master["Warehouse"]) == 9


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
