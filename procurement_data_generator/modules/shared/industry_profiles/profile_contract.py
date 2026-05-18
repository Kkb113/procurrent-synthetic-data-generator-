"""Shared industry profile contract for future catalog-driven generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcurementProfile:
    """Procurement catalog and realism hints for an industry."""

    supplier_name_patterns: tuple[str, ...]
    component_categories: tuple[str, ...]
    component_name_patterns: tuple[str, ...]
    component_category_codes: tuple[str, ...] = field(default_factory=tuple)
    component_material_examples: dict[str, tuple[str, ...]] = field(default_factory=dict)
    component_specification_patterns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    component_uom_preferences: dict[str, tuple[str, ...]] = field(default_factory=dict)
    component_cost_profiles: dict[str, tuple[float, float]] = field(default_factory=dict)
    component_financial_profiles: dict[str, dict[str, float]] = field(default_factory=dict)
    component_category_aliases: dict[str, str] = field(default_factory=dict)
    rejection_reasons: tuple[str, ...] = field(default_factory=tuple)
    inspection_test_names: tuple[str, ...] = field(default_factory=tuple)
    safety_critical_category_terms: tuple[str, ...] = field(default_factory=tuple)
    plant_type_names: tuple[str, ...] = field(default_factory=tuple)
    warehouse_type_names: tuple[str, ...] = field(default_factory=tuple)
    supplier_component_relationship_rules: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProductionProfile:
    """Production catalog and realism hints for an industry."""

    product_categories: tuple[str, ...]
    product_name_patterns: tuple[str, ...]
    work_center_names: tuple[str, ...]
    routing_operation_names: tuple[str, ...]
    product_catalog: tuple[dict[str, object], ...] = field(default_factory=tuple)
    work_center_catalog: tuple[dict[str, str], ...] = field(default_factory=tuple)
    fallback_components: tuple[dict[str, object], ...] = field(default_factory=tuple)
    fallback_plants: tuple[dict[str, object], ...] = field(default_factory=tuple)
    fallback_warehouses: tuple[dict[str, object], ...] = field(default_factory=tuple)
    bom_patterns: tuple[str, ...] = field(default_factory=tuple)
    scrap_yield_profiles: dict[str, tuple[float, float]] = field(default_factory=dict)
    quality_defect_codes: tuple[str, ...] = field(default_factory=tuple)
    scrap_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    rework_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    cost_profiles: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class SalesProfile:
    """Sales / Order-to-Cash catalog and pricing hints for an industry."""

    customer_types: tuple[str, ...] = field(default_factory=tuple)
    customer_industries: tuple[str, ...] = field(default_factory=tuple)
    customer_name_terms: tuple[str, ...] = field(default_factory=tuple)
    sales_channels: tuple[str, ...] = field(default_factory=tuple)
    payment_terms: tuple[str, ...] = field(default_factory=tuple)
    regions: tuple[str, ...] = field(default_factory=tuple)
    price_margin_pct_range: tuple[float, float] = (20.0, 45.0)
    minimum_order_quantity_range: tuple[float, float] = (1.0, 100.0)
    fallback_price_range: tuple[float, float] = (10.0, 100.0)


@dataclass(frozen=True)
class SharedProfile:
    """Shared industry-neutral settings that are not operating-scope rules."""

    countable_uoms: tuple[str, ...]
    measurable_uoms: tuple[str, ...]
    default_country: str = "USA"
    default_currency: str = "USD"
    location_catalog: tuple[dict[str, str], ...] = field(default_factory=tuple)
    date_scope_notes: tuple[str, ...] = field(default_factory=tuple)
    realism_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IndustryProfile:
    """Top-level industry profile.

    Profiles describe catalog content and realism hints only. Plant count,
    warehouse count, and shift-code scope remain in operating_scope.py.
    """

    industry_id: str
    industry_name: str
    industry_description: str
    supported_domains: tuple[str, ...]
    procurement: ProcurementProfile
    production: ProductionProfile
    shared: SharedProfile
    sales: SalesProfile = field(default_factory=SalesProfile)
