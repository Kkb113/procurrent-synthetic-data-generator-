"""Safe normalization for Azure-generated LLM plans."""

from __future__ import annotations

from dataclasses import dataclass

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
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
