"""Pydantic contract for the LLM generation plan JSON."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from procurement_data_generator.core.contracts.schema_contract import GenerationType


Confidence = Literal["high", "medium", "low"]
RowCountSource = Literal["metadata", "llm_adjusted", "derived_from_parent"]
FormulaRuleType = Literal[
    "row_level",
    "aggregate",
    "date_diff",
    "percentage",
    "quantity_reconciliation",
    "inventory_balance",
]
FormulaOperation = Literal[
    "add",
    "subtract",
    "multiply",
    "divide",
    "sum",
    "count",
    "avg",
    "min",
    "max",
    "date_diff",
    "percentage",
    "equals",
    "less_than_or_equal",
    "greater_than_or_equal",
]
ToleranceType = Literal["absolute", "percentage", "none"]
QuantityOperator = Literal["<=", ">=", "=", "<", ">"]
PlanValidationRuleType = Literal[
    "pk_check",
    "fk_check",
    "not_null",
    "unique_check",
    "date_order",
    "quantity_check",
    "formula_check",
    "reconciliation",
    "status_check",
]
RuleSeverity = Literal["error", "warning"]


class StrictPlanModel(BaseModel):
    """Base model that prevents unplanned fields in the LLM contract."""

    model_config = ConfigDict(extra="forbid")


class MaterialCategory(StrictPlanModel):
    """Domain-specific material category guidance."""

    category_name: str
    material_examples: list[str] = Field(default_factory=list)
    specification_patterns: list[str] = Field(default_factory=list)

    @field_validator("category_name")
    @classmethod
    def category_name_not_blank(cls, value: str) -> str:
        return _not_blank(value, "category_name")


class DomainProfile(StrictPlanModel):
    """Domain profile used later by deterministic generation engines."""

    industry: str
    business_context: str | None = None
    vendor_categories: list[str] = Field(default_factory=list)
    material_categories: list[MaterialCategory] = Field(default_factory=list)
    warehouse_types: list[str] = Field(default_factory=list)
    plant_locations: list[str] = Field(default_factory=list)
    carrier_name_patterns: list[str] = Field(default_factory=list)
    inspection_test_categories: list[str] = Field(default_factory=list)

    @field_validator("industry")
    @classmethod
    def industry_not_blank(cls, value: str) -> str:
        return _not_blank(value, "industry")


class TableRoleMapping(StrictPlanModel):
    """LLM's table-to-role interpretation."""

    table_name: str
    table_role: str
    area: str
    confidence: Confidence
    reasoning: str | None = None

    @field_validator("table_name", "table_role", "area")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")


class RowCountPlan(StrictPlanModel):
    """Planned row count for a table."""

    table_name: str
    target_rows: int = Field(gt=0)
    source: RowCountSource
    reasoning: str | None = None

    @field_validator("table_name")
    @classmethod
    def table_name_not_blank(cls, value: str) -> str:
        return _not_blank(value, "table_name")


PlanScalar = str | int | float | None


class ColumnGenerationRule(StrictPlanModel):
    """Column-level generation strategy proposed by the LLM."""

    table_name: str
    column_name: str
    generation_type: GenerationType
    strategy: str
    allowed_values: list[str] = Field(default_factory=list)
    min_value: PlanScalar = None
    max_value: PlanScalar = None
    nullable_strategy: str | None = None
    depends_on_columns: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("table_name", "column_name", "strategy")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")


class FormulaRule(StrictPlanModel):
    """Formula structure only; formulas are not executed in Phase 4."""

    rule_id: str
    rule_type: FormulaRuleType
    target_table: str
    target_column: str
    operation: FormulaOperation
    input_columns: list[str] = Field(default_factory=list)
    source_table: str | None = None
    source_column: str | None = None
    relationship_key: str | None = None
    group_by_columns: list[str] = Field(default_factory=list)
    formula: str
    denominator_column: str | None = None
    denominator_guard: bool = False
    tolerance_type: ToleranceType | None = None
    tolerance_value: float | None = None
    description: str | None = None

    @field_validator("rule_id", "target_table", "target_column", "formula")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")


class DateRule(StrictPlanModel):
    """Lifecycle ordering rule between two date columns."""

    rule_id: str
    earlier_table: str
    earlier_column: str
    later_table: str
    later_column: str
    min_offset_days: int | None = None
    max_offset_days: int | None = None
    description: str | None = None

    @field_validator("rule_id", "earlier_table", "earlier_column", "later_table", "later_column")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")


class QuantityRule(StrictPlanModel):
    """Lifecycle quantity comparison rule."""

    rule_id: str
    left_table: str
    left_column: str
    operator: QuantityOperator
    right_table: str
    right_column: str
    description: str | None = None

    @field_validator("rule_id", "left_table", "left_column", "right_table", "right_column")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")


class StatusRule(StrictPlanModel):
    """Status derivation guidance; random assignment is not allowed later."""

    rule_id: str
    table_name: str
    status_column: str
    status_values: list[str]
    derivation_logic: str
    description: str | None = None

    @field_validator("rule_id", "table_name", "status_column", "derivation_logic")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")

    @field_validator("status_values")
    @classmethod
    def status_values_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("status_values must contain at least one status.")
        return value


class PlanValidationRule(StrictPlanModel):
    """Validation rule proposed by the LLM for later plan/data checks."""

    rule_id: str
    rule_type: PlanValidationRuleType
    table_name: str | None = None
    column_name: str | None = None
    condition: str
    severity: RuleSeverity
    description: str | None = None

    @field_validator("rule_id", "condition")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _not_blank(value, "required string")


class LLMGenerationPlan(StrictPlanModel):
    """Top-level JSON contract returned by the LLM planning step."""

    module: str
    business_summary: str
    domain_profile: DomainProfile
    table_role_mapping: list[TableRoleMapping] = Field(default_factory=list)
    generation_order: list[str]
    row_count_plan: list[RowCountPlan] = Field(default_factory=list)
    column_generation_rules: list[ColumnGenerationRule] = Field(default_factory=list)
    formula_rules: list[FormulaRule] = Field(default_factory=list)
    date_rules: list[DateRule] = Field(default_factory=list)
    quantity_rules: list[QuantityRule] = Field(default_factory=list)
    status_rules: list[StatusRule] = Field(default_factory=list)
    validation_rules: list[PlanValidationRule] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("module")
    @classmethod
    def module_must_be_supported(cls, value: str) -> str:
        if value not in {"procurement", "production"}:
            raise ValueError("module must be 'procurement' or 'production'.")
        return value

    @field_validator("business_summary")
    @classmethod
    def business_summary_not_blank(cls, value: str) -> str:
        return _not_blank(value, "business_summary")

    @field_validator("generation_order")
    @classmethod
    def generation_order_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("generation_order must contain at least one table.")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("generation_order must contain non-blank table names.")
        return value

    @model_validator(mode="after")
    def assumptions_and_warnings_are_lists(self) -> "LLMGenerationPlan":
        # Pydantic already enforces list shape. This keeps the contract intent visible.
        return self


def _not_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank.")
    return value
