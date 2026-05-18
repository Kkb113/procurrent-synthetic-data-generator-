"""Shared industry profile architecture for future catalog-driven generation."""

from procurement_data_generator.modules.shared.industry_profiles.ev_manufacturing_profile import EV_MANUFACTURING_PROFILE
from procurement_data_generator.modules.shared.industry_profiles.food_manufacturing_profile import FOOD_MANUFACTURING_PROFILE
from procurement_data_generator.modules.shared.industry_profiles.generic_mes_profile import GENERIC_MES_PROFILE
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import (
    IndustryProfile,
    ProcurementProfile,
    ProductionProfile,
    SalesProfile,
    SharedProfile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_validator import (
    IndustryProfileValidationResult,
    validate_industry_profile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_value_provider import (
    DEFAULT_PROCUREMENT_INSPECTION_TEST_NAMES,
    DEFAULT_PROCUREMENT_REJECTION_REASONS,
    LEGACY_MANUFACTURING_LOCATIONS,
    IndustryProfileValueProvider,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import (
    DEFAULT_INDUSTRY_PROFILE_ID,
    get_default_industry_profile,
    get_industry_profile,
    get_industry_profile_or_default,
    get_supported_industry_profile_ids,
    industry_profile_to_dict,
    load_industry_profile_from_dict,
    load_industry_profile_from_json,
)

__all__ = [
    "EV_MANUFACTURING_PROFILE",
    "FOOD_MANUFACTURING_PROFILE",
    "GENERIC_MES_PROFILE",
    "DEFAULT_INDUSTRY_PROFILE_ID",
    "IndustryProfile",
    "IndustryProfileValidationResult",
    "IndustryProfileValueProvider",
    "LEGACY_MANUFACTURING_LOCATIONS",
    "ProcurementProfile",
    "ProductionProfile",
    "SalesProfile",
    "SharedProfile",
    "DEFAULT_PROCUREMENT_REJECTION_REASONS",
    "DEFAULT_PROCUREMENT_INSPECTION_TEST_NAMES",
    "get_default_industry_profile",
    "get_industry_profile",
    "get_industry_profile_or_default",
    "get_supported_industry_profile_ids",
    "industry_profile_to_dict",
    "load_industry_profile_from_dict",
    "load_industry_profile_from_json",
    "validate_industry_profile",
]
