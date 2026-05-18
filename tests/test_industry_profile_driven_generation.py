from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator
from procurement_data_generator.modules.shared.industry_profiles import GENERIC_MES_PROFILE, IndustryProfile, get_industry_profile


pytestmark = pytest.mark.integration


ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PRODUCTION_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PRODUCTION_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
FOOD_CONTEXT_TERMS = (
    "Ingredient",
    "Seasoning",
    "Edible Oil",
    "Packaging Film",
    "Carton",
    "Label",
    "Potato Chips",
    "Corn Snacks",
    "Roasted Snacks",
    "Snack Mix",
)
EV_CONTEXT_TERMS = (
    "EV",
    "Battery",
    "Automotive",
    "Chassis",
    "Drive Unit",
    "Drive Motor",
    "Power Electronics",
    "Thermal Runaway",
    "High Voltage",
    "Charging Module",
)


def test_procurement_master_generation_uses_custom_profile_vocabulary() -> None:
    profile = _custom_food_packaging_profile()
    schema, plan = _schema_and_plan(PROCUREMENT_METADATA, PROCUREMENT_PLAN)

    dataframes, report = ProcurementMasterDataGenerator(industry_profile=profile).generate_master_data(
        schema,
        plan,
        seed=42,
        model_version="v2",
    )

    assert report.is_valid, [error.message for error in report.errors]
    component_text = " ".join(dataframes["ComponentMaster"]["ComponentName"].astype(str))
    supplier_text = " ".join(dataframes["SupplierMaster"]["SupplierName"].astype(str))
    assert "Aseptic Pouch" in component_text or "Sterile Cap" in component_text
    assert "Food" in supplier_text or "Aseptic" in supplier_text
    assert set(dataframes["ComponentMaster"]["CurrencyCode"]) == {"USD"}
    assert set(dataframes["Plant"]["PlantCountry"]) == {"USA"}


def test_procurement_master_generation_is_deterministic_for_same_seed_and_profile() -> None:
    profile = _custom_food_packaging_profile()
    schema, plan = _schema_and_plan(PROCUREMENT_METADATA, PROCUREMENT_PLAN)
    generator = ProcurementMasterDataGenerator(industry_profile=profile)

    first, first_report = generator.generate_master_data(schema, plan, seed=42, model_version="v2")
    second, second_report = generator.generate_master_data(schema, plan, seed=42, model_version="v2")

    assert first_report.is_valid
    assert second_report.is_valid
    pd.testing.assert_frame_equal(first["ComponentMaster"], second["ComponentMaster"])
    pd.testing.assert_frame_equal(first["SupplierMaster"], second["SupplierMaster"])


def test_production_master_generation_uses_custom_profile_vocabulary(tmp_path: Path) -> None:
    profile = _custom_food_packaging_profile()
    procurement_schema, procurement_plan = _schema_and_plan(PROCUREMENT_METADATA, PROCUREMENT_PLAN)
    procurement_dataframes, procurement_report = ProcurementMasterDataGenerator(industry_profile=profile).generate_master_data(
        procurement_schema,
        procurement_plan,
        seed=42,
        model_version="v2",
    )
    assert procurement_report.is_valid
    upstream_folder = tmp_path / "custom_procurement_master"
    ProcurementMasterDataGenerator(industry_profile=profile).export_master_data(procurement_dataframes, upstream_folder)

    production_schema, production_plan = _schema_and_plan(PRODUCTION_METADATA, PRODUCTION_PLAN)
    dataframes, report = ProductionMasterDataGenerator(industry_profile=profile).generate_master_data(
        production_schema,
        production_plan,
        seed=42,
        upstream_data_folder=upstream_folder,
    )

    assert report.is_valid, [error.message for error in report.errors]
    assert "Shelf Stable Meal Kit" in set(dataframes["ProductMaster"]["ProductName"])
    assert "Thermal Processing" in set(dataframes["RoutingOperation"]["OperationName"])
    assert "Retort Line" in set(dataframes["WorkCenter"]["WorkCenterName"])


def test_production_transaction_policy_values_come_from_profile() -> None:
    profile = _custom_food_packaging_profile()
    generator = ProductionTransactionGenerator(industry_profile=profile)

    assert generator._scrap_reason_code(random.Random(1)) == "Seal Scrap"
    assert generator._rework_reason_code(random.Random(1)) == "Relabel"
    assert generator.profile_values.production_cost_range("ScrapCostPerUnit", (75.0, 250.0)) == (12.0, 18.0)


def test_procurement_quality_test_names_can_come_from_profile() -> None:
    profile = _custom_food_packaging_profile()
    _, plan = _schema_and_plan(PROCUREMENT_METADATA, PROCUREMENT_PLAN)
    generator = ProcurementTransactionGenerator(industry_profile=profile)

    tests = generator._profile_driven_inspection_test_names(10, plan, random.Random(42))

    assert tests == ["Seal Integrity Test", "Label Verification"]


def test_generation_config_profile_id_drives_procurement_and_production_food_vocabulary(tmp_path: Path) -> None:
    procurement_schema, procurement_plan = _schema_and_plan(
        _food_procurement_metadata(tmp_path),
        PROCUREMENT_PLAN,
    )
    config = GenerationConfig(seed=42, profile_id="food_manufacturing")
    procurement_dataframes, procurement_report = ProcurementMasterDataGenerator(generation_config=config).generate_master_data(
        procurement_schema,
        procurement_plan,
        seed=42,
        model_version="v2",
    )

    assert procurement_report.is_valid, [error.message for error in procurement_report.errors]
    procurement_food_rows = _context_row_count(
        procurement_dataframes["SupplierMaster"],
        ["SupplierName"],
        FOOD_CONTEXT_TERMS,
    ) + _context_row_count(
        procurement_dataframes["ComponentMaster"],
        ["ComponentName", "ComponentCategory"],
        FOOD_CONTEXT_TERMS,
    )
    procurement_ev_rows = _context_row_count(
        procurement_dataframes["SupplierMaster"],
        ["SupplierName"],
        EV_CONTEXT_TERMS,
    ) + _context_row_count(
        procurement_dataframes["ComponentMaster"],
        ["ComponentName", "ComponentCategory"],
        EV_CONTEXT_TERMS,
    )
    assert procurement_food_rows > 0
    assert procurement_ev_rows == 0

    upstream_folder = tmp_path / "food_procurement_master"
    ProcurementMasterDataGenerator(generation_config=config).export_master_data(procurement_dataframes, upstream_folder)
    production_schema, production_plan = _schema_and_plan(
        _food_production_metadata(tmp_path),
        PRODUCTION_PLAN,
    )
    production_dataframes, production_report = ProductionMasterDataGenerator(generation_config=config).generate_master_data(
        production_schema,
        production_plan,
        seed=42,
        upstream_data_folder=upstream_folder,
    )

    assert production_report.is_valid, [error.message for error in production_report.errors]
    production_food_rows = _context_row_count(
        production_dataframes["ProductMaster"],
        ["ProductName", "ProductCategory"],
        FOOD_CONTEXT_TERMS,
    )
    production_ev_rows = _context_row_count(
        production_dataframes["ProductMaster"],
        ["ProductName", "ProductCategory"],
        EV_CONTEXT_TERMS,
    )
    assert production_food_rows > 0
    assert production_ev_rows == 0


def test_default_ev_profile_still_loads_when_explicitly_selected() -> None:
    profile = get_industry_profile("ev_manufacturing")

    assert profile.industry_id == "ev_manufacturing"
    assert "Battery Components" in profile.procurement.component_categories


def _schema_and_plan(metadata_path: Path, plan_path: Path):
    schema_result = load_metadata_schema(metadata_path)
    plan_result = load_llm_plan_json(plan_path)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    return schema_result.schema, plan_result.plan


def _food_procurement_metadata(tmp_path: Path) -> Path:
    path = tmp_path / "food_procurement_metadata.xlsx"
    metadata = pd.read_excel(PROCUREMENT_METADATA, sheet_name="Metadata", engine="openpyxl", dtype=object)
    _set_allowed(metadata, "SupplierMaster", "SupplierCountry", "India")
    _set_allowed(metadata, "Plant", "PlantCountry", "India")
    _set_allowed(metadata, "Warehouse", "WarehouseCountry", "India")
    _set_allowed(metadata, "ComponentMaster", "CurrencyCode", "INR")
    _set_allowed(metadata, "SupplierComponent", "CurrencyCode", "INR")
    _set_allowed(
        metadata,
        "ComponentMaster",
        "ComponentCategory",
        "Raw Ingredients,Seasonings & Spices,Edible Oils,Packaging Film,Labels,Cartons,Cleaning Consumables,Food Safety",
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)
    return path


def _food_production_metadata(tmp_path: Path) -> Path:
    path = tmp_path / "food_production_metadata.xlsx"
    metadata = pd.read_excel(PRODUCTION_METADATA, sheet_name="Metadata", engine="openpyxl", dtype=object)
    _set_allowed(
        metadata,
        "ProductMaster",
        "ProductCategory",
        "Potato Chips,Corn Snacks,Roasted Snacks,Seasoned Snack Mix",
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)
    return path


def _set_allowed(metadata: pd.DataFrame, table_name: str, column_name: str, allowed_values: str) -> None:
    mask = (metadata["TableName"] == table_name) & (metadata["ColumnName"] == column_name)
    metadata.loc[mask, "AllowedValues"] = allowed_values


def _context_row_count(dataframe: pd.DataFrame, columns: list[str], terms: tuple[str, ...]) -> int:
    lowered_terms = tuple(term.lower() for term in terms)
    count = 0
    for _, row in dataframe.iterrows():
        row_text = " ".join(str(row[column]) for column in columns if column in dataframe.columns).lower()
        if any(term in row_text for term in lowered_terms):
            count += 1
    return count


def _custom_food_packaging_profile() -> IndustryProfile:
    return replace(
        GENERIC_MES_PROFILE,
        industry_id="test_food_packaging",
        industry_name="Test Food Packaging",
        industry_description="Deterministic test profile for packaged food generation.",
        procurement=replace(
            GENERIC_MES_PROFILE.procurement,
            supplier_name_patterns=("Aseptic Food Supply", "Packaging Food Partners"),
            component_categories=("Food Packaging", "Ingredients"),
            component_name_patterns=("Aseptic Pouch", "Sterile Cap"),
            component_category_codes=("Packaging", "Maintenance", "Mechanical", "Electrical"),
            component_material_examples={
                "Food Packaging": ("Aseptic Pouch", "Sterile Cap"),
            },
            component_specification_patterns={
                "Food Packaging": ("Food Safe", "Retort Grade"),
            },
            component_cost_profiles={
                "Packaging": (100.0, 300.0),
                "Food Packaging": (100.0, 300.0),
            },
            rejection_reasons=("Seal Failure", "Label Damage"),
            inspection_test_names=("Seal Integrity Test", "Label Verification"),
        ),
        production=replace(
            GENERIC_MES_PROFILE.production,
            product_catalog=(
                {
                    "name": "Shelf Stable Meal Kit",
                    "category": "Packaged Food",
                    "product_type": "FinishedGood",
                    "uom": "EA",
                    "base_cost": 14,
                    "base_hours": 1.1,
                },
            ),
            work_center_catalog=(
                {"name": "Retort Line", "line_name": "Retort"},
                {"name": "Labeling Cell", "line_name": "Labeling"},
            ),
            routing_operation_names=("Thermal Processing", "Label Verification"),
            scrap_reason_codes=("Seal Scrap",),
            rework_reason_codes=("Relabel",),
            quality_defect_codes=("SealFailure", "LabelDamage"),
            cost_profiles={
                "ProductionLaborCostPerOperation": (9.0, 11.0),
                "ProductionOverheadPct": (6.0, 8.0),
                "ScrapCostPerUnit": (12.0, 18.0),
                "ReworkCostPerUnit": (5.0, 7.0),
            },
        ),
        shared=replace(
            GENERIC_MES_PROFILE.shared,
            default_country="USA",
            default_currency="USD",
            location_catalog=(
                {"city": "Detroit", "state": "Michigan", "zip": "48201", "country": "USA"},
            ),
        ),
    )
