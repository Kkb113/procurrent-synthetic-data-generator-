"""Build LLM planning prompts from validated project contracts."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import get_args

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import (
    Confidence,
    FormulaOperation,
    FormulaRuleType,
    PlanValidationRuleType,
    QuantityOperator,
    RowCountSource,
    RuleSeverity,
)
from procurement_data_generator.core.contracts.schema_contract import Area, GenerationType, SchemaContract
from procurement_data_generator.core.modules.contracts import PromptSection
from procurement_data_generator.core.modules.registry import ModuleRegistry, create_default_module_registry


PROCUREMENT_V1_UNSUPPORTED_MESSAGE = "Procurement V1 is deprecated and no longer supported. Use Procurement V2."


def build_llm_planning_prompt(
    schema_contract: SchemaContract,
    relationships: list[RelationshipContract],
    business_scenario: str,
    role_catalog: dict | None = None,
    model_version: str = "v2",
    module_ids: Sequence[str] | None = None,
    module_registry: ModuleRegistry | None = None,
) -> str:
    """Build the planning prompt that will later be sent to an LLM.

    The default remains Procurement v2 for backward compatibility. New callers
    can pass module_ids to assemble a generic MES prompt with selected module
    sections.
    """

    if model_version == "v1":
        raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)

    registry = module_registry or create_default_module_registry()
    selected_module_ids = tuple(module_ids or _default_module_ids(model_version))
    plugins = tuple(registry.get(module_id) for module_id in selected_module_ids)
    scenario = business_scenario.strip()
    catalog = role_catalog or _combined_role_catalog(plugins)
    module_sections = [
        section
        for plugin in plugins
        for section in plugin.get_prompt_sections(
            schema=schema_contract,
            relationships=relationships,
            scenario=scenario,
        )
    ]

    sections = [
        _system_instruction_section(),
        _task_objective_section(selected_module_ids),
        _hard_rules_section(),
        _business_scenario_section(scenario),
        _metadata_summary_section(schema_contract),
        _erd_relationships_section(relationships),
        _selected_modules_section(plugins),
        _normalized_plan_guidance_section(),
        _supported_values_section(catalog),
        _module_prompt_sections(module_sections),
        _json_shape_section(selected_module_ids),
        _formula_guidance_section(),
        _date_rule_guidance_section(),
        _quantity_rule_guidance_section(),
        _status_rule_guidance_section(),
        _domain_profile_guidance_section(),
        _output_contract_section(),
    ]
    return "\n\n".join(section for section in sections if section.strip()).strip() + "\n"


def _default_module_ids(model_version: str) -> tuple[str, ...]:
    if model_version == "production_v1":
        return ("production",)
    return ("procurement",)


def _combined_role_catalog(plugins) -> dict:
    catalog = {}
    for plugin in plugins:
        catalog.update(plugin.get_role_catalog())
    return catalog


def _system_instruction_section() -> str:
    return "\n".join(
        [
            "A. System/Role Instruction",
            "You are an MES synthetic data planning assistant.",
            "Your job is to create a structured LLMGenerationPlan JSON contract for Python to validate and execute later.",
            "Core principle: LLM plans. Python validates. Python generates. Python calculates. Python reconciles. Python enforces business rules. Python writes output artifacts and optionally loads to SQL.",
            "The LLM creates a business generation plan only.",
        ]
    )


def _task_objective_section(module_ids: Sequence[str]) -> str:
    return "\n".join(
        [
            "B. Task Objective",
            "Produce one structured JSON planning object only.",
            f"Selected modules: {', '.join(module_ids)}",
            "The plan should describe module context, domain profile, table role mapping, generation order, row counts, column strategies, formula rules, date rules, quantity rules, status rules, validation rules, assumptions, and warnings.",
        ]
    )


def _hard_rules_section() -> str:
    return "\n".join(
        [
            "C. Generic MES Planning Hard Rules",
            "- Return JSON only.",
            "- Do not generate raw rows.",
            "- Do not generate actual table rows.",
            "- Do not generate CSV data.",
            "- Do not generate SQL inserts.",
            "- Do not generate Python code.",
            "- Do not generate markdown.",
            "- Do not invent table names.",
            "- Do not invent column names.",
            "- Use only the provided metadata tables and columns.",
            "- Respect supplied table metadata and ERD relationships.",
            "- Respect selected modules.",
            "- Respect the current simple operating scope unless explicitly supplied: one plant, one warehouse, one shift per day.",
            "- Use module-specific sections for lifecycle details.",
            "- Python owns primary key generation, foreign key consistency, formulas, reconciliation, inventory calculations, status derivation, date consistency, validation, deterministic generation, output artifacts, and optional SQL load.",
            "- Use only supported generation types.",
            "- Use only supported formula rule types.",
            "- Use only supported formula operations.",
            "- Formula rules must reference existing columns only.",
            "- Date rules must reference existing date columns only.",
            "- Quantity rules must reference existing quantity columns only.",
            "- Status rules must reference existing status columns only.",
            "- CRITICAL: For column_generation_rules.depends_on_columns, only include columns that exist in the SAME table as table_name. Do not include columns from parent/child tables. Cross-table dependencies belong in date_rules, quantity_rules, formula_rules, or validation_rules.",
            "- depends_on_columns is for same-table dependencies only.",
            "- Every value in depends_on_columns must be a column that exists in the same table_name.",
            "- Do not put parent-table or child-table columns inside depends_on_columns.",
            "- If a generated column depends on a parent table column, leave depends_on_columns empty and describe the dependency in date_rules or quantity_rules.",
            "- Before returning JSON, verify every depends_on_columns entry exists in that table's column list.",
            "- Row count plan should primarily respect TargetRows from metadata.",
            "- If the business scenario suggests row count changes, set source to llm_adjusted and explain reasoning.",
            "- Domain profile should help Python generate realistic and unique names.",
            "- Do not fix duplicate names by appending numeric suffixes.",
            "- Do not include raw formulas outside the supported FormulaRule structure.",
            "- Do not use unsafe operations.",
            "- Do not produce SQL.",
            "- Do not produce code.",
            "- Do not use markdown.",
            "- Do not include comments inside JSON.",
            "- Do not include explanations outside JSON.",
        ]
    )


def _business_scenario_section(business_scenario: str) -> str:
    return "\n".join(
        [
            "D. Business Scenario",
            business_scenario or "(No business scenario was provided.)",
        ]
    )


def _metadata_summary_section(schema_contract: SchemaContract) -> str:
    lines = ["E. Metadata Summary"]
    for table in schema_contract.ordered_tables:
        lines.extend(
            [
                f"TableName: {table.table_name}",
                f"ProcessOrder: {table.process_order}",
                f"Area: {table.area}",
                f"TableRole: {table.table_role}",
                f"TargetRows: {table.target_rows}",
                "Columns:",
            ]
        )
        for column in table.columns:
            lines.append(
                "  - "
                f"ColumnName={column.column_name}; "
                f"DataType={column.data_type}; "
                f"KeyType={column.key_type or ''}; "
                f"RelatedTable={column.related_table or ''}; "
                f"RelatedColumn={column.related_column or ''}; "
                f"Nullable={column.nullable}; "
                f"GenerationType={column.generation_type}; "
                f"AllowedValues={', '.join(column.allowed_values)}; "
                f"MinValue={_blank_if_none(column.min_value)}; "
                f"MaxValue={_blank_if_none(column.max_value)}; "
                f"Formula={column.formula or ''}"
            )
        lines.append("")
    return "\n".join(lines).strip()


def _erd_relationships_section(relationships: list[RelationshipContract]) -> str:
    lines = ["F. ERD Relationships"]
    if not relationships:
        lines.append("- No ERD relationships were parsed.")
        return "\n".join(lines)

    for relationship in relationships:
        lines.extend(
            [
                f"- Parent: {relationship.parent_table}",
                f"  Child: {relationship.child_table}",
                f"  Type: {relationship.relationship_type}",
                f"  MermaidSymbol: {relationship.mermaid_symbol}",
                f"  Label: {relationship.label or ''}",
            ]
        )
    return "\n".join(lines)


def _selected_modules_section(plugins) -> str:
    lines = ["G. Selected MES Modules"]
    for plugin in plugins:
        lines.append(f"- {plugin.module_id}: {plugin.module_name} {plugin.module_version}")
    return "\n".join(lines)


def _normalized_plan_guidance_section() -> str:
    return "\n".join(
        [
            "H. Normalized Plan Compatibility Guidance",
            "The platform supports a normalized multi-module MES plan envelope, but the current Procurement prompt remains legacy LLMGenerationPlan-compatible for backward compatibility.",
            "Future normalized envelopes can include module_set, module_versions, modules, operating_scope, industry_profile, global_assumptions, and validation_rules.",
            "For this prompt, return the legacy single-module LLMGenerationPlan JSON unless explicitly instructed otherwise by the caller.",
        ]
    )


def _supported_values_section(role_catalog: dict) -> str:
    return "\n".join(
        [
            "I. Supported Values",
            f"- Area: {', '.join(get_args(Area))}",
            f"- TableRole: {', '.join(role_catalog.keys())}",
            f"- GenerationType: {', '.join(get_args(GenerationType))}",
            f"- Formula rule_type: {', '.join(get_args(FormulaRuleType))}",
            f"- Formula operation: {', '.join(get_args(FormulaOperation))}",
            f"- Quantity operator: {', '.join(get_args(QuantityOperator))}",
            f"- Validation rule type: {', '.join(get_args(PlanValidationRuleType))}",
            f"- Severity: {', '.join(get_args(RuleSeverity))}",
            f"- Confidence: {', '.join(get_args(Confidence))}",
            f"- Row count source: {', '.join(get_args(RowCountSource))}",
        ]
    )


def _module_prompt_sections(sections: list[PromptSection]) -> str:
    lines = ["J. Module-Specific Planning Sections"]
    if not sections:
        lines.append("- No module-specific prompt sections were provided.")
        return "\n".join(lines)
    for section in sections:
        lines.extend([f"## {section.title}", f"Section ID: {section.section_id}", section.content])
    return "\n".join(lines)


def _json_shape_section(module_ids: Sequence[str]) -> str:
    module_value = module_ids[0] if len(module_ids) == 1 else "selected_module_id"
    skeleton = {
        "module": module_value,
        "business_summary": "string",
        "domain_profile": {
            "industry": "string",
            "business_context": "string or null",
            "vendor_categories": ["string"],
            "material_categories": [
                {
                    "category_name": "string",
                    "material_examples": ["string"],
                    "specification_patterns": ["string"],
                }
            ],
            "warehouse_types": ["string"],
            "plant_locations": ["string"],
            "carrier_name_patterns": ["string"],
            "inspection_test_categories": ["string"],
        },
        "table_role_mapping": [
            {
                "table_name": "existing metadata table name",
                "table_role": "supported module role",
                "area": "supported area",
                "confidence": "high|medium|low",
                "reasoning": "string or null",
            }
        ],
        "generation_order": ["existing metadata table name"],
        "row_count_plan": [
            {
                "table_name": "existing metadata table name",
                "target_rows": 1,
                "source": "metadata|llm_adjusted|derived_from_parent",
                "reasoning": "string or null",
            }
        ],
        "column_generation_rules": [
            {
                "table_name": "existing metadata table name",
                "column_name": "existing metadata column name",
                "generation_type": "supported generation type",
                "strategy": "string",
                "allowed_values": ["string"],
                "min_value": "string, number, or null",
                "max_value": "string, number, or null",
                "nullable_strategy": "string or null",
                "depends_on_columns": ["existing metadata column name"],
                "notes": "string or null",
            }
        ],
        "formula_rules": [
            {
                "rule_id": "non_blank_string",
                "rule_type": "supported formula rule_type",
                "target_table": "existing metadata table name",
                "target_column": "existing metadata column name",
                "operation": "supported formula operation",
                "input_columns": ["existing metadata column name"],
                "source_table": "existing metadata table name or null",
                "source_column": "existing metadata column name or null",
                "relationship_key": "existing key column or null",
                "group_by_columns": ["existing metadata column name"],
                "formula": "string",
                "denominator_column": "existing metadata column name or null",
                "denominator_guard": True,
                "tolerance_type": "absolute|percentage|none|null",
                "tolerance_value": 0.0,
                "description": "string or null",
            }
        ],
        "date_rules": [],
        "quantity_rules": [],
        "status_rules": [],
        "validation_rules": [],
        "assumptions": ["string"],
        "warnings": ["string"],
    }
    return "K. Required JSON Shape\n" + json.dumps(skeleton, indent=2)


def _formula_guidance_section() -> str:
    return "\n".join(
        [
            "L. Generic Formula Guidance",
            "Include formula rules only if the involved target and input columns exist in metadata.",
            "- PurchaseOrderLine.LineAmount = OrderedQuantity * UnitPrice",
            "- PurchaseOrderHeader.TotalAmount = SUM(PurchaseOrderLine.LineAmount) grouped by PurchaseOrderID",
            "- GoodsReceiptLine.ShortQuantity = ShippedQuantity - ReceivedQuantity",
            "- QualityInspectionLine.RejectedQuantity = InspectedQuantity - AcceptedQuantity",
            "- QualityInspectionLine.RejectionRatePct = RejectedQuantity / InspectedQuantity * 100 with denominator guard",
            "- InventoryTransaction.InventoryValue = TransactionQuantity * UnitPrice",
            "- Inventory.OnHandQuantity = SUM(InventoryTransaction.TransactionQuantity) grouped by ComponentID, PlantID, WarehouseID",
            "- Inventory.OnHandValue = SUM(InventoryTransaction.InventoryValue) grouped by ComponentID, PlantID, WarehouseID",
            "- Inventory.AvailableQuantity = OnHandQuantity - ReservedQuantity",
            "- Do not use relationship_key for multi-column inventory formulas.",
            "- relationship_key is only for single-key parent-child aggregations like PurchaseOrderID.",
            "Do not execute formulas. Only describe them using FormulaRule objects.",
        ]
    )


def _date_rule_guidance_section() -> str:
    return "\n".join(
        [
            "M. Generic Date Rule Guidance",
            "Create date rules only when those columns exist in metadata.",
            "- RequisitionDate <= OrderDate",
            "- OrderDate <= ShipmentDate",
            "- ShipmentDate <= ReceiptDate",
            "- ReceiptDate <= InspectionDate",
            "- InspectionDate <= InventoryPostingDate",
        ]
    )


def _quantity_rule_guidance_section() -> str:
    return "\n".join(
        [
            "N. Generic Quantity Rule Guidance",
            "Create quantity rules only when those columns exist in metadata.",
            "- ShippedQuantity <= OrderedQuantity",
            "- ReceivedQuantity <= ShippedQuantity",
            "- AcceptedQuantity + RejectedQuantity = InspectedQuantity",
            "- InventoryTransaction.Quantity = AcceptedQuantity",
        ]
    )


def _status_rule_guidance_section() -> str:
    return "\n".join(
        [
            "O. Generic Status Rule Guidance",
            "- Status values should be derived from lifecycle logic later.",
            "- Do not treat status as random if lifecycle context exists.",
            "- Use AllowedValues from metadata when present.",
        ]
    )


def _domain_profile_guidance_section() -> str:
    return "\n".join(
        [
            "P. Domain Profile Guidance",
            "- Use the business scenario to infer industry.",
            "- Produce supplier/vendor categories, material or component categories, material examples, specification patterns, warehouse types, plant locations, carrier patterns, and quality test categories when relevant to selected modules.",
            "- Material names must be industry-specific.",
            "- Vendor names must be supplier/manufacturer style.",
            "- Warehouse names should be location plus warehouse function.",
            "- No artificial numeric suffixes for duplicate names.",
            "- If not enough unique names can be generated later, Python should fail clearly.",
        ]
    )


def _output_contract_section() -> str:
    return "\n".join(
        [
            "Q. Output Contract",
            "Return only valid JSON matching the LLMGenerationPlan schema.",
            "Do not include markdown fences.",
            "Do not include explanations.",
        ]
    )


def _blank_if_none(value: object) -> str:
    return "" if value is None else str(value)
