"""Prompt builder for small industry scenario planning."""

from __future__ import annotations

import json

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.schema_contract import SchemaContract


def build_industry_scenario_prompt(
    schema: SchemaContract,
    relationships: list[RelationshipContract],
    business_scenario: str,
    supported_domains: tuple[str, ...] = ("procurement", "production", "sales"),
) -> str:
    """Build a compact prompt for `IndustryScenarioPlan` JSON only."""

    skeleton = {
        "industry_id": "short_stable_snake_case_id",
        "industry_name": "Human readable industry name",
        "business_summary": "Short interpretation of the user's business scenario",
        "supported_domains": list(supported_domains),
        "row_volume_intent": "small|standard|analytics",
        "procurement": {
            "supplier_types": ["string"],
            "component_categories": ["string"],
            "raw_material_terms": ["string"],
            "purchasing_patterns": ["string"],
            "supplier_risk_factors": ["string"],
            "inspection_or_quality_hints": ["string"],
        },
        "production": {
            "product_families": ["string"],
            "production_process_terms": ["string"],
            "work_center_terms": ["string"],
            "routing_patterns": ["string"],
            "scrap_or_yield_hints": ["string"],
            "finished_good_terms": ["string"],
        },
        "sales": {
            "customer_types": ["string"],
            "customer_industries": ["string"],
            "sales_channels": ["string"],
            "demand_patterns": ["string"],
            "payment_terms": ["string"],
            "return_reasons": ["string"],
            "region_terms": ["string"],
        },
        "shared": {
            "geography_terms": ["string"],
            "currency": "ISO currency code",
            "seasonality": ["string"],
            "naming_style": "string",
            "regulatory_or_quality_terms": ["string"],
        },
        "assumptions": ["string"],
        "warnings": ["string"],
    }
    sections = [
        "You are an MES industry scenario planning assistant.",
        "Return JSON only. Do not include markdown, code fences, comments, or explanations outside JSON.",
        "You are not generating data rows.",
        "You are not generating an executable plan.",
        "You are not generating formulas.",
        "You are not generating validation rules.",
        "You are not generating SQL.",
        "You are only interpreting the business scenario and producing industry-specific planning hints.",
        "The result must support Procurement, Production, and Sales.",
        "Use metadata and ERD only as context. Do not reproduce table names or column names as required output fields.",
        "Do not invent table names or column names.",
        "",
        "Business scenario:",
        business_scenario.strip() or "(No scenario provided.)",
        "",
        "High-level metadata summary:",
        _metadata_summary(schema),
        "",
        "ERD summary:",
        _erd_summary(relationships),
        "",
        "Required JSON shape:",
        json.dumps(skeleton, indent=2),
    ]
    return "\n".join(sections).strip() + "\n"


def _metadata_summary(schema: SchemaContract) -> str:
    by_area: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for table in schema.ordered_tables:
        by_area[table.area] = by_area.get(table.area, 0) + 1
        by_role[table.table_role] = by_role.get(table.table_role, 0) + 1
    summary = {
        "table_count": len(schema.tables),
        "total_columns": sum(len(table.columns) for table in schema.tables.values()),
        "areas": by_area,
        "table_roles": sorted(by_role),
        "target_rows_total": sum(table.target_rows for table in schema.tables.values()),
    }
    return json.dumps(summary, indent=2)


def _erd_summary(relationships: list[RelationshipContract]) -> str:
    if not relationships:
        return json.dumps({"relationship_count": 0, "relationships": []}, indent=2)
    payload = {
        "relationship_count": len(relationships),
        "relationships": [
            {
                "parent_area": relationship.parent_table,
                "child_area": relationship.child_table,
                "type": relationship.relationship_type,
            }
            for relationship in relationships[:50]
        ],
    }
    return json.dumps(payload, indent=2)
