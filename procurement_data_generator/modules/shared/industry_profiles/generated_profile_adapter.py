"""Convert validated LLM scenario hints into runtime industry profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from procurement_data_generator.core.llm.industry_scenario_contract import IndustryScenarioPlan
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import (
    IndustryProfile,
    ProcurementProfile,
    ProductionProfile,
    SalesProfile,
    SharedProfile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import industry_profile_to_dict
from procurement_data_generator.modules.shared.quantity_precision import DECIMAL_QUANTITY_UOMS, INTEGER_QUANTITY_UOMS


@dataclass(frozen=True)
class GeneratedIndustryProfile:
    """Runtime profile plus provenance for artifact/report writing."""

    profile: IndustryProfile
    source: str
    fallback_used: bool
    naming_style: str
    geography_terms: tuple[str, ...]
    seasonality: tuple[str, ...]
    quality_or_regulatory_terms: tuple[str, ...]

    def to_artifact_dict(self) -> dict[str, Any]:
        payload = industry_profile_to_dict(self.profile)
        payload.update(
            {
                "source": self.source,
                "fallback_used": self.fallback_used,
                "naming_style": self.naming_style,
                "geography_terms": list(self.geography_terms),
                "seasonality": list(self.seasonality),
                "quality_or_regulatory_terms": list(self.quality_or_regulatory_terms),
            }
        )
        return payload


def build_generated_industry_profile(
    scenario: IndustryScenarioPlan,
    *,
    fallback_used: bool = False,
    source: str | None = None,
) -> GeneratedIndustryProfile:
    """Build a deterministic runtime profile from validated scenario hints."""

    family = _industry_family(scenario)
    defaults = _defaults_for_family(family)
    profile = IndustryProfile(
        industry_id=scenario.industry_id,
        industry_name=scenario.industry_name,
        industry_description=scenario.business_summary,
        supported_domains=("procurement", "production", "sales"),
        procurement=_procurement_profile(scenario, defaults),
        production=_production_profile(scenario, defaults),
        shared=_shared_profile(scenario, defaults),
        sales=_sales_profile(scenario, defaults),
    )
    return GeneratedIndustryProfile(
        profile=profile,
        source=source or ("fallback" if fallback_used else "llm_scenario"),
        fallback_used=fallback_used,
        naming_style=scenario.shared.naming_style,
        geography_terms=tuple(scenario.shared.geography_terms or defaults["geography_terms"]),
        seasonality=tuple(scenario.shared.seasonality or defaults["seasonality"]),
        quality_or_regulatory_terms=tuple(
            _dedupe([*scenario.shared.regulatory_or_quality_terms, *defaults["quality_terms"]])
        ),
    )


def _procurement_profile(scenario: IndustryScenarioPlan, defaults: dict[str, Any]) -> ProcurementProfile:
    supplier_types = _values_or_default(scenario.procurement.supplier_types, defaults["supplier_types"])
    component_categories = _values_or_default(scenario.procurement.component_categories, defaults["component_categories"])
    raw_terms = _values_or_default(scenario.procurement.raw_material_terms, defaults["raw_material_terms"])
    quality_terms = _values_or_default(scenario.procurement.inspection_or_quality_hints, defaults["quality_terms"])
    category_examples = _component_examples(component_categories, raw_terms, defaults["component_examples"])
    return ProcurementProfile(
        supplier_name_patterns=tuple(supplier_types),
        component_categories=tuple(component_categories),
        component_name_patterns=tuple(raw_terms),
        component_category_codes=tuple(_dedupe([*component_categories, *defaults["component_category_codes"]])),
        component_material_examples=category_examples,
        component_specification_patterns={
            category: tuple(_dedupe([*quality_terms, *defaults["specification_terms"]]))
            for category in category_examples
        },
        component_uom_preferences=dict(defaults["component_uom_preferences"]),
        component_cost_profiles={category: tuple(defaults["component_cost_range"]) for category in category_examples},
        component_category_aliases={category.lower(): category for category in component_categories},
        rejection_reasons=tuple(_dedupe([*scenario.procurement.supplier_risk_factors, *defaults["rejection_reasons"]])),
        inspection_test_names=tuple(quality_terms),
        safety_critical_category_terms=tuple(defaults["safety_critical_terms"]),
        plant_type_names=tuple(defaults["plant_type_names"]),
        warehouse_type_names=tuple(defaults["warehouse_type_names"]),
        supplier_component_relationship_rules=tuple(
            _dedupe([*scenario.procurement.purchasing_patterns, *defaults["supplier_component_rules"]])
        ),
    )


def _production_profile(scenario: IndustryScenarioPlan, defaults: dict[str, Any]) -> ProductionProfile:
    product_families = _values_or_default(scenario.production.product_families, defaults["product_families"])
    finished_goods = _values_or_default(scenario.production.finished_good_terms, defaults["finished_good_terms"])
    work_centers = _values_or_default(scenario.production.work_center_terms, defaults["work_center_terms"])
    operations = _values_or_default(scenario.production.production_process_terms, defaults["operation_terms"])
    routing_patterns = _values_or_default(scenario.production.routing_patterns, defaults["routing_patterns"])
    scrap_terms = _values_or_default(scenario.production.scrap_or_yield_hints, defaults["scrap_terms"])
    product_catalog = tuple(
        {
            "name": name,
            "category": product_families[index % len(product_families)],
            "product_type": "FinishedGood",
            "uom": "EA",
            "base_cost": defaults["base_costs"][index % len(defaults["base_costs"])],
            "base_hours": defaults["base_hours"][index % len(defaults["base_hours"])],
        }
        for index, name in enumerate(finished_goods)
    )
    work_center_catalog = tuple(
        {"name": name, "line_name": _line_name(name)}
        for name in work_centers
    )
    fallback_components = tuple(
        {"ComponentID": index, "ComponentName": component_name, "UOM": _component_uom(component_name)}
        for index, component_name in enumerate(defaults["fallback_component_names"], start=1)
    )
    return ProductionProfile(
        product_categories=tuple(product_families),
        product_name_patterns=tuple(finished_goods),
        work_center_names=tuple(work_centers),
        routing_operation_names=tuple(operations),
        product_catalog=product_catalog,
        work_center_catalog=work_center_catalog,
        fallback_components=fallback_components,
        fallback_plants=(
            {"PlantID": 1, "PlantName": f"{defaults['primary_location']} {defaults['plant_type_names'][0]}"},
        ),
        fallback_warehouses=(
            {"WarehouseID": 1, "PlantID": 1, "WarehouseName": f"{defaults['primary_location']} {defaults['warehouse_type_names'][0]}"},
        ),
        bom_patterns=tuple(routing_patterns),
        scrap_yield_profiles={operation: tuple(defaults["scrap_yield_range"]) for operation in operations[:5]},
        quality_defect_codes=tuple(defaults["quality_defect_codes"]),
        scrap_reason_codes=tuple(scrap_terms),
        rework_reason_codes=tuple(defaults["rework_reason_codes"]),
        cost_profiles=dict(defaults["cost_profiles"]),
    )


def _sales_profile(scenario: IndustryScenarioPlan, defaults: dict[str, Any]) -> SalesProfile:
    return SalesProfile(
        customer_types=tuple(_values_or_default(scenario.sales.customer_types, defaults["customer_types"])),
        customer_industries=tuple(_values_or_default(scenario.sales.customer_industries, defaults["customer_industries"])),
        customer_name_terms=tuple(_values_or_default(scenario.sales.customer_types + scenario.sales.customer_industries, defaults["customer_name_terms"])),
        sales_channels=tuple(_values_or_default(scenario.sales.sales_channels, defaults["sales_channels"])),
        payment_terms=tuple(_values_or_default(scenario.sales.payment_terms, defaults["payment_terms"])),
        regions=tuple(_values_or_default(scenario.sales.region_terms, defaults["region_terms"])),
        carrier_names=tuple(defaults["carrier_names"]),
        payment_methods=tuple(defaults["payment_methods"]),
        tax_rate_pct=float(defaults["tax_rate_pct"]),
        freight_amount_range=tuple(defaults["freight_amount_range"]),
        partial_payment_pct_range=tuple(defaults["partial_payment_pct_range"]),
        return_reasons=tuple(_values_or_default(scenario.sales.return_reasons, defaults["return_reasons"])),
        return_rate_range=tuple(defaults["return_rate_range"]),
        restock_pct_range=tuple(defaults["restock_pct_range"]),
        price_margin_pct_range=tuple(defaults["price_margin_pct_range"]),
        minimum_order_quantity_range=tuple(defaults["minimum_order_quantity_range"]),
        fallback_price_range=tuple(defaults["fallback_price_range"]),
    )


def _shared_profile(scenario: IndustryScenarioPlan, defaults: dict[str, Any]) -> SharedProfile:
    locations = tuple(
        {"city": city, "state": defaults["state"], "zip": defaults["zip"], "country": defaults["country"]}
        for city in _values_or_default(scenario.shared.geography_terms, defaults["geography_terms"])
    )
    return SharedProfile(
        countable_uoms=tuple(sorted(INTEGER_QUANTITY_UOMS | set(defaults["countable_uoms"]))),
        measurable_uoms=tuple(sorted(DECIMAL_QUANTITY_UOMS | set(defaults["measurable_uoms"]))),
        default_country=defaults["country"],
        default_currency=scenario.shared.currency or defaults["currency"],
        location_catalog=locations,
        date_scope_notes=("Generated scenarios remain in calendar year 2025.",),
        realism_notes=(
            "Generated profile was derived from validated IndustryScenarioPlan hints.",
            "Python remains responsible for rows, lifecycle logic, formulas, reconciliation, and validation.",
        ),
    )


def _industry_family(scenario: IndustryScenarioPlan) -> str:
    text = " ".join([scenario.industry_id, scenario.industry_name, scenario.business_summary]).lower()
    if any(term in text for term in ("pharma", "pharmaceutical", "medicine", "hospital", "sterile")):
        return "pharma"
    if any(term in text for term in ("food", "beverage", "snack", "grocery", "ingredient")):
        return "food"
    if any(term in text for term in ("ev", "electric vehicle", "battery", "automotive", "motor", "inverter")):
        return "ev"
    return "general"


def _defaults_for_family(family: str) -> dict[str, Any]:
    defaults = {
        "general": {
            "supplier_types": ["Component Supplier", "Raw Material Supplier", "Packaging Supplier"],
            "component_categories": ["Raw Materials", "Mechanical Components", "Electrical Components", "Packaging Materials"],
            "raw_material_terms": ["Industrial Sheet Metal", "Engineering Polymer", "Control Cable", "Packaging Set"],
            "component_examples": ["Industrial Sheet Metal", "Engineering Polymer", "Control Cable", "Packaging Set"],
            "component_category_codes": ["Raw", "Mechanical", "Electrical", "Packaging", "Maintenance"],
            "quality_terms": ["Incoming Inspection", "Quality Certificate", "Supplier Deviation"],
            "specification_terms": ["Industrial Grade", "Standard Pack", "Grade A"],
            "rejection_reasons": ["Dimension Variance", "Packaging Damage", "Supplier Deviation"],
            "safety_critical_terms": ["Safety", "Electrical"],
            "product_families": ["Finished Goods", "Assembly Products"],
            "finished_good_terms": ["Finished Product", "Assembly Product", "Packaged Product"],
            "work_center_terms": ["Material Preparation", "Assembly Station", "Inspection Station", "Packaging Line"],
            "operation_terms": ["Material Prep", "Assembly", "Inspection", "Packaging", "Release"],
            "routing_patterns": ["Finished products consume raw materials, components, and packaging."],
            "scrap_terms": ["Process Defect", "Inspection Scrap", "Packaging Scrap"],
            "fallback_component_names": ["Industrial Sheet Metal", "Control Cable", "Fastener Kit", "Packaging Set"],
            "quality_defect_codes": ["DimensionalIssue", "FunctionalFailure", "PackagingDefect"],
            "rework_reason_codes": ["ReassemblyRequired", "InspectionCorrection", "PackagingRework"],
            "customer_types": ["Distributor", "Retail Customer", "Industrial Customer"],
            "customer_industries": ["Manufacturing", "Distribution", "Retail"],
            "customer_name_terms": ["Apex", "Metro", "Summit", "Prime"],
            "sales_channels": ["DIRECT", "DISTRIBUTOR", "RETAIL", "ONLINE"],
            "return_reasons": ["Quality Complaint", "Shipping Damage", "Wrong Item"],
            "region_terms": ["North", "South", "East", "West"],
        },
        "food": {
            "supplier_types": ["Food Ingredient Supplier", "Packaging Supplier", "Cold Chain Supplier"],
            "component_categories": ["Food Ingredients", "Seasonings", "Edible Oils", "Packaging Materials"],
            "raw_material_terms": ["Wheat Flour", "Cocoa Powder", "Flavoring", "Bottle", "Carton", "Label"],
            "component_examples": ["Wheat Flour", "Cocoa Powder", "Flavoring", "PET Bottle", "Corrugated Carton", "Nutrition Label"],
            "component_category_codes": ["Packaging", "Raw Ingredient", "Seasoning", "Edible Oil", "Carton", "Label"],
            "quality_terms": ["Food Grade", "Allergen Declared", "Expiry Controlled", "Batch Certified"],
            "specification_terms": ["Food Grade", "Low Moisture", "Batch Certified", "Expiry Controlled"],
            "rejection_reasons": ["Moisture Out of Spec", "Foreign Material Detected", "Expired Lot", "Label Print Defect"],
            "safety_critical_terms": ["Food Safety", "Ingredient"],
            "product_families": ["Snack Foods", "Beverages", "Packaged Foods"],
            "finished_good_terms": ["Protein Bar", "Fruit Juice", "Snack Mix", "Dairy Drink"],
            "work_center_terms": ["Mixing Station", "Baking Line", "Filling Line", "Packaging Line", "Cold Storage"],
            "operation_terms": ["Blend Ingredients", "Heat Process", "Fill", "Pack", "Label"],
            "routing_patterns": ["Food products consume ingredients, packaging, labels, and batch-controlled lots."],
            "scrap_terms": ["Expired Batch", "Seal Failure", "Underweight Pack"],
            "fallback_component_names": ["Wheat Flour", "Cocoa Powder", "Flavoring", "Bottle", "Carton", "Label"],
            "quality_defect_codes": ["MoistureOutOfSpec", "SealFailure", "ExpiredLot", "LabelingIssue"],
            "rework_reason_codes": ["Repack", "Relabel", "Reinspect"],
            "customer_types": ["Grocery Chain", "Distributor", "Retailer", "Foodservice Buyer"],
            "customer_industries": ["Grocery", "Retail Food", "Foodservice", "Wholesale Distribution"],
            "customer_name_terms": ["Grocery", "FreshMart", "Foodservice", "Retail"],
            "sales_channels": ["RETAIL_DISTRIBUTION", "WHOLESALE", "FOODSERVICE", "ECOMMERCE"],
            "return_reasons": ["Expired Product", "Damaged Packaging", "Quality Complaint", "Temperature Excursion"],
            "region_terms": ["North", "South", "East", "West"],
        },
        "ev": {
            "supplier_types": ["Battery Systems Supplier", "Electronics Supplier", "Motor Assembly Supplier"],
            "component_categories": ["Battery Components", "Power Electronics", "Motors", "Wiring Harnesses"],
            "raw_material_terms": ["Battery Cell", "Inverter Module", "Copper Wire", "Wiring Harness", "Sensor", "Controller"],
            "component_examples": ["Battery Cell", "Inverter Module", "Copper Wire", "Wiring Harness", "Sensor", "Controller"],
            "component_category_codes": ["Battery", "Electrical", "Mechanical", "Electronics", "Safety", "Packaging"],
            "quality_terms": ["Automotive Grade", "High Voltage", "IP67", "Functional Test"],
            "specification_terms": ["Automotive Grade", "High Voltage", "IP67", "Grade A"],
            "rejection_reasons": ["Electrical Test Failure", "Thermal Stress Failure", "Connector Fitment Issue"],
            "safety_critical_terms": ["Battery", "Safety", "High Voltage"],
            "product_families": ["Battery Modules", "Drive Units", "Control Modules"],
            "finished_good_terms": ["Battery Module", "Drive Unit", "Control Module", "Harness Assembly"],
            "work_center_terms": ["Cell Assembly", "Motor Assembly", "Electronics Assembly", "Final Inspection"],
            "operation_terms": ["Assemble Pack", "Test Inverter", "Calibrate Controller", "Inspect Harness"],
            "routing_patterns": ["EV assemblies consume battery, motor, inverter, harness, sensor, and controller components."],
            "scrap_terms": ["Electrical Test Scrap", "Thermal Leak Scrap", "Calibration Scrap"],
            "fallback_component_names": ["Battery Cell", "Inverter Module", "Copper Wire", "Wiring Harness", "Sensor", "Controller"],
            "quality_defect_codes": ["ElectricalContinuityFailure", "CalibrationFailure", "ConnectorFitmentIssue"],
            "rework_reason_codes": ["ConnectorReseat", "CalibrationRetry", "HarnessCorrection"],
            "customer_types": ["OEM", "EV Dealer", "Fleet Operator", "Automotive Distributor"],
            "customer_industries": ["Automotive OEM", "Dealer Network", "Fleet Sales", "Aftermarket Distribution"],
            "customer_name_terms": ["OEM", "Dealer", "Fleet", "Automotive"],
            "sales_channels": ["OEM_CONTRACT", "DEALER_NETWORK", "FLEET_SALES", "AFTERMARKET_DISTRIBUTION"],
            "return_reasons": ["Warranty Return", "Shipping Damage", "Fitment Issue", "Quality Complaint"],
            "region_terms": ["North", "South", "East", "West"],
        },
        "pharma": {
            "supplier_types": ["API Supplier", "Excipient Supplier", "Sterile Packaging Supplier", "Regulated Supplier"],
            "component_categories": ["Active Ingredients", "Excipients", "Sterile Packaging", "Laboratory Supplies"],
            "raw_material_terms": ["Active Ingredient", "Excipient", "Vial", "Blister Pack", "Capsule Shell", "Sterile Stopper"],
            "component_examples": ["Active Ingredient", "Excipient", "Sterile Vial", "Blister Pack", "Capsule Shell", "Oral Syrup Bottle"],
            "component_category_codes": ["API", "Excipient", "Packaging", "Sterile Packaging", "Laboratory"],
            "quality_terms": ["USP Grade", "Sterile", "GMP Released", "Batch Certified"],
            "specification_terms": ["USP Grade", "Sterile", "GMP Released", "Analytical Grade"],
            "rejection_reasons": ["Sterility Failure", "Assay Out of Spec", "Documentation Deviation", "Packaging Integrity Failure"],
            "safety_critical_terms": ["API", "Sterile"],
            "product_families": ["Tablets", "Capsules", "Sterile Vials", "Oral Syrups"],
            "finished_good_terms": ["Tablet Batch", "Capsule Batch", "Sterile Vial", "Oral Syrup"],
            "work_center_terms": ["Granulation", "Compression", "Coating", "Filling", "Sterile Packing"],
            "operation_terms": ["Blend API", "Compress Tablet", "Inspect Batch", "Fill Vial", "Package"],
            "routing_patterns": ["Pharma products consume active ingredients, excipients, and sterile packaging with batch traceability."],
            "scrap_terms": ["Assay Failure", "Sterility Hold", "Packaging Integrity Failure"],
            "fallback_component_names": ["Active Ingredient", "Excipient", "Sterile Vial", "Blister Pack", "Capsule Shell"],
            "quality_defect_codes": ["AssayOutOfSpec", "SterilityFailure", "PackagingIntegrityFailure"],
            "rework_reason_codes": ["ReinspectBatch", "Repackage", "QualityHoldReview"],
            "customer_types": ["Hospital", "Pharmacy", "Healthcare Distributor", "Wholesaler"],
            "customer_industries": ["Hospital Network", "Pharmacy Retail", "Healthcare Distribution", "Medical Wholesale"],
            "customer_name_terms": ["Hospital", "Pharmacy", "Healthcare", "Medical"],
            "sales_channels": ["INSTITUTIONAL_SALES", "DISTRIBUTOR_CHANNEL", "PHARMACY_NETWORK", "WHOLESALE"],
            "return_reasons": ["Recall Return", "Expired Product", "Temperature Excursion", "Documentation Issue"],
            "region_terms": ["North", "South", "East", "West"],
        },
    }
    base = {**defaults["general"], **defaults.get(family, {})}
    base.update(
        {
            "country": "USA",
            "currency": "USD",
            "state": "State",
            "zip": "10001",
            "geography_terms": ["Detroit", "Austin", "Fremont", "Phoenix"] if family == "ev" else ["Chicago", "Dallas", "Atlanta", "Seattle"],
            "seasonality": ["standard business calendar"],
            "primary_location": "Detroit" if family == "ev" else "Chicago",
            "plant_type_names": base.get("plant_type_names", ["Manufacturing Plant", "Processing Plant"]),
            "warehouse_type_names": base.get("warehouse_type_names", ["Raw Material Warehouse", "Packaging Warehouse"]),
            "component_uom_preferences": {
                "Food Ingredients": ("KG", "Liter"),
                "Active Ingredients": ("KG", "Gram"),
                "Battery Components": ("EA", "Set"),
                "Packaging Materials": ("EA", "Pack", "Roll"),
            },
            "component_cost_range": (1.0, 250.0),
            "base_costs": [12, 20, 35] if family == "food" else [1200, 2500, 4000] if family == "ev" else [18, 45, 70] if family == "pharma" else [100, 250, 500],
            "base_hours": [1.0, 1.5, 2.0],
            "scrap_yield_range": (0.0, 3.0),
            "cost_profiles": {
                "LaborRatePerHour": (20.0, 70.0),
                "OverheadPct": (5.0, 20.0),
                "ProductionLaborCostPerOperation": (35.0, 80.0),
                "ProductionOverheadPct": (8.0, 20.0),
                "ScrapCostPerUnit": (5.0, 120.0),
                "ReworkCostPerUnit": (5.0, 80.0),
            },
            "payment_terms": ["Net 15", "Net 30", "Net 45", "Net 60"],
            "carrier_names": ["Regional Logistics", "Express Distribution", "Certified Freight"],
            "payment_methods": ["BankTransfer", "Card", "OnlineTransfer", "Cheque"],
            "tax_rate_pct": 8.0,
            "freight_amount_range": (50.0, 750.0),
            "partial_payment_pct_range": (25.0, 75.0),
            "return_rate_range": (2.0, 5.0),
            "restock_pct_range": (60.0, 90.0),
            "price_margin_pct_range": (20.0, 45.0),
            "minimum_order_quantity_range": (1.0, 100.0),
            "fallback_price_range": (10.0, 250.0),
            "countable_uoms": {"EA", "Pack", "Set", "Box"},
            "measurable_uoms": {"KG", "Gram", "Liter", "Meter", "Roll"},
            "supplier_component_rules": ["Prefer suppliers associated with the generated component vocabulary."],
        }
    )
    return base


def _component_examples(categories: list[str], raw_terms: list[str], default_examples: list[str]) -> dict[str, tuple[str, ...]]:
    examples = _dedupe([*raw_terms, *default_examples])
    return {
        category: tuple(examples[index:: max(1, len(categories))] or examples[:3])
        for index, category in enumerate(categories)
    }


def _component_uom(name: str) -> str:
    normalized = name.lower()
    if any(term in normalized for term in ("flour", "powder", "ingredient", "excipient", "api")):
        return "KG"
    if any(term in normalized for term in ("oil", "syrup")):
        return "Liter"
    if any(term in normalized for term in ("wire", "film", "label")):
        return "Roll"
    return "EA"


def _line_name(value: str) -> str:
    words = str(value).replace("-", " ").split()
    return words[0] if words else "Line"


def _values_or_default(values: Iterable[str], default: Iterable[str]) -> list[str]:
    return _dedupe([*values, *default]) or list(default)


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output
