from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from procurement_data_generator.core.llm.azure_openai_client import AzureOpenAIClient, AzureOpenAIConfig
from procurement_data_generator.core.llm.json_extractor import extract_json_object
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.shared.industry_profiles import (
    EV_MANUFACTURING_PROFILE,
    GENERIC_MES_PROFILE,
    industry_profile_to_dict,
    load_industry_profile_from_dict,
    load_industry_profile_from_json,
    validate_industry_profile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_prompt_builder import build_industry_profile_prompt


ROOT = Path(__file__).resolve().parents[1]
PROCUREMENT_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROCUREMENT_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PRODUCTION_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PRODUCTION_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"


def test_profile_prompt_builder_requires_json_only_and_no_rows() -> None:
    prompt = build_industry_profile_prompt(
        "Food Manufacturing",
        description="Generate Procurement and Production Execution profile for packaged food manufacturing.",
    )

    assert "Return JSON only" in prompt
    assert "Do not generate table rows" in prompt
    assert "Procurement -> Production Execution -> Sales" in prompt
    assert '"supported_domains": ["procurement", "production", "sales"]' in prompt
    assert "customer/channel/payment/region/return vocabulary" in prompt
    assert "OEE" in prompt


def test_mock_azure_openai_profile_response_can_be_extracted() -> None:
    raw_text = "```json\n" + json.dumps(_food_profile_data()) + "\n```"
    extraction = extract_json_object(raw_text)

    assert extraction.success
    assert extraction.parsed_json is not None
    assert extraction.parsed_json["industry_id"] == "food_manufacturing"


def test_azure_openai_client_json_generation_uses_fake_client_only() -> None:
    fake_client = _FakeAzureClient(json.dumps(_food_profile_data()))
    config = AzureOpenAIConfig(
        endpoint="https://example.openai.azure.com",
        api_key="test-key",
        deployment="test-deployment",
        api_version="2024-02-15-preview",
    )
    response = AzureOpenAIClient(config, openai_client=fake_client).generate_json(
        "Build a food manufacturing profile.",
        system_message="Return JSON only. Do not generate table rows.",
    )

    assert response.status == "passed"
    assert response.parsed_json is not None
    assert response.parsed_json["industry_id"] == "food_manufacturing"
    assert fake_client.chat.completions.calls == 1


def test_valid_generated_profile_json_validates_successfully() -> None:
    profile = load_industry_profile_from_dict(_food_profile_data())
    result = validate_industry_profile(profile)

    assert result.valid
    assert result.errors == []


@pytest.mark.parametrize(
    "section,error_text",
    [
        ("procurement", "procurement"),
        ("production", "production"),
        ("shared", "shared"),
    ],
)
def test_generated_profile_missing_required_sections_fails(section: str, error_text: str) -> None:
    data = _food_profile_data()
    data.pop(section)

    result = validate_industry_profile(data)

    assert not result.valid
    assert any(error_text in error for error in result.errors)


def test_missing_shared_uom_section_fails_validation() -> None:
    data = _food_profile_data()
    data["shared"].pop("countable_uoms")

    result = validate_industry_profile(data)

    assert not result.valid
    assert any("shared.countable_uoms" in error for error in result.errors)


def test_load_industry_profile_from_json_works(tmp_path: Path) -> None:
    path = tmp_path / "food_manufacturing_profile.json"
    path.write_text(json.dumps(_food_profile_data()), encoding="utf-8")

    profile = load_industry_profile_from_json(path)

    assert profile.industry_id == "food_manufacturing"
    assert profile.production.work_center_names


def test_generated_profile_can_be_used_by_procurement_master_generator(tmp_path: Path) -> None:
    profile_path = _write_food_profile(tmp_path)
    profile = load_industry_profile_from_json(profile_path)
    schema_result = load_metadata_schema(PROCUREMENT_METADATA)
    plan_result = load_llm_plan_json(PROCUREMENT_PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None

    dataframes, report = ProcurementMasterDataGenerator(industry_profile=profile).generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
        model_version="v2",
    )

    assert report.is_valid
    assert {"SupplierMaster", "ComponentMaster", "SupplierComponent", "Plant", "Warehouse"} == set(dataframes)
    assert any("Ingredient" in name or "Packaging" in name for name in dataframes["ComponentMaster"]["ComponentName"])


def test_generated_profile_can_be_used_by_production_master_generator(tmp_path: Path) -> None:
    profile_path = _write_food_profile(tmp_path)
    profile = load_industry_profile_from_json(profile_path)
    upstream_folder = tmp_path / "food_procurement_master"
    procurement_schema = load_metadata_schema(PROCUREMENT_METADATA).schema
    procurement_plan = load_llm_plan_json(PROCUREMENT_PLAN).plan
    assert procurement_schema is not None
    assert procurement_plan is not None
    procurement_data, procurement_report = ProcurementMasterDataGenerator(industry_profile=profile).generate_master_data(
        procurement_schema,
        procurement_plan,
        seed=42,
        model_version="v2",
    )
    assert procurement_report.is_valid
    ProcurementMasterDataGenerator(industry_profile=profile).export_master_data(procurement_data, upstream_folder)

    production_schema = load_metadata_schema(PRODUCTION_METADATA).schema
    production_plan = load_llm_plan_json(PRODUCTION_PLAN).plan
    assert production_schema is not None
    assert production_plan is not None
    dataframes, report = ProductionMasterDataGenerator(industry_profile=profile).generate_master_data(
        production_schema,
        production_plan,
        seed=42,
        upstream_data_folder=upstream_folder,
    )

    assert report.is_valid
    assert "Mixing Station" in set(dataframes["WorkCenter"]["WorkCenterName"])
    assert "Batch Preparation" in set(dataframes["RoutingOperation"]["OperationName"])
    assert any("Bottled Beverage" in name for name in dataframes["ProductMaster"]["ProductName"])


def test_unknown_profile_id_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Unknown industry profile"):
        ProcurementMasterDataGenerator(profile_id="missing_profile")


def test_static_profiles_still_load_and_serialize() -> None:
    assert industry_profile_to_dict(EV_MANUFACTURING_PROFILE)["industry_id"] == "ev_manufacturing"
    assert industry_profile_to_dict(GENERIC_MES_PROFILE)["industry_id"] == "generic_mes"


def _write_food_profile(tmp_path: Path) -> Path:
    path = tmp_path / "food_manufacturing_profile.json"
    path.write_text(json.dumps(_food_profile_data()), encoding="utf-8")
    return path


def _food_profile_data() -> dict:
    return {
        "industry_id": "food_manufacturing",
        "industry_name": "Food Manufacturing",
        "industry_description": "Catalog hints for packaged food procurement and production execution.",
        "supported_domains": ["procurement", "production"],
        "procurement": {
            "supplier_name_patterns": ["{category} Ingredient Supply", "{region} Packaging Partners"],
            "component_categories": ["Ingredients", "Packaging Materials", "Labels", "Bottles", "Caps", "Cleaning Consumables"],
            "component_name_patterns": ["Ingredient Blend", "Bottle", "Cap", "Label Roll", "Packaging Film"],
            "component_category_codes": ["Packaging", "Maintenance", "Mechanical", "Electrical"],
            "component_material_examples": {
                "Ingredients": ["Ingredient Blend", "Flavor Concentrate", "Sweetener"],
                "Packaging Materials": ["Bottle", "Cap", "Label Roll", "Carton"],
            },
            "component_specification_patterns": {
                "Ingredients": ["Food Grade", "Batch Certified", "25kg"],
                "Packaging Materials": ["Food Safe", "Printed", "Standard Pack"],
            },
            "component_uom_preferences": {
                "Ingredients": ["KG", "Liter"],
                "Packaging Materials": ["EA", "Pack", "Roll"],
            },
            "component_cost_profiles": {
                "Ingredients": [2.0, 150.0],
                "Packaging Materials": [0.5, 80.0],
            },
            "supplier_component_relationship_rules": ["Ingredient suppliers require food safety certification."],
        },
        "production": {
            "product_categories": ["Bottled Beverage", "Packaged Sauce", "Snack Pack"],
            "product_name_patterns": ["Bottled Beverage", "Packaged Sauce", "Snack Pack"],
            "work_center_names": [
                "Mixing Station",
                "Filling Line",
                "Sealing Station",
                "Labeling Line",
                "Packaging Line",
                "Quality Inspection Station",
            ],
            "routing_operation_names": [
                "Batch Preparation",
                "Mixing",
                "Filling",
                "Sealing",
                "Labeling",
                "Final Inspection",
                "Packaging Release",
            ],
            "product_catalog": [
                {"name": "Bottled Beverage", "category": "Beverage", "product_type": "FinishedGood", "uom": "EA", "base_cost": 8, "base_hours": 1.5},
                {"name": "Packaged Sauce", "category": "Sauce", "product_type": "FinishedGood", "uom": "EA", "base_cost": 6, "base_hours": 1.2},
                {"name": "Snack Pack", "category": "Snack", "product_type": "FinishedGood", "uom": "Pack", "base_cost": 5, "base_hours": 1.0},
            ],
            "work_center_catalog": [
                {"name": "Mixing Station", "line_name": "Mixing"},
                {"name": "Filling Line", "line_name": "Filling"},
                {"name": "Sealing Station", "line_name": "Sealing"},
                {"name": "Labeling Line", "line_name": "Labeling"},
                {"name": "Packaging Line", "line_name": "Packaging"},
                {"name": "Quality Inspection Station", "line_name": "Quality"},
            ],
            "fallback_components": [
                {"ComponentID": 1, "ComponentName": "Ingredient Blend", "UOM": "KG"},
                {"ComponentID": 2, "ComponentName": "Bottle", "UOM": "EA"},
                {"ComponentID": 3, "ComponentName": "Cap", "UOM": "EA"},
            ],
            "fallback_plants": [{"PlantID": 1, "PlantName": "Main Food Manufacturing Plant"}],
            "fallback_warehouses": [{"WarehouseID": 1, "PlantID": 1, "WarehouseName": "Main Ingredient Warehouse"}],
            "bom_patterns": ["Finished food products consume ingredients, packaging, labels, and caps."],
            "scrap_yield_profiles": {"Filling": [0.0, 2.0], "Packaging": [0.0, 1.5]},
            "quality_defect_codes": ["FillLevelIssue", "SealFailure", "LabelMisalignment", "ContaminationRisk", "PackagingDefect"],
            "rework_reason_codes": ["Re-label", "Re-seal", "Re-pack", "Re-inspect"],
            "cost_profiles": {"LaborRatePerHour": [18.0, 55.0], "OverheadPct": [5.0, 18.0]},
        },
        "shared": {
            "countable_uoms": ["EA", "Each", "Unit", "Piece", "PCS", "Pack", "Set"],
            "measurable_uoms": ["KG", "Gram", "Liter", "Meter", "Roll"],
            "default_currency": "USD",
            "date_scope_notes": ["Generated scenarios remain in calendar year 2025."],
            "realism_notes": ["Food profile is catalog content only; Python generates rows."],
        },
    }


class _FakeAzureClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        return SimpleNamespace(choices=[choice], usage=usage)
