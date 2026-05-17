"""Explicit operating scope for current MES synthetic data generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class OperatingScope:
    """Current supported operating scope.

    The defaults intentionally preserve today's simplified demo setup: one
    plant, one warehouse, Shift A only, and calendar year 2025.
    """

    plant_count: int = 1
    warehouse_count: int = 1
    shift_codes: tuple[str, ...] = ("A",)
    default_shift_code: str = "A"
    calendar_year: int = 2025
    allow_cross_year: bool = False

    def __post_init__(self) -> None:
        _validate_positive_int(self.plant_count, "plant_count")
        _validate_positive_int(self.warehouse_count, "warehouse_count")
        _validate_positive_int(self.calendar_year, "calendar_year")
        if not isinstance(self.allow_cross_year, bool):
            raise ValueError("allow_cross_year must be a boolean.")
        normalized_shift_codes = tuple(str(shift_code).strip() for shift_code in self.shift_codes)
        if not normalized_shift_codes:
            raise ValueError("shift_codes must contain at least one shift code.")
        if any(not shift_code for shift_code in normalized_shift_codes):
            raise ValueError("shift_codes must not contain blank values.")
        default_shift_code = str(self.default_shift_code).strip()
        if not default_shift_code:
            raise ValueError("default_shift_code must not be blank.")
        if default_shift_code not in normalized_shift_codes:
            raise ValueError("default_shift_code must be present in shift_codes.")

        object.__setattr__(self, "shift_codes", normalized_shift_codes)
        object.__setattr__(self, "default_shift_code", default_shift_code)

    @property
    def date_start(self) -> date:
        return date(self.calendar_year, 1, 1)

    @property
    def date_end(self) -> date:
        return date(self.calendar_year, 12, 31)

    def is_allowed_shift_code(self, shift_code: str) -> bool:
        return str(shift_code).strip() in self.shift_codes


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer.")


DEFAULT_OPERATING_SCOPE = OperatingScope()

PLANT_COUNT = DEFAULT_OPERATING_SCOPE.plant_count
WAREHOUSE_COUNT = DEFAULT_OPERATING_SCOPE.warehouse_count
ALLOWED_SHIFT_CODES = DEFAULT_OPERATING_SCOPE.shift_codes
DEFAULT_SHIFT_CODE = DEFAULT_OPERATING_SCOPE.default_shift_code
CALENDAR_YEAR = DEFAULT_OPERATING_SCOPE.calendar_year


def default_operating_scope() -> OperatingScope:
    return DEFAULT_OPERATING_SCOPE


def is_allowed_shift_code(shift_code: str, scope: OperatingScope | None = None) -> bool:
    return (scope or DEFAULT_OPERATING_SCOPE).is_allowed_shift_code(shift_code)


def get_allowed_shift_codes(scope: OperatingScope | None = None) -> tuple[str, ...]:
    return (scope or DEFAULT_OPERATING_SCOPE).shift_codes


def get_default_shift_code(scope: OperatingScope | None = None) -> str:
    return (scope or DEFAULT_OPERATING_SCOPE).default_shift_code


def get_expected_plant_count(scope: OperatingScope | None = None) -> int:
    return (scope or DEFAULT_OPERATING_SCOPE).plant_count


def get_expected_warehouse_count(scope: OperatingScope | None = None) -> int:
    return (scope or DEFAULT_OPERATING_SCOPE).warehouse_count


def get_calendar_year(scope: OperatingScope | None = None) -> int:
    return (scope or DEFAULT_OPERATING_SCOPE).calendar_year
