"""Procurement v2 financial realism profiles for EV component sourcing."""

from __future__ import annotations

import random
from typing import TypedDict


class FinancialProfile(TypedDict):
    unit_price_min: float
    unit_price_max: float
    quantity_min: float
    quantity_max: float
    line_amount_soft_max: float
    high_value_probability: float


CATEGORY_FINANCIAL_PROFILES: dict[str, FinancialProfile] = {
    "Battery Components": {
        "unit_price_min": 100.0,
        "unit_price_max": 2500.0,
        "quantity_min": 20.0,
        "quantity_max": 300.0,
        "line_amount_soft_max": 500000.0,
        "high_value_probability": 0.025,
    },
    "Electrical Components": {
        "unit_price_min": 25.0,
        "unit_price_max": 1200.0,
        "quantity_min": 20.0,
        "quantity_max": 500.0,
        "line_amount_soft_max": 350000.0,
        "high_value_probability": 0.012,
    },
    "Powertrain Components": {
        "unit_price_min": 200.0,
        "unit_price_max": 3000.0,
        "quantity_min": 5.0,
        "quantity_max": 150.0,
        "line_amount_soft_max": 500000.0,
        "high_value_probability": 0.02,
    },
    "Thermal Management": {
        "unit_price_min": 20.0,
        "unit_price_max": 800.0,
        "quantity_min": 20.0,
        "quantity_max": 500.0,
        "line_amount_soft_max": 280000.0,
        "high_value_probability": 0.006,
    },
    "Mechanical Components": {
        "unit_price_min": 5.0,
        "unit_price_max": 500.0,
        "quantity_min": 50.0,
        "quantity_max": 1000.0,
        "line_amount_soft_max": 180000.0,
        "high_value_probability": 0.002,
    },
    "Charging Components": {
        "unit_price_min": 50.0,
        "unit_price_max": 1500.0,
        "quantity_min": 10.0,
        "quantity_max": 300.0,
        "line_amount_soft_max": 375000.0,
        "high_value_probability": 0.012,
    },
    "Safety Components": {
        "unit_price_min": 5.0,
        "unit_price_max": 300.0,
        "quantity_min": 50.0,
        "quantity_max": 1000.0,
        "line_amount_soft_max": 160000.0,
        "high_value_probability": 0.002,
    },
    "Packaging Materials": {
        "unit_price_min": 0.5,
        "unit_price_max": 100.0,
        "quantity_min": 100.0,
        "quantity_max": 5000.0,
        "line_amount_soft_max": 90000.0,
        "high_value_probability": 0.0,
    },
    "Maintenance Spares": {
        "unit_price_min": 10.0,
        "unit_price_max": 750.0,
        "quantity_min": 5.0,
        "quantity_max": 200.0,
        "line_amount_soft_max": 120000.0,
        "high_value_probability": 0.002,
    },
}

_CATEGORY_ALIASES = {
    "battery": "Battery Components",
    "electrical": "Electrical Components",
    "electronics": "Electrical Components",
    "mechanical": "Mechanical Components",
    "packaging": "Packaging Materials",
    "maintenance": "Maintenance Spares",
    "safety": "Safety Components",
    "powertrain": "Powertrain Components",
    "thermal": "Thermal Management",
    "charging": "Charging Components",
}

DEFAULT_FINANCIAL_PROFILE: FinancialProfile = CATEGORY_FINANCIAL_PROFILES["Mechanical Components"]


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
