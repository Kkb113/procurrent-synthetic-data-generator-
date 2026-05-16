"""Load and validate LLM generation plan JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.validation_report import ValidationReport


@dataclass(frozen=True)
class LLMPlanLoadResult:
    """Result of loading and validating an LLM generation plan."""

    plan: LLMGenerationPlan | None
    report: ValidationReport


def load_llm_plan_json(json_path: str | Path) -> LLMPlanLoadResult:
    """Load an LLM plan JSON file and validate it against the Phase 4 contract."""

    path = Path(json_path)
    report = ValidationReport()
    if not path.exists():
        report.add_error(
            message=f"LLM plan JSON file does not exist: {path}",
            suggested_fix="Provide a valid path to an LLM plan JSON file.",
        )
        return LLMPlanLoadResult(plan=None, report=report)

    try:
        raw_plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add_error(
            message=f"Invalid JSON: {exc.msg}.",
            suggested_fix="Fix the JSON syntax and try again.",
        )
        return LLMPlanLoadResult(plan=None, report=report)

    return validate_llm_plan_data(raw_plan)


def validate_llm_plan_data(raw_plan: Any) -> LLMPlanLoadResult:
    """Validate already-loaded JSON-like data against the LLM plan contract."""

    report = ValidationReport()
    try:
        plan = LLMGenerationPlan.model_validate(raw_plan)
    except ValidationError as exc:
        for error in exc.errors():
            field_path = _format_location(error.get("loc", ()))
            report.add_error(
                table_name=f"Field: {field_path}" if field_path else None,
                message=_format_error_message(error),
                suggested_fix=_suggest_fix(field_path),
            )
        return LLMPlanLoadResult(plan=None, report=report)

    return LLMPlanLoadResult(plan=plan, report=report)


def format_llm_plan_validation_result(result: LLMPlanLoadResult) -> str:
    """Format LLM plan validation output for CLI usage."""

    report = result.report
    plan = result.plan
    lines = ["LLM plan JSON validation completed."]
    if plan is not None:
        lines.extend(
            [
                f"Module: {plan.module}",
                f"Generation order tables: {len(plan.generation_order)}",
                f"Row count plan entries: {len(plan.row_count_plan)}",
                f"Column generation rules: {len(plan.column_generation_rules)}",
                f"Formula rules: {len(plan.formula_rules)}",
                f"Date rules: {len(plan.date_rules)}",
                f"Quantity rules: {len(plan.quantity_rules)}",
                f"Status rules: {len(plan.status_rules)}",
                f"Validation rules: {len(plan.validation_rules)}",
            ]
        )
    lines.append(f"Errors: {len(report.errors)}")
    lines.append(f"Validation status: {'passed' if report.is_valid else 'failed'}")

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors, start=1):
            lines.append(f"{index}. {issue.table_name or 'Field: N/A'}")
            lines.append(f"   Message: {issue.message}")
            lines.append(f"   Suggested fix: {issue.suggested_fix}")

    return "\n".join(lines)


def _format_location(location: tuple[Any, ...]) -> str:
    path = ""
    for item in location:
        if isinstance(item, int):
            path += f"[{item}]"
        else:
            path += f".{item}" if path else str(item)
    return path


def _format_error_message(error: dict[str, Any]) -> str:
    message = str(error.get("msg", "Invalid value."))
    context = error.get("ctx") or {}
    expected = context.get("expected")
    input_value = error.get("input")

    if error.get("type") == "literal_error" and expected is not None:
        return f"Unsupported value {input_value!r}. Expected one of: {expected}."
    return message


def _suggest_fix(field_path: str) -> str:
    if "operation" in field_path:
        return "Use one of the supported operation values."
    if "generation_type" in field_path:
        return "Use one of the supported generation_type values."
    if "rule_type" in field_path:
        return "Use one of the supported rule_type values."
    if "confidence" in field_path:
        return "Use confidence value high, medium, or low."
    if "target_rows" in field_path:
        return "Set target_rows to a number greater than 0."
    if "severity" in field_path:
        return "Use severity value error or warning."
    if "generation_order" in field_path:
        return "Provide a non-empty generation_order list of table names."
    if "module" in field_path:
        return "Set module to procurement or production."
    return "Update the JSON value to match the LLM generation plan schema."
