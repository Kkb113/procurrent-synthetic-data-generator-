"""Prompt builder for Azure OpenAI-generated industry profiles."""

from __future__ import annotations


def build_industry_profile_prompt(industry: str, description: str | None = None, profile_id: str | None = None) -> str:
    """Build a focused prompt for structured industry profile JSON generation."""

    industry_text = str(industry or "").strip()
    description_text = str(description or "").strip()
    suggested_id = str(profile_id or "").strip()
    context_line = f"Context: {description_text}" if description_text else "Context: Procurement, Production Execution, and Sales synthetic data profile."
    profile_id_line = f'Use industry_id "{suggested_id}".' if suggested_id else "Create a lowercase snake_case industry_id."

    return f"""
Generate one industry profile for: {industry_text}
{context_line}
{profile_id_line}

Return JSON only.
Do not include markdown.
Do not include explanations.
Do not generate table rows.
Do not generate sample CSV data.
Generate only catalog/profile content.

The profile must support the full MES lifecycle: Procurement -> Production Execution -> Sales.
Keep schemas, lifecycle logic, formulas, reconciliation, and operating scope outside the profile.
Include procurement supplier/component/raw material vocabulary, production product/BOM/work center/routing vocabulary, and sales customer/channel/payment/region/return vocabulary.
Do not include unrelated MES areas such as OEE, downtime, maintenance execution, labor tracking, warranty, or service operations.
Keep the profile compatible with 2025-only synthetic data generation.
Respect countable vs measurable UOM concepts.

Return one JSON object with this shape:
{{
  "industry_id": "snake_case_id",
  "industry_name": "Readable Industry Name",
  "industry_description": "Short description of catalog and realism hints.",
  "supported_domains": ["procurement", "production", "sales"],
  "procurement": {{
    "supplier_name_patterns": ["{{category}} Supply Co", "{{region}} Components"],
    "component_categories": ["Category A", "Category B"],
    "component_name_patterns": ["Specific Component Name"],
    "component_category_codes": ["Raw", "Mechanical", "Electrical", "Packaging"],
    "component_material_examples": {{"Category A": ["Example Component"]}},
    "component_specification_patterns": {{"Category A": ["Grade A", "Standard Pack"]}},
    "component_uom_preferences": {{"Category A": ["EA", "KG"]}},
    "component_cost_profiles": {{"Category A": [1.0, 100.0]}},
    "supplier_component_relationship_rules": ["Rule text"]
  }},
  "production": {{
    "product_categories": ["Finished Product"],
    "product_name_patterns": ["Finished Product A"],
    "work_center_names": ["Assembly Station", "Inspection Station"],
    "routing_operation_names": ["Material Prep", "Assembly", "Inspection", "Packaging"],
    "product_catalog": [
      {{"name": "Finished Product A", "category": "Finished Product", "product_type": "FinishedGood", "uom": "EA", "base_cost": 1000, "base_hours": 4}}
    ],
    "work_center_catalog": [
      {{"name": "Assembly Station", "line_name": "Assembly"}}
    ],
    "fallback_components": [
      {{"ComponentID": 1, "ComponentName": "Raw Material", "UOM": "KG"}}
    ],
    "fallback_plants": [
      {{"PlantID": 1, "PlantName": "Main Manufacturing Plant"}}
    ],
    "fallback_warehouses": [
      {{"WarehouseID": 1, "PlantID": 1, "WarehouseName": "Main Raw Material Warehouse"}}
    ],
    "bom_patterns": ["Finished products consume raw materials, components, and packaging."],
    "scrap_yield_profiles": {{"Assembly": [0.0, 3.0]}},
    "quality_defect_codes": ["DimensionalIssue", "FunctionalFailure", "PackagingDefect"],
    "rework_reason_codes": ["ReworkRequired", "Reinspect"],
    "cost_profiles": {{"LaborRatePerHour": [20.0, 70.0], "OverheadPct": [5.0, 20.0]}}
  }},
  "shared": {{
    "countable_uoms": ["EA", "Each", "Unit", "Piece", "PCS", "Pack", "Set"],
    "measurable_uoms": ["KG", "Gram", "Liter", "Meter", "Roll"],
    "default_currency": "USD",
    "date_scope_notes": ["Generated scenarios remain in calendar year 2025."],
    "realism_notes": ["Industry-specific catalog hints only; Python generates rows."]
  }},
  "sales": {{
    "customer_types": ["Distributor", "Retail Customer", "Institutional Customer"],
    "customer_industries": ["Distribution", "Retail", "Healthcare"],
    "customer_name_terms": ["Industry customer naming terms"],
    "sales_channels": ["DIRECT", "DISTRIBUTOR", "RETAIL"],
    "payment_terms": ["Net 30", "Net 45"],
    "regions": ["North", "South", "East", "West"],
    "carrier_names": ["Regional Logistics"],
    "payment_methods": ["BankTransfer", "Card"],
    "return_reasons": ["Quality Complaint", "Shipping Damage"],
    "price_margin_pct_range": [20.0, 45.0],
    "minimum_order_quantity_range": [1.0, 100.0],
    "fallback_price_range": [10.0, 100.0]
  }}
}}
""".strip()
