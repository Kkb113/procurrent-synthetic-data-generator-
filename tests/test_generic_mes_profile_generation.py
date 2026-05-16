from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.shared.industry_profiles import get_industry_profile, validate_industry_profile
from procurement_data_generator.modules.shared.operating_scope import get_default_shift_code, get_expected_plant_count, get_expected_warehouse_count


ROOT = Path(__file__).resolve().parents[1]
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


def test_generic_mes_profile_validates() -> None:
    result = validate_industry_profile(get_industry_profile("generic_mes"))

    assert result.valid
    assert result.errors == []


def test_procurement_master_generation_uses_generic_mes_profile() -> None:
    dataframes, report = _generate_procurement_master(profile_id="generic_mes")

    assert report.is_valid
    assert set(dataframes) == {"SupplierMaster", "ComponentMaster", "Plant", "Warehouse", "SupplierComponent"}
    assert len(dataframes["Plant"]) == get_expected_plant_count()
    assert len(dataframes["Warehouse"]) == get_expected_warehouse_count()
    assert "Battery" not in set(dataframes["ComponentMaster"]["ComponentCategory"])
    _assert_ev_only_terms_absent(
        dataframes["ComponentMaster"],
        ["ComponentName", "ComponentCategory"],
    )
    _assert_ev_only_terms_absent(dataframes["SupplierMaster"], ["SupplierName"])


def test_production_master_generation_uses_generic_mes_profile(tmp_path: Path) -> None:
    upstream_folder = tmp_path / "generic_procurement_master"
    procurement_dataframes, procurement_report = _generate_procurement_master(profile_id="generic_mes")
    assert procurement_report.is_valid
    ProcurementMasterDataGenerator(profile_id="generic_mes").export_master_data(procurement_dataframes, upstream_folder)

    schema_result = load_metadata_schema(PRODUCTION_METADATA)
    plan_result = load_llm_plan_json(PRODUCTION_PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None

    dataframes, report = ProductionMasterDataGenerator(profile_id="generic_mes").generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
        upstream_data_folder=upstream_folder,
    )

    assert report.is_valid
    assert set(dataframes) == {"ProductMaster", "BOMHeader", "BOMLine", "WorkCenter", "RoutingHeader", "RoutingOperation", "ProductionShift"}
    assert set(dataframes["ProductionShift"]["ShiftCode"]) == {get_default_shift_code()}
    _assert_ev_only_terms_absent(dataframes["ProductMaster"], ["ProductName", "ProductCategory"])
    _assert_ev_only_terms_absent(dataframes["WorkCenter"], ["WorkCenterName", "LineName"])
    _assert_ev_only_terms_absent(dataframes["RoutingOperation"], ["OperationName"])


def test_default_ev_profile_generation_still_works() -> None:
    dataframes, report = _generate_procurement_master(profile_id=None)

    assert report.is_valid
    assert len(dataframes["Plant"]) == get_expected_plant_count()
    assert len(dataframes["Warehouse"]) == get_expected_warehouse_count()


def test_unknown_profile_id_fails_clearly() -> None:
    try:
        ProcurementMasterDataGenerator(profile_id="unknown_profile")
    except ValueError as exc:
        assert "Unknown industry profile" in str(exc)
    else:
        raise AssertionError("Unknown profile ID should fail clearly.")


def _generate_procurement_master(profile_id: str | None):
    schema_result = load_metadata_schema(PROCUREMENT_METADATA)
    plan_result = load_llm_plan_json(PROCUREMENT_PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None

    return ProcurementMasterDataGenerator(profile_id=profile_id).generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
        model_version="v2",
    )


def _assert_ev_only_terms_absent(dataframe: pd.DataFrame, columns: list[str]) -> None:
    text = " ".join(
        str(value)
        for column in columns
        for value in dataframe[column].dropna().tolist()
    )
    for term in EV_ONLY_TERMS:
        assert term.lower() not in text.lower()
