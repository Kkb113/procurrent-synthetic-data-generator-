from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.llm.industry_scenario_contract import IndustryScenarioPlan
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.shared.industry_profiles.generated_profile_adapter import (
    build_generated_industry_profile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import (
    get_industry_profile_or_default,
    load_industry_profile_from_json,
)


pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PRODUCTION_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PRODUCTION_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
SALES_METADATA = ROOT / "input" / "sales_v1_metadata.xlsx"

INDUSTRIES = {
    "food": {
        "scenario": "Food manufacturing for snack, beverage, ingredient, grocery, retailer, and foodservice customers.",
        "keywords": ("ingredient", "flour", "packaging", "beverage", "snack", "grocery", "retail", "foodservice"),
    },
    "ev": {
        "scenario": "EV manufacturing for battery packs, motors, inverters, wiring harnesses, fleet operators, and dealers.",
        "keywords": ("battery", "motor", "inverter", "harness", "sensor", "controller", "fleet", "dealer"),
    },
    "pharma": {
        "scenario": "Pharma manufacturing for API, excipient, sterile vial, tablet, capsule, hospital, and pharmacy channels.",
        "keywords": ("api", "excipient", "vial", "tablet", "capsule", "pharmacy", "hospital", "sterile"),
    },
}


def test_generated_profile_adapter_contains_full_lifecycle_sections() -> None:
    profile = _generated_profile("pharma").profile

    assert set(profile.supported_domains) == {"procurement", "production", "sales"}
    assert profile.procurement.supplier_name_patterns
    assert profile.procurement.component_name_patterns
    assert profile.production.product_catalog
    assert profile.production.work_center_catalog
    assert profile.sales.customer_types
    assert profile.sales.sales_channels


def test_generated_profile_adapter_fallback_missing_hints_still_usable() -> None:
    scenario = IndustryScenarioPlan.model_validate(
        {
            "industry_id": "general",
            "industry_name": "General Manufacturing",
            "business_summary": "General manufacturing.",
            "supported_domains": ["procurement", "production", "sales"],
        }
    )

    generated = build_generated_industry_profile(scenario, fallback_used=True, source="fallback")

    assert generated.fallback_used
    assert generated.profile.procurement.component_name_patterns
    assert generated.profile.production.routing_operation_names
    assert generated.profile.sales.customer_types


def test_profile_file_has_priority_over_profile_id_and_static_default(tmp_path: Path) -> None:
    profile_path = _write_profile(tmp_path, "food")

    loaded = get_industry_profile_or_default("ev_manufacturing", profile_file=profile_path)
    generator = ProcurementMasterDataGenerator(
        generation_config=GenerationConfig(seed=42, profile_id="ev_manufacturing", profile_file=profile_path)
    )
    default_profile = get_industry_profile_or_default(None)

    assert loaded.industry_id == "food"
    assert generator.industry_profile.industry_id == "food"
    assert default_profile.industry_id == "ev_manufacturing"


@pytest.mark.parametrize("industry_key", ["food", "ev", "pharma"])
def test_procurement_master_data_reflects_generated_industry_profile(tmp_path: Path, industry_key: str) -> None:
    profile_path = _write_profile(tmp_path, industry_key)
    config = GenerationConfig(seed=42, profile_file=profile_path)
    schema = load_metadata_schema(PROCUREMENT_METADATA).schema
    plan = load_llm_plan_json(PROCUREMENT_PLAN).plan

    dataframes, report = ProcurementMasterDataGenerator(generation_config=config).generate_master_data(
        schema,
        plan,
        seed=42,
        model_version="v2",
    )

    assert report.is_valid, [error.message for error in report.errors]
    assert _has_industry_signature(
        dataframes,
        ("SupplierMaster", "ComponentMaster"),
        INDUSTRIES[industry_key]["keywords"],
    )


@pytest.mark.parametrize("industry_key", ["food", "ev", "pharma"])
def test_production_master_data_reflects_generated_industry_profile(tmp_path: Path, industry_key: str) -> None:
    profile_path = _write_profile(tmp_path, industry_key)
    procurement_data = _procurement_master_data(profile_path)
    upstream_folder = tmp_path / f"{industry_key}_procurement"
    ProcurementMasterDataGenerator(generation_config=GenerationConfig(seed=42, profile_file=profile_path)).export_master_data(
        procurement_data,
        upstream_folder,
    )
    schema = load_metadata_schema(PRODUCTION_METADATA).schema
    plan = load_llm_plan_json(PRODUCTION_PLAN).plan

    dataframes, report = ProductionMasterDataGenerator(
        generation_config=GenerationConfig(seed=42, profile_file=profile_path)
    ).generate_master_data(schema, plan, seed=42, upstream_data_folder=upstream_folder)

    assert report.is_valid, [error.message for error in report.errors]
    assert _has_industry_signature(
        dataframes,
        ("ProductMaster", "WorkCenter", "RoutingOperation"),
        INDUSTRIES[industry_key]["keywords"],
    )


@pytest.mark.parametrize("industry_key", ["food", "ev", "pharma"])
def test_sales_master_data_reflects_generated_industry_profile(tmp_path: Path, industry_key: str) -> None:
    profile_path = _write_profile(tmp_path, industry_key)
    schema = load_metadata_schema(SALES_METADATA).schema
    product_master = pd.DataFrame(
        {
            "ProductID": [1, 2, 3],
            "ProductName": ["Industry Product A", "Industry Product B", "Industry Product C"],
            "StandardCost": [10.0, 20.0, 30.0],
        }
    )
    upstream = {
        "ProductMaster": product_master,
        "FinishedGoodsReceipt": pd.DataFrame({"ProductID": [1, 2, 3], "UnitCost": [10.0, 20.0, 30.0]}),
        "ProductionCostSummary": pd.DataFrame({"ProductID": [1, 2, 3], "UnitProductionCost": [10.0, 20.0, 30.0]}),
    }

    dataframes = SalesMasterDataGenerator(
        generation_config=GenerationConfig(seed=42, profile_file=profile_path)
    ).generate_master_data(schema=schema, upstream_data=upstream)

    assert _has_industry_signature(
        dataframes,
        ("CustomerMaster", "SalesChannel"),
        INDUSTRIES[industry_key]["keywords"],
    )


def _generated_profile(industry_key: str):
    scenario_text = INDUSTRIES[industry_key]["scenario"]
    scenario = IndustryScenarioPlan.model_validate(
        {
            "industry_id": industry_key,
            "industry_name": scenario_text,
            "business_summary": scenario_text,
            "supported_domains": ["procurement", "production", "sales"],
        }
    )
    return build_generated_industry_profile(scenario)


def _write_profile(tmp_path: Path, industry_key: str) -> Path:
    path = tmp_path / f"{industry_key}_generated_profile.json"
    path.write_text(json.dumps(_generated_profile(industry_key).to_artifact_dict(), indent=2), encoding="utf-8")
    assert load_industry_profile_from_json(path).industry_id == industry_key
    return path


def _procurement_master_data(profile_path: Path) -> dict[str, pd.DataFrame]:
    schema = load_metadata_schema(PROCUREMENT_METADATA).schema
    plan = load_llm_plan_json(PROCUREMENT_PLAN).plan
    dataframes, report = ProcurementMasterDataGenerator(
        generation_config=GenerationConfig(seed=42, profile_file=profile_path)
    ).generate_master_data(schema, plan, seed=42, model_version="v2")
    assert report.is_valid, [error.message for error in report.errors]
    return dataframes


def _has_industry_signature(
    dataframes: dict[str, pd.DataFrame],
    table_names: tuple[str, ...],
    keywords: tuple[str, ...],
) -> bool:
    text = " ".join(
        str(value)
        for table_name in table_names
        for value in dataframes[table_name].astype(str).to_numpy().ravel().tolist()
    ).lower()
    return any(keyword.lower() in text for keyword in keywords)
