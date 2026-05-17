"""Generic manufacturing execution industry profile placeholder."""

from __future__ import annotations

from procurement_data_generator.modules.shared.industry_profiles.profile_contract import (
    IndustryProfile,
    ProcurementProfile,
    ProductionProfile,
    SharedProfile,
)
from procurement_data_generator.modules.shared.quantity_precision import DECIMAL_QUANTITY_UOMS, INTEGER_QUANTITY_UOMS


GENERIC_MES_PROFILE = IndustryProfile(
    industry_id="generic_mes",
    industry_name="Generic Manufacturing Execution",
    industry_description="Industry-neutral catalog and realism hints for procurement-to-production execution.",
    supported_domains=("procurement", "production"),
    procurement=ProcurementProfile(
        supplier_name_patterns=(
            "{category} Supply Co",
            "{region} Industrial Partners",
            "{material} Components Ltd",
            "{category} Procurement Services",
        ),
        component_categories=(
            "Raw Materials",
            "Mechanical Components",
            "Electrical Components",
            "Consumables",
            "Packaging Materials",
            "Maintenance Spares",
        ),
        component_name_patterns=(
            "Raw Material",
            "Mechanical Component",
            "Electrical Component",
            "Assembly Fastener",
            "Packaging Set",
            "Consumable Supply",
        ),
        component_category_codes=(
            "Raw",
            "Mechanical",
            "Electrical",
            "Consumables",
            "Packaging",
            "Maintenance",
        ),
        component_uom_preferences={
            "Raw Materials": ("KG", "Meter", "Liter"),
            "Mechanical Components": ("EA", "PCS", "Set"),
            "Consumables": ("Pack", "Box", "Roll"),
            "Packaging Materials": ("Box", "Pack", "Roll"),
        },
        plant_type_names=(
            "Manufacturing Plant",
            "Assembly Plant",
            "Component Facility",
            "Production Site",
        ),
        warehouse_type_names=(
            "Raw Material Warehouse",
            "Quality Hold Warehouse",
            "Inbound Warehouse",
            "Packaging Warehouse",
        ),
        component_cost_profiles={
            "Raw Materials": (2.0, 250.0),
            "Mechanical Components": (1.0, 500.0),
            "Consumables": (0.5, 80.0),
        },
        rejection_reasons=(
            "Dimension Variance",
            "Surface Defect",
            "Packaging Damage",
            "Supplier Deviation",
            "Functional Test Failure",
        ),
        supplier_component_relationship_rules=(
            "Prefer suppliers associated with the requested component category.",
            "Use stable supplier-component pairings for repeatability.",
        ),
    ),
    production=ProductionProfile(
        product_categories=(
            "Finished Product A",
            "Finished Product B",
            "Assembly Product",
            "Packaged Product",
            "Semi Finished Assembly",
        ),
        product_name_patterns=(
            "Finished Product",
            "Assembly Product",
            "Packaged Product",
            "Semi Finished Assembly",
            "Configured Product",
        ),
        work_center_names=(
            "Material Preparation",
            "Assembly Station",
            "Calibration Station",
            "Inspection Station",
            "Packaging Line",
            "Finished Goods Receipt Area",
        ),
        routing_operation_names=(
            "Material Prep",
            "Assembly",
            "Calibration",
            "Inspection",
            "Packaging",
            "Release",
        ),
        product_catalog=(
            {"name": "Finished Product A", "category": "Finished Product", "product_type": "FinishedGood", "uom": "EA", "base_cost": 1000, "base_hours": 4},
            {"name": "Finished Product B", "category": "Finished Product", "product_type": "FinishedGood", "uom": "EA", "base_cost": 1200, "base_hours": 5},
            {"name": "Assembly Product", "category": "Assembly", "product_type": "SemiFinished", "uom": "EA", "base_cost": 750, "base_hours": 3},
        ),
        work_center_catalog=(
            {"name": "Material Preparation", "line_name": "Preparation"},
            {"name": "Assembly Station", "line_name": "Assembly"},
            {"name": "Calibration Station", "line_name": "Calibration"},
            {"name": "Inspection Station", "line_name": "Inspection"},
            {"name": "Packaging Line", "line_name": "Packaging"},
        ),
        fallback_components=(
            {"ComponentID": 1, "ComponentName": "Mechanical Component", "UOM": "EA"},
            {"ComponentID": 2, "ComponentName": "Electrical Component", "UOM": "EA"},
            {"ComponentID": 3, "ComponentName": "Raw Material", "UOM": "KG"},
            {"ComponentID": 4, "ComponentName": "Assembly Fastener", "UOM": "Set"},
            {"ComponentID": 5, "ComponentName": "Packaging Set", "UOM": "Pack"},
        ),
        fallback_plants=(
            {"PlantID": 1, "PlantName": "Main Manufacturing Plant"},
        ),
        fallback_warehouses=(
            {"WarehouseID": 1, "PlantID": 1, "WarehouseName": "Main Raw Material Warehouse"},
        ),
        bom_patterns=(
            "Finished products consume raw materials, components, consumables, and packaging.",
            "Semi finished assemblies can feed later finished product receipts.",
        ),
        scrap_yield_profiles={
            "Assembly": (0.0, 3.0),
            "Inspection": (0.0, 2.0),
            "Packaging": (0.0, 1.0),
        },
        quality_defect_codes=(
            "DimensionalIssue",
            "AssemblyDefect",
            "SurfaceDefect",
            "FunctionalFailure",
            "PackagingDefect",
        ),
        scrap_reason_codes=(
            "Process Defect",
            "Assembly Scrap",
            "Inspection Scrap",
        ),
        rework_reason_codes=(
            "ReassemblyRequired",
            "CalibrationAdjustment",
            "InspectionCorrection",
            "PackagingRework",
        ),
        cost_profiles={
            "LaborRatePerHour": (20.0, 70.0),
            "OverheadPct": (5.0, 20.0),
            "ProductionLaborCostPerOperation": (35.0, 80.0),
            "ProductionOverheadPct": (8.0, 20.0),
            "ScrapCostPerUnit": (35.0, 160.0),
            "ReworkCostPerUnit": (25.0, 125.0),
        },
    ),
    shared=SharedProfile(
        countable_uoms=tuple(sorted(INTEGER_QUANTITY_UOMS)),
        measurable_uoms=tuple(sorted(DECIMAL_QUANTITY_UOMS)),
        default_country="USA",
        default_currency="USD",
        date_scope_notes=("Current generated scenarios remain in calendar year 2025.",),
        realism_notes=(
            "Generic profile avoids industry-specific product labels.",
            "Operating scope is intentionally separate from industry profile content.",
        ),
    ),
)
