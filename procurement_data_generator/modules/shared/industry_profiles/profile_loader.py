"""Lightweight industry profile lookup helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from procurement_data_generator.modules.shared.industry_profiles.ev_manufacturing_profile import EV_MANUFACTURING_PROFILE
from procurement_data_generator.modules.shared.industry_profiles.food_manufacturing_profile import FOOD_MANUFACTURING_PROFILE
from procurement_data_generator.modules.shared.industry_profiles.generic_mes_profile import GENERIC_MES_PROFILE
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import (
    IndustryProfile,
    ProcurementProfile,
    ProductionProfile,
    SharedProfile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_validator import validate_industry_profile


DEFAULT_INDUSTRY_PROFILE_ID = "ev_manufacturing"

_INDUSTRY_PROFILES: dict[str, IndustryProfile] = {
    EV_MANUFACTURING_PROFILE.industry_id: EV_MANUFACTURING_PROFILE,
    FOOD_MANUFACTURING_PROFILE.industry_id: FOOD_MANUFACTURING_PROFILE,
    GENERIC_MES_PROFILE.industry_id: GENERIC_MES_PROFILE,
}


def get_default_industry_profile() -> IndustryProfile:
    """Return the default industry profile used by current deterministic generators."""

    return get_industry_profile(DEFAULT_INDUSTRY_PROFILE_ID)


def get_industry_profile_or_default(profile_id: str | None = None, profile_file: str | Path | None = None) -> IndustryProfile:
    """Return the requested profile, or the default profile when no ID is supplied."""

    if profile_file is not None:
        return load_industry_profile_from_json(profile_file)
    if profile_id is None or not str(profile_id).strip():
        return get_default_industry_profile()
    return get_industry_profile(profile_id)


def get_industry_profile(industry_id: str) -> IndustryProfile:
    """Return a known industry profile by ID."""

    normalized = str(industry_id or "").strip().lower()
    try:
        return _INDUSTRY_PROFILES[normalized]
    except KeyError as exc:
        known = ", ".join(sorted(_INDUSTRY_PROFILES))
        raise ValueError(f"Unknown industry profile '{industry_id}'. Supported profiles: {known}.") from exc


def get_supported_industry_profile_ids() -> tuple[str, ...]:
    """Return supported industry profile IDs."""

    return tuple(sorted(_INDUSTRY_PROFILES))


def load_industry_profile_from_json(path: str | Path) -> IndustryProfile:
    """Load and validate an industry profile JSON artifact."""

    profile_path = Path(path)
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return load_industry_profile_from_dict(data)


def load_industry_profile_from_dict(data: Mapping[str, Any]) -> IndustryProfile:
    """Convert generated profile JSON into the dataclass contract and validate it."""

    profile = IndustryProfile(
        industry_id=str(data.get("industry_id", "")).strip(),
        industry_name=str(data.get("industry_name", "")).strip(),
        industry_description=str(data.get("industry_description", "")).strip(),
        supported_domains=_tuple_of_str(data.get("supported_domains", ("procurement", "production"))),
        procurement=_load_procurement_profile(_mapping(data.get("procurement"))),
        production=_load_production_profile(_mapping(data.get("production"))),
        shared=_load_shared_profile(_mapping(data.get("shared"))),
    )
    result = validate_industry_profile(profile)
    if not result.valid:
        raise ValueError("Industry profile validation failed: " + "; ".join(result.errors))
    return profile


def industry_profile_to_dict(profile: IndustryProfile) -> dict[str, Any]:
    """Serialize an industry profile dataclass into JSON-friendly dictionaries."""

    return {
        "industry_id": profile.industry_id,
        "industry_name": profile.industry_name,
        "industry_description": profile.industry_description,
        "supported_domains": list(profile.supported_domains),
        "procurement": {
            "supplier_name_patterns": list(profile.procurement.supplier_name_patterns),
            "component_categories": list(profile.procurement.component_categories),
            "component_name_patterns": list(profile.procurement.component_name_patterns),
            "component_category_codes": list(profile.procurement.component_category_codes),
            "component_material_examples": _dict_tuple_to_list(profile.procurement.component_material_examples),
            "component_specification_patterns": _dict_tuple_to_list(profile.procurement.component_specification_patterns),
            "component_uom_preferences": _dict_tuple_to_list(profile.procurement.component_uom_preferences),
            "component_cost_profiles": _dict_tuple_to_list(profile.procurement.component_cost_profiles),
            "component_financial_profiles": profile.procurement.component_financial_profiles,
            "component_category_aliases": dict(profile.procurement.component_category_aliases),
            "rejection_reasons": list(profile.procurement.rejection_reasons),
            "inspection_test_names": list(profile.procurement.inspection_test_names),
            "safety_critical_category_terms": list(profile.procurement.safety_critical_category_terms),
            "plant_type_names": list(profile.procurement.plant_type_names),
            "warehouse_type_names": list(profile.procurement.warehouse_type_names),
            "supplier_component_relationship_rules": list(profile.procurement.supplier_component_relationship_rules),
        },
        "production": {
            "product_categories": list(profile.production.product_categories),
            "product_name_patterns": list(profile.production.product_name_patterns),
            "work_center_names": list(profile.production.work_center_names),
            "routing_operation_names": list(profile.production.routing_operation_names),
            "product_catalog": list(profile.production.product_catalog),
            "work_center_catalog": list(profile.production.work_center_catalog),
            "fallback_components": list(profile.production.fallback_components),
            "fallback_plants": list(profile.production.fallback_plants),
            "fallback_warehouses": list(profile.production.fallback_warehouses),
            "bom_patterns": list(profile.production.bom_patterns),
            "scrap_yield_profiles": _dict_tuple_to_list(profile.production.scrap_yield_profiles),
            "quality_defect_codes": list(profile.production.quality_defect_codes),
            "scrap_reason_codes": list(profile.production.scrap_reason_codes),
            "rework_reason_codes": list(profile.production.rework_reason_codes),
            "cost_profiles": _dict_tuple_to_list(profile.production.cost_profiles),
        },
        "shared": {
            "countable_uoms": list(profile.shared.countable_uoms),
            "measurable_uoms": list(profile.shared.measurable_uoms),
            "default_country": profile.shared.default_country,
            "default_currency": profile.shared.default_currency,
            "location_catalog": list(profile.shared.location_catalog),
            "date_scope_notes": list(profile.shared.date_scope_notes),
            "realism_notes": list(profile.shared.realism_notes),
        },
    }


def _load_procurement_profile(data: Mapping[str, Any]) -> ProcurementProfile:
    return ProcurementProfile(
        supplier_name_patterns=_tuple_of_str(data.get("supplier_name_patterns")),
        component_categories=_tuple_of_str(data.get("component_categories")),
        component_name_patterns=_tuple_of_str(data.get("component_name_patterns")),
        component_category_codes=_tuple_of_str(data.get("component_category_codes")),
        component_material_examples=_dict_of_str_tuples(data.get("component_material_examples")),
        component_specification_patterns=_dict_of_str_tuples(data.get("component_specification_patterns")),
        component_uom_preferences=_dict_of_str_tuples(data.get("component_uom_preferences")),
        component_cost_profiles=_dict_of_float_pairs(data.get("component_cost_profiles")),
        component_financial_profiles=_dict_of_float_dicts(data.get("component_financial_profiles")),
        component_category_aliases=_dict_of_str(data.get("component_category_aliases")),
        rejection_reasons=_tuple_of_str(data.get("rejection_reasons")),
        inspection_test_names=_tuple_of_str(data.get("inspection_test_names")),
        safety_critical_category_terms=_tuple_of_str(data.get("safety_critical_category_terms")),
        plant_type_names=_tuple_of_str(data.get("plant_type_names")),
        warehouse_type_names=_tuple_of_str(data.get("warehouse_type_names")),
        supplier_component_relationship_rules=_tuple_of_str(data.get("supplier_component_relationship_rules")),
    )


def _load_production_profile(data: Mapping[str, Any]) -> ProductionProfile:
    return ProductionProfile(
        product_categories=_tuple_of_str(data.get("product_categories")),
        product_name_patterns=_tuple_of_str(data.get("product_name_patterns")),
        work_center_names=_tuple_of_str(data.get("work_center_names")),
        routing_operation_names=_tuple_of_str(data.get("routing_operation_names")),
        product_catalog=_tuple_of_dicts(data.get("product_catalog")),
        work_center_catalog=_tuple_of_dicts(data.get("work_center_catalog")),
        fallback_components=_tuple_of_dicts(data.get("fallback_components")),
        fallback_plants=_tuple_of_dicts(data.get("fallback_plants")),
        fallback_warehouses=_tuple_of_dicts(data.get("fallback_warehouses")),
        bom_patterns=_tuple_of_str(data.get("bom_patterns")),
        scrap_yield_profiles=_dict_of_float_pairs(data.get("scrap_yield_profiles")),
        quality_defect_codes=_tuple_of_str(data.get("quality_defect_codes")),
        scrap_reason_codes=_tuple_of_str(data.get("scrap_reason_codes")),
        rework_reason_codes=_tuple_of_str(data.get("rework_reason_codes")),
        cost_profiles=_dict_of_float_pairs(data.get("cost_profiles")),
    )


def _load_shared_profile(data: Mapping[str, Any]) -> SharedProfile:
    return SharedProfile(
        countable_uoms=_tuple_of_str(data.get("countable_uoms")),
        measurable_uoms=_tuple_of_str(data.get("measurable_uoms")),
        default_country=str(data.get("default_country") or "USA"),
        default_currency=str(data.get("default_currency") or "USD"),
        location_catalog=_tuple_of_dicts(data.get("location_catalog")),
        date_scope_notes=_tuple_of_str(data.get("date_scope_notes")),
        realism_notes=_tuple_of_str(data.get("realism_notes")),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or value is None or not hasattr(value, "__iter__"):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _tuple_of_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(value, str) or value is None or not hasattr(value, "__iter__"):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _dict_of_str_tuples(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _tuple_of_str(values) for key, values in value.items()}


def _dict_of_float_pairs(value: Any) -> dict[str, tuple[float, float]]:
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, tuple[float, float]] = {}
    for key, values in value.items():
        if isinstance(values, str) or values is None or not hasattr(values, "__iter__"):
            continue
        pair = list(values)
        if len(pair) >= 2:
            output[str(key)] = (float(pair[0]), float(pair[1]))
    return output


def _dict_of_float_dicts(value: Any) -> dict[str, dict[str, float]]:
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, dict[str, float]] = {}
    for key, profile in value.items():
        if isinstance(profile, Mapping):
            output[str(key)] = {str(item_key): float(item_value) for item_key, item_value in profile.items()}
    return output


def _dict_of_str(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item_value) for key, item_value in value.items()}


def _dict_tuple_to_list(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: list(item) if isinstance(item, tuple) else item for key, item in value.items()}
