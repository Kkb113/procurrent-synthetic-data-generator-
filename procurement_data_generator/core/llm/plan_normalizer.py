"""Safe normalization for Azure-generated LLM plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan, NormalizedLLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract


@dataclass(frozen=True)
class PlanNormalizationWarning:
    """One harmless plan cleanup warning."""

    table_name: str
    column_name: str
    message: str
    suggested_fix: str
    removed_dependency: str | None = None
    removed_rule_id: str | None = None
    normalization_type: str = "depends_on_columns"

    def to_dict(self) -> dict[str, str]:
        payload = {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "normalization_type": self.normalization_type,
        }
        if self.removed_dependency is not None:
            payload["removed_dependency"] = self.removed_dependency
        if self.removed_rule_id is not None:
            payload["removed_rule_id"] = self.removed_rule_id
        return payload


@dataclass(frozen=True)
class PlanNormalizationResult:
    """Result of normalizing a generated plan."""

    plan: LLMGenerationPlan
    warnings: list[PlanNormalizationWarning]

    @property
    def changed(self) -> bool:
        return bool(self.warnings)


def normalize_column_generation_dependencies(
    plan: LLMGenerationPlan,
    schema: SchemaContract,
) -> PlanNormalizationResult:
    """Remove harmless live-LLM aliases before semantic validation.

    The semantic validator remains strict for executable rules. This normalizer
    only removes known non-executable Azure aliases:
    - cross-table ``depends_on_columns`` entries,
    - aggregate date formulas over date columns,
    - date rules that attach cross-table lifecycle dates to the wrong table.
    """

    plan_data = plan.model_dump(mode="json")
    table_columns = {
        table_name: {column.column_name for column in table.columns}
        for table_name, table in schema.tables.items()
    }
    warnings: list[PlanNormalizationWarning] = []

    for rule in plan_data.get("column_generation_rules", []):
        table_name = rule.get("table_name", "")
        column_name = rule.get("column_name", "")
        valid_columns = table_columns.get(table_name, set())
        original_dependencies = list(rule.get("depends_on_columns") or [])
        kept_dependencies = []

        for dependency in original_dependencies:
            if dependency in valid_columns:
                kept_dependencies.append(dependency)
            else:
                warnings.append(
                    PlanNormalizationWarning(
                        table_name=table_name,
                        column_name=column_name,
                        message=(
                            f"Removed invalid depends_on_columns reference {dependency!r} from "
                            f"{table_name}.{column_name}; dependencies must exist in the same table."
                        ),
                        suggested_fix=(
                            "Put cross-table lifecycle dependencies in date_rules, quantity_rules, "
                            "formula_rules, or validation_rules."
                        ),
                        removed_dependency=dependency,
                    )
                )

        rule["depends_on_columns"] = kept_dependencies

    plan_data["formula_rules"] = _normalize_formula_rules(plan_data.get("formula_rules", []), schema, warnings)
    plan_data["date_rules"] = _normalize_date_rules(plan_data.get("date_rules", []), schema, warnings)

    return PlanNormalizationResult(plan=LLMGenerationPlan.model_validate(plan_data), warnings=warnings)


def _normalize_formula_rules(
    rules: list[dict[str, Any]],
    schema: SchemaContract,
    warnings: list[PlanNormalizationWarning],
) -> list[dict[str, Any]]:
    kept_rules: list[dict[str, Any]] = []
    for rule in rules:
        if _is_date_aggregate_formula_alias(rule, schema):
            warnings.append(
                PlanNormalizationWarning(
                    table_name=str(rule.get("target_table") or ""),
                    column_name=str(rule.get("target_column") or ""),
                    message=(
                        f"Removed date aggregate FormulaRule {rule.get('rule_id')!r}; "
                        "date rollups are deterministic generator guidance, not numeric formula rules."
                    ),
                    suggested_fix="Keep date rollup guidance in validation_rules or assumptions, not formula_rules.",
                    removed_rule_id=str(rule.get("rule_id") or ""),
                    normalization_type="formula_rules",
                )
            )
            continue
        kept_rules.append(rule)
    return kept_rules


def _is_date_aggregate_formula_alias(rule: dict[str, Any], schema: SchemaContract) -> bool:
    if rule.get("rule_type") != "aggregate" or rule.get("operation") not in {"min", "max"}:
        return False
    target_column = _get_column(schema, rule.get("target_table"), rule.get("target_column"))
    source_column = _get_column(schema, rule.get("source_table"), rule.get("source_column"))
    return _is_date_column(target_column) or _is_date_column(source_column)


def _normalize_date_rules(
    rules: list[dict[str, Any]],
    schema: SchemaContract,
    warnings: list[PlanNormalizationWarning],
) -> list[dict[str, Any]]:
    kept_rules: list[dict[str, Any]] = []
    for rule in rules:
        if _has_cross_table_date_alias(rule, schema):
            warnings.append(
                PlanNormalizationWarning(
                    table_name=str(rule.get("later_table") or rule.get("earlier_table") or ""),
                    column_name=str(rule.get("later_column") or rule.get("earlier_column") or ""),
                    message=(
                        f"Removed DateRule {rule.get('rule_id')!r}; it references a date column "
                        "on the wrong table and is treated as lifecycle guidance only."
                    ),
                    suggested_fix=(
                        "Use earlier_table/earlier_column and later_table/later_column with concrete "
                        "metadata columns, or keep broad lifecycle guidance in validation_rules."
                    ),
                    removed_rule_id=str(rule.get("rule_id") or ""),
                    normalization_type="date_rules",
                )
            )
            continue
        kept_rules.append(rule)
    return kept_rules


def _has_cross_table_date_alias(rule: dict[str, Any], schema: SchemaContract) -> bool:
    checks = (
        (rule.get("earlier_table"), rule.get("earlier_column")),
        (rule.get("later_table"), rule.get("later_column")),
    )
    for table_name, column_name in checks:
        if not table_name or not column_name:
            continue
        if _get_column(schema, table_name, column_name) is not None:
            continue
        if _column_exists_anywhere(schema, str(column_name)):
            return True
    return False


def _get_column(schema: SchemaContract, table_name: Any, column_name: Any):
    if not isinstance(table_name, str) or not isinstance(column_name, str):
        return None
    table = schema.tables.get(table_name)
    if table is None:
        return None
    return next((column for column in table.columns if column.column_name == column_name), None)


def _column_exists_anywhere(schema: SchemaContract, column_name: str) -> bool:
    return any(column.column_name == column_name for table in schema.tables.values() for column in table.columns)


def _is_date_column(column: Any) -> bool:
    if column is None:
        return False
    data_type = str(column.data_type).strip().lower()
    return any(data_type.startswith(type_name) for type_name in ("date", "datetime", "smalldatetime", "timestamp"))


def normalize_llm_generation_plan(plan_or_data: LLMGenerationPlan | NormalizedLLMGenerationPlan | dict[str, Any]) -> NormalizedLLMGenerationPlan:
    """Return the normalized multi-module plan envelope.

    Legacy single-module plans remain valid and are wrapped under
    ``modules[module_id]["legacy_plan"]``. Normalized envelopes pass through
    validation and get missing module payloads filled with empty dictionaries.
    """

    if isinstance(plan_or_data, NormalizedLLMGenerationPlan):
        return NormalizedLLMGenerationPlan.model_validate(plan_or_data.model_dump(mode="json"))

    if isinstance(plan_or_data, LLMGenerationPlan):
        return _normalize_legacy_plan(plan_or_data)

    if not isinstance(plan_or_data, dict):
        raise TypeError("plan_or_data must be an LLMGenerationPlan, NormalizedLLMGenerationPlan, or dict.")

    if _looks_like_normalized_plan(plan_or_data):
        return NormalizedLLMGenerationPlan.model_validate(plan_or_data)

    legacy_data = dict(plan_or_data)
    legacy_model_version = legacy_data.pop("model_version", None)
    legacy_plan = LLMGenerationPlan.model_validate(legacy_data)
    return _normalize_legacy_plan(legacy_plan, module_version=legacy_model_version)


def get_legacy_module_plan(
    normalized_plan: NormalizedLLMGenerationPlan,
    module_id: str,
) -> LLMGenerationPlan | None:
    """Return a legacy module plan payload from a normalized envelope when present."""

    payload = normalized_plan.modules.get(module_id.strip().lower(), {})
    legacy_plan = payload.get("legacy_plan")
    if legacy_plan is None:
        return None
    return LLMGenerationPlan.model_validate(legacy_plan)


def _looks_like_normalized_plan(data: dict[str, Any]) -> bool:
    return "module_set" in data or "modules" in data


def _normalize_legacy_plan(plan: LLMGenerationPlan, module_version: str | None = None) -> NormalizedLLMGenerationPlan:
    module_id = plan.module.strip().lower()
    legacy_payload = plan.model_dump(mode="json")
    inferred_module_version = module_version or _default_module_version(module_id)
    return NormalizedLLMGenerationPlan(
        plan_id=None,
        plan_version="1.0",
        industry=plan.domain_profile.industry,
        module_set=[module_id],
        module_versions={module_id: inferred_module_version} if inferred_module_version else {},
        operating_scope=None,
        industry_profile=plan.domain_profile.model_dump(mode="json"),
        modules={module_id: {"legacy_plan": legacy_payload}},
        global_assumptions=list(plan.assumptions),
        validation_rules=[rule.model_dump(mode="json") for rule in plan.validation_rules],
    )


def _default_module_version(module_id: str) -> str | None:
    if module_id == "procurement":
        return "v2"
    if module_id == "production":
        return "v1"
    return None
