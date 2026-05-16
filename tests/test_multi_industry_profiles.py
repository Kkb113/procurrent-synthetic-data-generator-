from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
import pytest

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.shared.industry_profiles import (
    EV_MANUFACTURING_PROFILE,
    GENERIC_MES_PROFILE,
    IndustryProfile,
    load_industry_profile_from_dict,
    load_industry_profile_from_json,
    validate_industry_profile,
)
from procurement_data_generator.modules.shared.operating_scope import get_default_shift_code, get_expected_plant_count, get_expected_warehouse_count


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "industry_profiles"
PROCUREMENT_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PRODUCTION_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PRODUCTION_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
EV_ONLY_TERMS = (
    "EV",
    "Battery Pack",
    "Charging Module",
    "High Voltage",
    "Drive Motor",
    "Power Electronics",
    "Thermal Management Unit",
)


@pytest.fixture(scope="module")
def procurement_schema_and_plan():
    schema_result = load_metadata_schema(PROCUREMENT_METADATA)
    plan_result = load_llm_plan_json(PROCUREMENT_PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    return schema_result.schema, plan_result.plan


@pytest.fixture(scope="module")
def production_schema_and_plan():
    schema_result = load_metadata_schema(PRODUCTION_METADATA)
    plan_result = load_llm_plan_json(PRODUCTION_PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    return schema_result.schema, plan_result.plan


@pytest.fixture(scope="module")
def profiles() -> dict[str, IndustryProfile]:
    return {
        "ev_manufacturing": EV_MANUFACTURING_PROFILE,
        "generic_mes": GENERIC_MES_PROFILE,
        "food_manufacturing": load_industry_profile_from_json(FIXTURE_DIR / "food_manufacturing_profile.json"),
        "pharma_manufacturing": load_industry_profile_from_json(FIXTURE_DIR / "pharma_manufacturing_profile.json"),
        "electronics_manufacturing": load_industry_profile_from_json(FIXTURE_DIR / "electronics_manufacturing_profile.json"),
    }


def test_all_static_and_fixture_profiles_validate(profiles: dict[str, IndustryProfile]) -> None:
    assert set(profiles) == {
        "ev_manufacturing",
        "generic_mes",
        "food_manufacturing",
        "pharma_manufacturing",
        "electronics_manufacturing",
    }
    for profile in profiles.values():
        result = validate_industry_profile(profile)
        assert result.valid, result.errors
        assert profile.procurement.component_categories
        assert profile.production.product_categories
        assert profile.production.work_center_names
        assert profile.production.routing_operation_names
        assert profile.production.quality_defect_codes
        assert profile.shared.countable_uoms
        assert profile.shared.measurable_uoms


@pytest.mark.parametrize("profile_id", ["ev_manufacturing", "generic_mes", "food_manufacturing", "pharma_manufacturing", "electronics_manufacturing"])
def test_procurement_master_generation_works_for_profile(
    profile_id: str,
    profiles: dict[str, IndustryProfile],
    procurement_schema_and_plan,
) -> None:
    schema, plan = procurement_schema_and_plan
    dataframes, report = ProcurementMasterDataGenerator(industry_profile=profiles[profile_id]).generate_master_data(
        schema,
        plan,
        seed=42,
        model_version="v2",
    )

    assert report.is_valid, [error.message for error in report.errors]
    assert set(dataframes) == {"SupplierMaster", "ComponentMaster", "Plant", "Warehouse", "SupplierComponent"}
    assert len(dataframes["Plant"]) == get_expected_plant_count()
    assert len(dataframes["Warehouse"]) == get_expected_warehouse_count()
    assert set(dataframes["Warehouse"]["PlantID"]) == set(dataframes["Plant"]["PlantID"])
    assert not dataframes["SupplierMaster"].empty
    assert not dataframes["ComponentMaster"].empty
    assert not dataframes["SupplierComponent"].empty
    if profile_id != "ev_manufacturing":
        _assert_ev_only_terms_absent(dataframes["SupplierMaster"], ["SupplierName"])
        _assert_ev_only_terms_absent(dataframes["ComponentMaster"], ["ComponentName", "ComponentCategory"])


@pytest.mark.parametrize("profile_id", ["ev_manufacturing", "generic_mes", "food_manufacturing", "pharma_manufacturing", "electronics_manufacturing"])
def test_production_master_generation_works_for_profile(
    profile_id: str,
    profiles: dict[str, IndustryProfile],
    procurement_schema_and_plan,
    production_schema_and_plan,
    tmp_path: Path,
) -> None:
    procurement_schema, procurement_plan = procurement_schema_and_plan
    procurement_dataframes, procurement_report = ProcurementMasterDataGenerator(industry_profile=profiles[profile_id]).generate_master_data(
        procurement_schema,
        procurement_plan,
        seed=42,
        model_version="v2",
    )
    assert procurement_report.is_valid
    upstream_folder = tmp_path / f"{profile_id}_procurement_master"
    ProcurementMasterDataGenerator(industry_profile=profiles[profile_id]).export_master_data(procurement_dataframes, upstream_folder)

    production_schema, production_plan = production_schema_and_plan
    dataframes, report = ProductionMasterDataGenerator(industry_profile=profiles[profile_id]).generate_master_data(
        production_schema,
        production_plan,
        seed=42,
        upstream_data_folder=upstream_folder,
    )

    assert report.is_valid, [error.message for error in report.errors]
    assert set(dataframes) == {"ProductMaster", "BOMHeader", "BOMLine", "WorkCenter", "RoutingHeader", "RoutingOperation", "ProductionShift"}
    assert len(dataframes["WorkCenter"]) > get_expected_plant_count()
    assert set(dataframes["ProductionShift"]["ShiftCode"]) == {get_default_shift_code()}
    assert set(dataframes["BOMHeader"]["ProductID"]).issubset(set(dataframes["ProductMaster"]["ProductID"]))
    assert set(dataframes["BOMLine"]["BOMID"]).issubset(set(dataframes["BOMHeader"]["BOMID"]))
    assert set(dataframes["RoutingOperation"]["RoutingID"]).issubset(set(dataframes["RoutingHeader"]["RoutingID"]))
    if profile_id != "ev_manufacturing":
        _assert_ev_only_terms_absent(dataframes["ProductMaster"], ["ProductName", "ProductCategory"])
        _assert_ev_only_terms_absent(dataframes["WorkCenter"], ["WorkCenterName", "LineName"])
        _assert_ev_only_terms_absent(dataframes["RoutingOperation"], ["OperationName"])


def test_unknown_or_bad_profile_fails_validation() -> None:
    result = validate_industry_profile({"industry_id": "", "industry_name": "Bad"})
    assert not result.valid

    with pytest.raises(ValueError, match="Industry profile validation failed"):
        load_industry_profile_from_dict({"industry_id": "bad", "industry_name": "Bad"})


def test_multi_industry_tests_do_not_use_azure_openai() -> None:
    assert "Azure" + "OpenAIClient" not in globals()
    assert "AZURE" + "_OPENAI_API_KEY" not in globals()
    assert "generate" + "_industry_profile" not in globals()


def _assert_ev_only_terms_absent(dataframe: pd.DataFrame, columns: list[str]) -> None:
    text = " ".join(
        str(value)
        for column in columns
        for value in dataframe[column].dropna().tolist()
    )
    for term in EV_ONLY_TERMS:
        if term == "EV":
            assert re.search(r"(?<![A-Za-z])EV(?![A-Za-z])", text, flags=re.IGNORECASE) is None
        else:
            assert term.lower() not in text.lower()
