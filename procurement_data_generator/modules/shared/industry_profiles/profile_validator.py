"""Validation helpers for shared industry profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class IndustryProfileValidationResult:
    """Lightweight validation result for industry profiles."""

    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_industry_profile(profile: Any) -> IndustryProfileValidationResult:
    """Validate required industry profile shape and minimum useful content."""

    data = _as_mapping(profile)
    errors: list[str] = []
    warnings: list[str] = []

    for field_name in ("industry_id", "industry_name", "procurement", "production", "shared"):
        if field_name not in data:
            errors.append(f"Missing required top-level field: {field_name}.")

    industry_id = str(data.get("industry_id", "")).strip()
    if not industry_id:
        errors.append("industry_id must be non-empty.")

    procurement = _as_mapping(data.get("procurement", {}))
    production = _as_mapping(data.get("production", {}))
    shared = _as_mapping(data.get("shared", {}))

    _require_non_empty_list(procurement, "procurement", "component_categories", errors)
    _require_non_empty_list(procurement, "procurement", "component_name_patterns", errors)
    _require_non_empty_list(procurement, "procurement", "supplier_name_patterns", errors)

    _require_non_empty_list(production, "production", "product_categories", errors)
    _require_non_empty_list(production, "production", "product_name_patterns", errors)
    _require_non_empty_list(production, "production", "work_center_names", errors)
    _require_non_empty_list(production, "production", "routing_operation_names", errors)
    _require_non_empty_list(production, "production", "quality_defect_codes", errors)

    countable_uoms = _require_non_empty_list(shared, "shared", "countable_uoms", errors)
    measurable_uoms = _require_non_empty_list(shared, "shared", "measurable_uoms", errors)
    countable_set = {str(value).strip().lower() for value in countable_uoms if str(value).strip()}
    measurable_set = {str(value).strip().lower() for value in measurable_uoms if str(value).strip()}
    if countable_set and measurable_set and countable_set == measurable_set:
        errors.append("shared.countable_uoms and shared.measurable_uoms must not fully overlap.")
    elif countable_set & measurable_set:
        warnings.append("shared.countable_uoms and shared.measurable_uoms contain overlapping suggestions.")

    return IndustryProfileValidationResult(valid=not errors, errors=errors, warnings=warnings)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


def _require_non_empty_list(mapping: Mapping[str, Any], section: str, field_name: str, errors: list[str]) -> tuple[Any, ...]:
    value = mapping.get(field_name)
    if value is None:
        errors.append(f"Missing required field: {section}.{field_name}.")
        return ()
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        errors.append(f"{section}.{field_name} must be a non-empty list or tuple.")
        return ()
    values = tuple(item for item in value if str(item).strip())
    if not values:
        errors.append(f"{section}.{field_name} must be non-empty.")
    return values
