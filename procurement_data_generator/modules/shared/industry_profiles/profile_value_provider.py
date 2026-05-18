"""Small access layer for profile-driven generator vocabulary and policies."""

from __future__ import annotations

from typing import Any

from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile


LEGACY_MANUFACTURING_LOCATIONS: tuple[dict[str, str], ...] = (
    {"city": "Detroit", "state": "Michigan", "zip": "48201", "country": "USA"},
    {"city": "Austin", "state": "Texas", "zip": "73301", "country": "USA"},
    {"city": "Fremont", "state": "California", "zip": "94536", "country": "USA"},
    {"city": "Phoenix", "state": "Arizona", "zip": "85001", "country": "USA"},
    {"city": "Nashville", "state": "Tennessee", "zip": "37201", "country": "USA"},
    {"city": "Columbus", "state": "Ohio", "zip": "43004", "country": "USA"},
    {"city": "Reno", "state": "Nevada", "zip": "89501", "country": "USA"},
    {"city": "Greenville", "state": "South Carolina", "zip": "29601", "country": "USA"},
)

DEFAULT_PROCUREMENT_REJECTION_REASONS: tuple[str, ...] = (
    "Dimension Out of Tolerance",
    "Surface Defect",
    "Electrical Test Failure",
    "Packaging Damage",
    "Material Contamination",
    "Wrong Specification",
    "Thermal Stress Failure",
    "Supplier Documentation Issue",
    "Visual Defect",
    "Functional Test Failure",
)

DEFAULT_PROCUREMENT_INSPECTION_TEST_NAMES: tuple[str, ...] = (
    "Electrical Test",
    "Dimensional Inspection",
    "Visual Inspection",
    "Functional Test",
)

DEFAULT_SALES_CUSTOMER_TYPES: tuple[str, ...] = (
    "Direct Customer",
    "Distributor",
    "Retailer",
    "Wholesale Customer",
    "E-commerce",
)

DEFAULT_SALES_CUSTOMER_INDUSTRIES: tuple[str, ...] = (
    "Manufacturing",
    "Distribution",
    "Retail",
    "Wholesale",
    "Online Commerce",
)

DEFAULT_SALES_CUSTOMER_NAME_TERMS: tuple[str, ...] = (
    "Apex",
    "Metro",
    "Summit",
    "Prime",
    "Pioneer",
    "CityLine",
    "Northstar",
    "Meridian",
)

DEFAULT_SALES_CHANNELS: tuple[str, ...] = (
    "DIRECT",
    "DISTRIBUTOR",
    "RETAIL",
    "ONLINE",
    "EXPORT",
)

DEFAULT_SALES_PAYMENT_TERMS: tuple[str, ...] = ("Net 15", "Net 30", "Net 45", "Net 60")

DEFAULT_SALES_REGIONS: tuple[str, ...] = ("North", "South", "East", "West", "Central")


class IndustryProfileValueProvider:
    """Expose profile values with stable defaults for existing generators."""

    def __init__(self, profile: IndustryProfile) -> None:
        self.profile = profile

    @property
    def default_country(self) -> str:
        return str(self.profile.shared.default_country or "USA").strip() or "USA"

    @property
    def default_currency(self) -> str:
        return str(self.profile.shared.default_currency or "USD").strip() or "USD"

    def location_catalog(self) -> tuple[dict[str, str], ...]:
        locations = tuple(_normalize_location(location, self.default_country) for location in self.profile.shared.location_catalog)
        locations = tuple(location for location in locations if location["city"])
        return locations or LEGACY_MANUFACTURING_LOCATIONS

    def procurement_rejection_reasons(self) -> tuple[str, ...]:
        reasons = tuple(str(reason).strip() for reason in self.profile.procurement.rejection_reasons if str(reason).strip())
        return reasons or DEFAULT_PROCUREMENT_REJECTION_REASONS

    def procurement_inspection_test_names(self) -> tuple[str, ...]:
        return tuple(
            str(test_name).strip()
            for test_name in self.profile.procurement.inspection_test_names
            if str(test_name).strip()
        )

    def fallback_procurement_inspection_test_names(self) -> tuple[str, ...]:
        return DEFAULT_PROCUREMENT_INSPECTION_TEST_NAMES

    def is_procurement_safety_critical_category(self, category: object) -> bool:
        normalized = str(category or "").strip().lower()
        if not normalized:
            return False
        terms = tuple(
            str(term).strip().lower()
            for term in self.profile.procurement.safety_critical_category_terms
            if str(term).strip()
        )
        return normalized in terms

    def production_scrap_reason_codes(self) -> tuple[str, ...]:
        reasons = tuple(str(reason).strip() for reason in self.profile.production.scrap_reason_codes if str(reason).strip())
        return reasons or ("Process Defect",)

    def production_rework_reason_codes(self) -> tuple[str, ...]:
        reasons = tuple(str(reason).strip() for reason in self.profile.production.rework_reason_codes if str(reason).strip())
        return reasons or ("Rework Hold",)

    def production_cost_range(self, key: str, default: tuple[float, float]) -> tuple[float, float]:
        raw = self.profile.production.cost_profiles.get(key)
        if raw is None or len(raw) < 2:
            return default
        low, high = float(raw[0]), float(raw[1])
        if high < low:
            low, high = high, low
        return low, high

    def production_percentage_range(self, key: str, default: tuple[float, float]) -> tuple[float, float]:
        low, high = self.production_cost_range(key, default)
        if low > 1 or high > 1:
            return low / 100.0, high / 100.0
        return low, high

    def sales_customer_types(self) -> tuple[str, ...]:
        values = tuple(str(value).strip() for value in self.profile.sales.customer_types if str(value).strip())
        return values or DEFAULT_SALES_CUSTOMER_TYPES

    def sales_customer_industries(self) -> tuple[str, ...]:
        values = tuple(str(value).strip() for value in self.profile.sales.customer_industries if str(value).strip())
        return values or DEFAULT_SALES_CUSTOMER_INDUSTRIES

    def sales_customer_name_terms(self) -> tuple[str, ...]:
        values = tuple(str(value).strip() for value in self.profile.sales.customer_name_terms if str(value).strip())
        return values or DEFAULT_SALES_CUSTOMER_NAME_TERMS

    def sales_channels(self) -> tuple[str, ...]:
        values = tuple(str(value).strip().upper() for value in self.profile.sales.sales_channels if str(value).strip())
        return values or DEFAULT_SALES_CHANNELS

    def sales_payment_terms(self) -> tuple[str, ...]:
        values = tuple(str(value).strip() for value in self.profile.sales.payment_terms if str(value).strip())
        return values or DEFAULT_SALES_PAYMENT_TERMS

    def sales_regions(self) -> tuple[str, ...]:
        values = tuple(str(value).strip() for value in self.profile.sales.regions if str(value).strip())
        return values or DEFAULT_SALES_REGIONS

    def sales_margin_pct_range(self) -> tuple[float, float]:
        return _normalize_percentage_range(self.profile.sales.price_margin_pct_range, (0.20, 0.45))

    def sales_minimum_order_quantity_range(self) -> tuple[float, float]:
        return _normalize_numeric_range(self.profile.sales.minimum_order_quantity_range, (1.0, 100.0), minimum=0.0)

    def sales_fallback_price_range(self) -> tuple[float, float]:
        return _normalize_numeric_range(self.profile.sales.fallback_price_range, (10.0, 100.0), minimum=0.01)


def _normalize_location(location: dict[str, Any], default_country: str) -> dict[str, str]:
    return {
        "city": str(location.get("city") or location.get("City") or "").strip(),
        "state": str(location.get("state") or location.get("State") or "").strip(),
        "zip": str(location.get("zip") or location.get("zip_code") or location.get("ZipCode") or "").strip(),
        "country": str(location.get("country") or location.get("Country") or default_country).strip() or default_country,
    }


def _normalize_numeric_range(
    value: tuple[float, float],
    default: tuple[float, float],
    minimum: float | None = None,
) -> tuple[float, float]:
    if len(value) < 2:
        low, high = default
    else:
        low, high = float(value[0]), float(value[1])
    if high < low:
        low, high = high, low
    if minimum is not None:
        low = max(minimum, low)
        high = max(low, high)
    return low, high


def _normalize_percentage_range(value: tuple[float, float], default: tuple[float, float]) -> tuple[float, float]:
    low, high = _normalize_numeric_range(value, default, minimum=0.0)
    if low > 1 or high > 1:
        low, high = low / 100.0, high / 100.0
    return low, high
