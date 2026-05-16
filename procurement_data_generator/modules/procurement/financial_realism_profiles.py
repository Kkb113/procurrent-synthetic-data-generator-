"""Procurement v2 financial realism profiles sourced from the default industry profile."""

from __future__ import annotations

import random
from typing import TypedDict, cast

from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_default_industry_profile


class FinancialProfile(TypedDict):
    unit_price_min: float
    unit_price_max: float
    quantity_min: float
    quantity_max: float
    line_amount_soft_max: float
    high_value_probability: float


_DEFAULT_PROCUREMENT_PROFILE = get_default_industry_profile().procurement

CATEGORY_FINANCIAL_PROFILES: dict[str, FinancialProfile] = {
    category: cast(FinancialProfile, dict(profile))
    for category, profile in _DEFAULT_PROCUREMENT_PROFILE.component_financial_profiles.items()
}

_CATEGORY_ALIASES = dict(_DEFAULT_PROCUREMENT_PROFILE.component_category_aliases)

_DEFAULT_PROFILE_NAME = _CATEGORY_ALIASES.get("mechanical", next(iter(CATEGORY_FINANCIAL_PROFILES)))
DEFAULT_FINANCIAL_PROFILE: FinancialProfile = CATEGORY_FINANCIAL_PROFILES[_DEFAULT_PROFILE_NAME]


def get_financial_profile(component_category: object) -> FinancialProfile:
    category = str(component_category or "").strip()
    if category in CATEGORY_FINANCIAL_PROFILES:
        return CATEGORY_FINANCIAL_PROFILES[category]
    normalized = category.lower()
    for token, profile_name in _CATEGORY_ALIASES.items():
        if token in normalized:
            return CATEGORY_FINANCIAL_PROFILES[profile_name]
    return DEFAULT_FINANCIAL_PROFILE


def generate_standard_cost(component_category: object, rng: random.Random) -> float:
    profile = get_financial_profile(component_category)
    low = profile["unit_price_min"]
    high = profile["unit_price_max"]
    mode = low + (high - low) * 0.28
    return round(rng.triangular(low, high, mode), 2)


def generate_contract_price(standard_cost: float, rng: random.Random) -> float:
    return round(float(standard_cost) * rng.uniform(0.9, 1.25), 2)


def generate_quote_price(contract_price: float, rng: random.Random) -> float:
    return round(float(contract_price) * rng.uniform(0.95, 1.15), 2)


def generate_order_quantity(
    component_category: object,
    expected_unit_price: float,
    rng: random.Random,
    quantity_min: float | None = None,
    quantity_max: float | None = None,
) -> float:
    profile = get_financial_profile(component_category)
    low = max(profile["quantity_min"], float(quantity_min)) if quantity_min is not None else profile["quantity_min"]
    high = min(profile["quantity_max"], float(quantity_max)) if quantity_max is not None else profile["quantity_max"]
    if high < low:
        low = high
    mode = low + (high - low) * 0.35
    quantity = rng.triangular(low, high, mode)

    if rng.random() < profile["high_value_probability"]:
        amount_cap = rng.uniform(1000000.0, 1450000.0)
    else:
        amount_cap = rng.uniform(profile["line_amount_soft_max"] * 0.65, profile["line_amount_soft_max"])

    safe_unit_price = max(float(expected_unit_price), 0.01)
    quantity = min(quantity, amount_cap / safe_unit_price)
    quantity = max(low, min(high, quantity))
    return round(quantity, 2)
