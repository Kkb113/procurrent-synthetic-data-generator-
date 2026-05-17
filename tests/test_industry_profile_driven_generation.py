from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator
from procurement_data_generator.modules.shared.industry_profiles import GENERIC_MES_PROFILE, IndustryProfile


pytestmark = pytest.mark.integration


ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PRODUCTION_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PRODUCTION_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"


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


def _schema_and_plan(metadata_path: Path, plan_path: Path):
    schema_result = load_metadata_schema(metadata_path)
    plan_result = load_llm_plan_json(plan_path)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    return schema_result.schema, plan_result.plan


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
