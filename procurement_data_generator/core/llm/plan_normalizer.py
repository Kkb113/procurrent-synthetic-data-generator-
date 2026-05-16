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
    removed_dependency: str
    message: str
    suggested_fix: str

    def to_dict(self) -> dict[str, str]:
        return {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "removed_dependency": self.removed_dependency,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
        }


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
    """Remove invalid same-table dependencies from ColumnGenerationRule entries.

    Only column_generation_rules.depends_on_columns is normalized. Unknown tables,
    formula rules, date rules, quantity rules, status rules, and validation rules
    are left untouched for Phase 6 semantic validation.
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
                        removed_dependency=dependency,
                        message=(
                            f"Removed invalid depends_on_columns reference {dependency!r} from "
                            f"{table_name}.{column_name}; dependencies must exist in the same table."
                        ),
                        suggested_fix=(
                            "Put cross-table lifecycle dependencies in date_rules, quantity_rules, "
                            "formula_rules, or validation_rules."
                        ),
                    )
                )

        rule["depends_on_columns"] = kept_dependencies

    return PlanNormalizationResult(plan=LLMGenerationPlan.model_validate(plan_data), warnings=warnings)


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
