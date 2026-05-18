from __future__ import annotations

from dataclasses import replace

import pytest

from procurement_data_generator.modules.shared.industry_profiles import (
    EV_MANUFACTURING_PROFILE,
    FOOD_MANUFACTURING_PROFILE,
    GENERIC_MES_PROFILE,
    IndustryProfileValueProvider,
)


pytestmark = pytest.mark.unit


def test_default_profile_value_provider_preserves_current_country_currency_and_locations() -> None:
    provider = IndustryProfileValueProvider(EV_MANUFACTURING_PROFILE)

    assert provider.default_country == "USA"
    assert provider.default_currency == "USD"
    assert provider.location_catalog()[0] == {
        "city": "Detroit",
        "state": "Michigan",
        "zip": "48201",
        "country": "USA",
    }


def test_default_profile_value_provider_preserves_procurement_rejection_reasons() -> None:
    provider = IndustryProfileValueProvider(EV_MANUFACTURING_PROFILE)
    reasons = provider.procurement_rejection_reasons()

    assert "Dimension Out of Tolerance" in reasons
    assert "Supplier Documentation Issue" in reasons
    assert len(reasons) >= 5
    assert provider.is_procurement_safety_critical_category("Battery") is True
    assert provider.is_procurement_safety_critical_category("Safety") is True


def test_non_default_profile_does_not_force_battery_safety_critical_policy() -> None:
    provider = IndustryProfileValueProvider(GENERIC_MES_PROFILE)

    assert provider.is_procurement_safety_critical_category("Battery") is False
    assert provider.is_procurement_safety_critical_category("Safety") is False


def test_food_profile_exposes_food_quality_vocabulary() -> None:
    provider = IndustryProfileValueProvider(FOOD_MANUFACTURING_PROFILE)

    assert provider.default_country == "India"
    assert provider.default_currency == "INR"
    assert "Moisture Check" in provider.procurement_inspection_test_names()
    assert "Foreign Material Detected" in provider.procurement_rejection_reasons()
    assert provider.is_procurement_safety_critical_category("Battery") is False


def test_custom_profile_values_override_named_generator_policies() -> None:
    custom = replace(
        GENERIC_MES_PROFILE,
        procurement=replace(
            GENERIC_MES_PROFILE.procurement,
            rejection_reasons=("Custom Seal Failure", "Custom Label Damage"),
            inspection_test_names=("Seal Integrity Test", "Label Verification"),
            safety_critical_category_terms=("sterile",),
        ),
        production=replace(
            GENERIC_MES_PROFILE.production,
            scrap_reason_codes=("Custom Scrap",),
            rework_reason_codes=("Custom Rework",),
            cost_profiles={
                **GENERIC_MES_PROFILE.production.cost_profiles,
                "ProductionLaborCostPerOperation": (11.0, 22.0),
                "ProductionOverheadPct": (7.0, 9.0),
            },
        ),
        shared=replace(
            GENERIC_MES_PROFILE.shared,
            default_country="USA",
            default_currency="USD",
            location_catalog=(
                {"city": "Madison", "state": "Wisconsin", "zip": "53703", "country": "USA"},
            ),
        ),
    )
    provider = IndustryProfileValueProvider(custom)

    assert provider.location_catalog() == (
        {"city": "Madison", "state": "Wisconsin", "zip": "53703", "country": "USA"},
    )
    assert provider.procurement_rejection_reasons() == ("Custom Seal Failure", "Custom Label Damage")
    assert provider.procurement_inspection_test_names() == ("Seal Integrity Test", "Label Verification")
    assert provider.is_procurement_safety_critical_category("Sterile") is True
    assert provider.is_procurement_safety_critical_category("Battery") is False
    assert provider.production_scrap_reason_codes() == ("Custom Scrap",)
    assert provider.production_rework_reason_codes() == ("Custom Rework",)
    assert provider.production_cost_range("ProductionLaborCostPerOperation", (45.0, 95.0)) == (11.0, 22.0)
    assert provider.production_percentage_range("ProductionOverheadPct", (0.12, 0.24)) == (0.07, 0.09)
