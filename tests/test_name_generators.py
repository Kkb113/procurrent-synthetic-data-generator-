from __future__ import annotations

import re

import pytest

from procurement_data_generator.core.contracts.llm_plan_contract import DomainProfile, MaterialCategory
from procurement_data_generator.modules.procurement.name_generators import (
    NameGenerationError,
    ProcurementNameGenerator,
)


ARTIFICIAL_SUFFIX_PATTERN = re.compile(r"\s(?:[1-9]|[1-9][0-9])$")


def test_vendor_names_are_unique_for_count_50() -> None:
    names = ProcurementNameGenerator().generate_vendor_names(50, _rich_profile(), seed=42)

    assert len(names) == 50
    assert len(names) == len(set(names))


def test_material_names_are_unique_for_count_200() -> None:
    names = ProcurementNameGenerator().generate_material_names(200, _rich_profile(), seed=42)

    assert len(names) == 200
    assert len(names) == len(set(names))


def test_plant_names_are_unique_for_count_2() -> None:
    names = ProcurementNameGenerator().generate_plant_names(2, _rich_profile(), seed=42)

    assert len(names) == 2
    assert len(names) == len(set(names))


def test_warehouse_names_are_unique_for_count_6() -> None:
    generator = ProcurementNameGenerator()
    plants = generator.generate_plant_names(2, _rich_profile(), seed=42)

    names = generator.generate_warehouse_names(6, _rich_profile(), plant_names=plants, seed=42)

    assert len(names) == 6
    assert len(names) == len(set(names))


def test_faker_person_names_are_unique_for_count_20() -> None:
    names = ProcurementNameGenerator().generate_faker_person_names(20, seed=42)

    assert len(names) == 20
    assert len(names) == len(set(names))


def test_faker_company_names_are_unique_for_count_20() -> None:
    names = ProcurementNameGenerator().generate_faker_company_names(20, seed=42)

    assert len(names) == 20
    assert len(names) == len(set(names))


def test_same_seed_produces_same_vendor_names() -> None:
    generator = ProcurementNameGenerator()

    first = generator.generate_vendor_names(10, _rich_profile(), seed=42)
    second = generator.generate_vendor_names(10, _rich_profile(), seed=42)

    assert first == second


def test_different_seed_can_produce_different_vendor_order_or_names() -> None:
    generator = ProcurementNameGenerator()

    first = generator.generate_vendor_names(10, _rich_profile(), seed=42)
    second = generator.generate_vendor_names(10, _rich_profile(), seed=43)

    assert first != second


def test_no_generated_name_ends_with_artificial_numeric_suffix() -> None:
    generator = ProcurementNameGenerator()
    profile = _rich_profile()
    names = [
        *generator.generate_vendor_names(50, profile, seed=42),
        *generator.generate_material_names(50, profile, seed=42),
        *generator.generate_plant_names(5, profile, seed=42),
        *generator.generate_warehouse_names(10, profile, seed=42),
    ]

    assert not any(ARTIFICIAL_SUFFIX_PATTERN.search(name) for name in names)


def test_material_names_use_profile_examples_or_spec_patterns_when_rich() -> None:
    profile = DomainProfile(
        industry="custom manufacturing",
        business_context=None,
        vendor_categories=["Custom suppliers"],
        material_categories=[
            MaterialCategory(
                category_name="Special Materials",
                material_examples=["Custom Alloy Plate"],
                specification_patterns=["SpecX", "Grade Prime"],
            )
        ],
        warehouse_types=["Raw Material"],
        plant_locations=["Bengaluru"],
        carrier_name_patterns=[],
        inspection_test_categories=[],
    )

    names = ProcurementNameGenerator().generate_material_names(10, profile, seed=42)

    assert all("Custom Alloy Plate" in name for name in names)
    assert any("SpecX" in name or "Grade Prime" in name for name in names)


def test_warehouse_names_use_plant_location_or_warehouse_function() -> None:
    names = ProcurementNameGenerator().generate_warehouse_names(
        4,
        _rich_profile(),
        plant_names=["Bengaluru Assembly Plant", "Pune Manufacturing Plant"],
        seed=42,
    )

    assert all(name.startswith("Bengaluru ") or name.startswith("Pune ") for name in names)
    assert all("Warehouse" in name for name in names)


def test_insufficient_unique_names_fail_clearly() -> None:
    profile = DomainProfile(
        industry="general manufacturing",
        business_context=None,
        vendor_categories=[],
        material_categories=[],
        warehouse_types=[],
        plant_locations=["OneCity"],
        carrier_name_patterns=[],
        inspection_test_categories=[],
    )

    with pytest.raises(NameGenerationError, match="Unable to generate 8 unique plant names"):
        ProcurementNameGenerator().generate_plant_names(8, profile, seed=42)


def test_pharma_fallback_produces_pharma_like_names() -> None:
    names = ProcurementNameGenerator().generate_material_names(20, _weak_profile("pharma manufacturing"), seed=42)

    assert any("Pharmaceutical" in name or "Sterile" in name or "Reagent" in name for name in names)


def test_semiconductor_fallback_produces_semiconductor_like_names() -> None:
    names = ProcurementNameGenerator().generate_material_names(20, _weak_profile("semiconductor chip manufacturing"), seed=42)

    assert any("Wafer" in name or "Photoresist" in name or "Cleanroom" in name for name in names)


def test_food_fallback_produces_food_like_names() -> None:
    names = ProcurementNameGenerator().generate_material_names(20, _weak_profile("food manufacturing"), seed=42)

    assert any("Sugar" in name or "Food" in name or "Flour" in name for name in names)


def test_furniture_fallback_produces_furniture_like_names() -> None:
    names = ProcurementNameGenerator().generate_material_names(20, _weak_profile("furniture manufacturing"), seed=42)

    assert any("Wood" in name or "Upholstery" in name or "Hinge" in name for name in names)


def test_it_office_fallback_produces_it_office_like_names() -> None:
    names = ProcurementNameGenerator().generate_material_names(20, _weak_profile("IT office procurement"), seed=42)

    assert any("Laptop" in name or "Cloud" in name or "Network" in name or "Office" in name for name in names)


def test_unknown_industry_uses_generic_procurement_fallback() -> None:
    names = ProcurementNameGenerator().generate_material_names(20, _weak_profile("unmapped specialty domain"), seed=42)

    assert any("Industrial" in name or "Bearing" in name or "Office" in name for name in names)


def _rich_profile() -> DomainProfile:
    return DomainProfile(
        industry="EV manufacturing",
        business_context="Procurement across two plants.",
        vendor_categories=["Battery suppliers", "Metal fabricators", "Electronics suppliers"],
        material_categories=[
            MaterialCategory(
                category_name="Battery Components",
                material_examples=["Lithium-Ion Cell", "Battery Management PCB", "Thermal Pad", "Copper Busbar"],
                specification_patterns=["21700", "Prismatic", "Grade A", "2mm", "HV", "12mm"],
            ),
            MaterialCategory(
                category_name="Packaging Materials",
                material_examples=["Corrugated Carton", "Protective Foam", "Packaging Film Roll"],
                specification_patterns=["Heavy Duty", "ESD Safe", "Standard Pack"],
            ),
        ],
        warehouse_types=["Raw Material", "Quality Hold", "Rejected Material", "Maintenance Spares"],
        plant_locations=["Bengaluru", "Pune", "Chennai"],
        carrier_name_patterns=["regional freight"],
        inspection_test_categories=["Dimensional inspection"],
    )


def _weak_profile(industry: str) -> DomainProfile:
    return DomainProfile(
        industry=industry,
        business_context=None,
        vendor_categories=[],
        material_categories=[],
        warehouse_types=[],
        plant_locations=[],
        carrier_name_patterns=[],
        inspection_test_categories=[],
    )
