from __future__ import annotations

from procurement_data_generator.modules.shared.industry_profiles import (
    EV_MANUFACTURING_PROFILE,
    GENERIC_MES_PROFILE,
    IndustryProfile,
    validate_industry_profile,
)


def test_industry_profiles_package_imports_successfully() -> None:
    assert IndustryProfile is not None
    assert callable(validate_industry_profile)


def test_ev_manufacturing_profile_loads() -> None:
    assert EV_MANUFACTURING_PROFILE.industry_id == "ev_manufacturing"
    assert EV_MANUFACTURING_PROFILE.industry_name == "Electric Vehicle Manufacturing"


def test_generic_mes_profile_loads() -> None:
    assert GENERIC_MES_PROFILE.industry_id == "generic_mes"
    assert GENERIC_MES_PROFILE.industry_name == "Generic Manufacturing Execution"


def test_ev_manufacturing_profile_validates_successfully() -> None:
    result = validate_industry_profile(EV_MANUFACTURING_PROFILE)

    assert result.valid
    assert result.errors == []


def test_generic_mes_profile_validates_successfully() -> None:
    result = validate_industry_profile(GENERIC_MES_PROFILE)

    assert result.valid
    assert result.errors == []


def test_invalid_profile_missing_required_sections_fails_validation() -> None:
    result = validate_industry_profile({"industry_id": "bad_profile", "industry_name": "Bad Profile"})

    assert not result.valid
    assert any("procurement" in error for error in result.errors)
    assert any("production" in error for error in result.errors)
    assert any("shared" in error for error in result.errors)


def test_profile_validator_returns_clear_errors() -> None:
    result = validate_industry_profile(
        {
            "industry_id": "",
            "industry_name": "Incomplete Profile",
            "procurement": {"component_categories": []},
            "production": {"product_categories": []},
            "shared": {"countable_uoms": ["EA"], "measurable_uoms": ["EA"]},
        }
    )

    assert not result.valid
    assert "industry_id must be non-empty." in result.errors
    assert any("procurement.component_name_patterns" in error for error in result.errors)
    assert any("production.work_center_names" in error for error in result.errors)


def test_ev_profile_contains_procurement_component_categories() -> None:
    categories = EV_MANUFACTURING_PROFILE.procurement.component_categories

    assert "Battery Components" in categories
    assert "Powertrain Components" in categories
    assert EV_MANUFACTURING_PROFILE.procurement.component_material_examples
    assert EV_MANUFACTURING_PROFILE.procurement.component_financial_profiles
    assert EV_MANUFACTURING_PROFILE.procurement.supplier_name_patterns


def test_ev_profile_contains_production_product_categories() -> None:
    categories = EV_MANUFACTURING_PROFILE.production.product_categories

    assert "EV Battery Pack Assembly" in categories
    assert "Drive Motor Assembly" in categories
    assert EV_MANUFACTURING_PROFILE.production.product_catalog


def test_ev_profile_contains_work_center_names() -> None:
    work_centers = EV_MANUFACTURING_PROFILE.production.work_center_names

    assert "Battery Assembly Line" in work_centers
    assert "End-of-Line Testing" in work_centers
    assert EV_MANUFACTURING_PROFILE.production.work_center_catalog


def test_ev_profile_contains_routing_operation_names() -> None:
    operations = EV_MANUFACTURING_PROFILE.production.routing_operation_names

    assert "Material Preparation" in operations
    assert "End-of-Line Test" in operations
    assert "TorqueDeviation" in EV_MANUFACTURING_PROFILE.production.quality_defect_codes
    assert EV_MANUFACTURING_PROFILE.production.rework_reason_codes


def test_generic_mes_profile_is_not_ev_specific() -> None:
    combined_text = " ".join(
        (
            GENERIC_MES_PROFILE.industry_name,
            *GENERIC_MES_PROFILE.procurement.component_categories,
            *GENERIC_MES_PROFILE.production.product_categories,
            *GENERIC_MES_PROFILE.production.work_center_names,
            *GENERIC_MES_PROFILE.production.routing_operation_names,
        )
    ).lower()

    assert "electric vehicle" not in combined_text
    assert "battery pack" not in combined_text
    assert "drive motor" not in combined_text


def test_profile_uom_sections_exist_and_are_non_empty() -> None:
    for profile in (EV_MANUFACTURING_PROFILE, GENERIC_MES_PROFILE):
        assert profile.shared.countable_uoms
        assert profile.shared.measurable_uoms
        assert set(profile.shared.countable_uoms) != set(profile.shared.measurable_uoms)
