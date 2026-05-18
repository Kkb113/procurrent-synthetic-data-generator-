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
        plan = LLMGenerationPlan.model_validate(_normalize_live_plan_shape(raw_plan))
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


def _normalize_live_plan_shape(raw_plan: Any) -> Any:
    """Accept common live-LLM aliases while preserving the strict plan contract.

    Prompted models occasionally return table-local date rules and multi-column
    validation rules. Python still validates the final contract; this adapter
    only maps those aliases into the existing strict fields.
    """

    if not isinstance(raw_plan, dict):
        return raw_plan
    normalized = dict(raw_plan)
    normalized["formula_rules"] = [
        rule
        for rule in (_normalize_formula_rule(rule) for rule in normalized.get("formula_rules", []))
        if rule is not None
    ]
    normalized["date_rules"] = [
        rule
        for rule in (_normalize_date_rule(rule) for rule in normalized.get("date_rules", []))
        if rule is not None
    ]
    normalized["quantity_rules"] = [
        rule
        for rule in (_normalize_quantity_rule(rule) for rule in normalized.get("quantity_rules", []))
        if rule is not None
    ]
    normalized["status_rules"] = [
        rule
        for rule in (_normalize_status_rule(rule) for rule in normalized.get("status_rules", []))
        if rule is not None
    ]
    normalized["validation_rules"] = [
        _normalize_validation_rule(rule)
        for rule in normalized.get("validation_rules", [])
    ]
    return normalized


def _normalize_date_rule(rule: Any) -> Any:
    if not isinstance(rule, dict):
        return rule
    if {"earlier_table", "earlier_column", "later_table", "later_column"}.issubset(rule):
        return rule
    table_name = rule.get("table_name") or rule.get("target_table")
    date_columns = rule.get("date_columns")
    if table_name and rule.get("column_name") and rule.get("related_table") and rule.get("related_column"):
        if not _looks_like_date_column(str(rule.get("column_name"))) or not _looks_like_date_column(str(rule.get("related_column"))):
            return None
        return {
            "rule_id": rule.get("rule_id") or f"{rule.get('related_table')}_{rule.get('related_column')}_before_{table_name}_{rule.get('column_name')}",
            "earlier_table": rule.get("related_table"),
            "earlier_column": rule.get("related_column"),
            "later_table": table_name,
            "later_column": rule.get("column_name"),
            "min_offset_days": rule.get("min_offset_days") or rule.get("offset_days"),
            "max_offset_days": rule.get("max_offset_days"),
            "description": rule.get("description"),
        }
    if not table_name or not isinstance(date_columns, list) or not date_columns:
        start_column = rule.get("start_column")
        end_column = rule.get("end_column")
        if table_name and start_column and end_column:
            if not _looks_like_date_column(str(start_column)) or not _looks_like_date_column(str(end_column)):
                return None
            return {
                "rule_id": rule.get("rule_id") or f"{table_name}_{start_column}_before_{end_column}",
                "earlier_table": table_name,
                "earlier_column": start_column,
                "later_table": table_name,
                "later_column": end_column,
                "min_offset_days": rule.get("min_offset_days"),
                "max_offset_days": rule.get("max_offset_days"),
                "description": rule.get("description"),
            }
        return rule
    date_columns = [column for column in date_columns if _looks_like_date_column(str(column))]
    if not date_columns:
        return None
    earlier_column = date_columns[0]
    later_column = date_columns[1] if len(date_columns) > 1 else date_columns[0]
    return {
        "rule_id": rule.get("rule_id") or f"{table_name}_{earlier_column}_before_{later_column}",
        "earlier_table": table_name,
        "earlier_column": earlier_column,
        "later_table": table_name,
        "later_column": later_column,
        "min_offset_days": rule.get("min_offset_days"),
        "max_offset_days": rule.get("max_offset_days"),
        "description": rule.get("description"),
    }


def _looks_like_date_column(column_name: str) -> bool:
    normalized = column_name.lower()
    return "date" in normalized or "time" in normalized


def _normalize_formula_rule(rule: Any) -> Any:
    if not isinstance(rule, dict):
        return rule
    if rule.get("rule_type") == "inventory_balance" and rule.get("operation") != "sum":
        return None
    if (
        rule.get("rule_type") == "row_level"
        and rule.get("target_table") == "Inventory"
        and rule.get("target_column") == "AvailableValue"
        and len(rule.get("input_columns") or []) < 2
    ):
        return None
    return rule


def _normalize_validation_rule(rule: Any) -> Any:
    if not isinstance(rule, dict):
        return rule
    normalized = {
        "rule_id": rule.get("rule_id"),
        "rule_type": rule.get("rule_type"),
        "table_name": rule.get("table_name"),
        "column_name": rule.get("column_name"),
        "condition": rule.get("condition"),
        "severity": rule.get("severity"),
        "description": rule.get("description"),
    }
    column_names = rule.get("column_names")
    if column_names is None:
        column_names = rule.get("columns")
    if (
        normalized["column_name"] is None
        and isinstance(column_names, list)
        and len(column_names) == 1
        and str(rule.get("severity", "error")).lower() == "error"
    ):
        normalized["column_name"] = column_names[0]
    if not normalized["condition"]:
        pieces = [
            str(value)
            for value in (
                rule.get("description"),
                rule.get("condition"),
                rule.get("table_name"),
                ", ".join(str(column_name) for column_name in column_names) if isinstance(column_names, list) else None,
            )
            if value
        ]
        normalized["condition"] = " ".join(pieces) or f"{normalized.get('rule_id') or 'validation rule'} must pass"
    return {key: value for key, value in normalized.items() if value is not None}


def _normalize_quantity_rule(rule: Any) -> Any:
    if not isinstance(rule, dict):
        return rule
    if {"left_table", "left_column", "right_table", "right_column"}.issubset(rule):
        return rule
    table_name = rule.get("table_name")
    column_name = rule.get("column_name")
    value = rule.get("value")
    if not table_name or not column_name or not isinstance(value, str) or "." not in value:
        return None
    right_table, right_column = value.split(".", maxsplit=1)
    if not _is_identifier(right_table.strip()) or not _is_identifier(right_column.strip()):
        return None
    return {
        "rule_id": rule.get("rule_id") or f"{table_name}_{column_name}_{right_table}_{right_column}",
        "left_table": table_name,
        "left_column": column_name,
        "operator": rule.get("operator") or "=",
        "right_table": right_table.strip(),
        "right_column": right_column.strip(),
        "description": rule.get("description"),
    }


def _is_identifier(value: str) -> bool:
    return bool(value) and (value[0].isalpha() or value[0] == "_") and all(character.isalnum() or character == "_" for character in value)


def _normalize_status_rule(rule: Any) -> Any:
    if not isinstance(rule, dict):
        return rule
    if {"status_column", "status_values", "derivation_logic"}.issubset(rule):
        if _looks_like_non_status_flag_column(rule.get("status_column"), rule.get("status_values")):
            return None
        return rule
    status_column = rule.get("status_column") or rule.get("column_name")
    status_values = rule.get("status_values") or rule.get("allowed_values") or []
    if _looks_like_non_status_flag_column(status_column, status_values):
        return None
    return {
        "rule_id": rule.get("rule_id"),
        "table_name": rule.get("table_name") or rule.get("target_table"),
        "status_column": status_column,
        "status_values": status_values,
        "derivation_logic": rule.get("derivation_logic") or rule.get("derivation") or rule.get("strategy") or rule.get("description") or "Derive from lifecycle facts.",
        "description": rule.get("description"),
    }


def _looks_like_non_status_flag_column(column_name: Any, values: Any) -> bool:
    normalized_name = str(column_name or "").strip().lower()
    if not normalized_name.endswith("flag"):
        return False
    if isinstance(values, str) or values is None or not hasattr(values, "__iter__"):
        return True
    normalized_values = {str(value).strip().lower() for value in values if str(value).strip()}
    return not normalized_values or normalized_values.issubset({"0", "1", "true", "false", "yes", "no"})


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
