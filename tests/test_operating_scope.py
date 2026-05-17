from __future__ import annotations

from datetime import date

import pytest

from procurement_data_generator.core.config import (
    ALLOWED_SHIFT_CODES,
    CALENDAR_YEAR,
    DEFAULT_OPERATING_SCOPE,
    DEFAULT_SHIFT_CODE,
    PLANT_COUNT,
    WAREHOUSE_COUNT,
    OperatingScope,
    default_operating_scope,
    get_allowed_shift_codes,
    get_calendar_year,
    get_default_shift_code,
    get_expected_plant_count,
    get_expected_warehouse_count,
    is_allowed_shift_code,
)
from procurement_data_generator.modules.shared import operating_scope as shared_operating_scope


pytestmark = pytest.mark.unit


def test_default_operating_scope_preserves_current_simple_scope() -> None:
    scope = DEFAULT_OPERATING_SCOPE

    assert scope.plant_count == 1
    assert scope.warehouse_count == 1
    assert scope.shift_codes == ("A",)
    assert scope.default_shift_code == "A"
    assert scope.calendar_year == 2025
    assert scope.allow_cross_year is False
    assert scope.date_start == date(2025, 1, 1)
    assert scope.date_end == date(2025, 12, 31)


def test_default_constants_are_derived_from_default_scope() -> None:
    assert PLANT_COUNT == DEFAULT_OPERATING_SCOPE.plant_count
    assert WAREHOUSE_COUNT == DEFAULT_OPERATING_SCOPE.warehouse_count
    assert ALLOWED_SHIFT_CODES == DEFAULT_OPERATING_SCOPE.shift_codes
    assert DEFAULT_SHIFT_CODE == DEFAULT_OPERATING_SCOPE.default_shift_code
    assert CALENDAR_YEAR == DEFAULT_OPERATING_SCOPE.calendar_year


def test_legacy_shared_operating_scope_imports_remain_compatible() -> None:
    assert shared_operating_scope.OperatingScope is OperatingScope
    assert shared_operating_scope.DEFAULT_OPERATING_SCOPE == DEFAULT_OPERATING_SCOPE
    assert shared_operating_scope.PLANT_COUNT == 1
    assert shared_operating_scope.WAREHOUSE_COUNT == 1
    assert shared_operating_scope.ALLOWED_SHIFT_CODES == ("A",)
    assert shared_operating_scope.DEFAULT_SHIFT_CODE == "A"
    assert shared_operating_scope.get_calendar_year() == 2025


def test_operating_scope_helpers_use_default_scope() -> None:
    assert default_operating_scope() is DEFAULT_OPERATING_SCOPE
    assert get_expected_plant_count() == 1
    assert get_expected_warehouse_count() == 1
    assert get_default_shift_code() == "A"
    assert get_allowed_shift_codes() == ("A",)
    assert get_calendar_year() == 2025
    assert is_allowed_shift_code("A") is True
    assert is_allowed_shift_code("B") is False


def test_operating_scope_helpers_can_use_explicit_scope() -> None:
    scope = OperatingScope(plant_count=2, warehouse_count=3, shift_codes=("A", "B"), default_shift_code="B")

    assert get_expected_plant_count(scope) == 2
    assert get_expected_warehouse_count(scope) == 3
    assert get_default_shift_code(scope) == "B"
    assert get_allowed_shift_codes(scope) == ("A", "B")
    assert is_allowed_shift_code(" B ", scope) is True


def test_shift_codes_are_normalized_to_tuple() -> None:
    scope = OperatingScope(shift_codes=[" A ", "B"], default_shift_code=" B ")

    assert scope.shift_codes == ("A", "B")
    assert scope.default_shift_code == "B"


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("plant_count", {"plant_count": 0}),
        ("warehouse_count", {"warehouse_count": 0}),
        ("calendar_year", {"calendar_year": 0}),
        ("plant_count", {"plant_count": True}),
    ],
)
def test_operating_scope_rejects_invalid_positive_integer_fields(field_name: str, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=field_name):
        OperatingScope(**kwargs)


def test_operating_scope_rejects_empty_shift_codes() -> None:
    with pytest.raises(ValueError, match="shift_codes"):
        OperatingScope(shift_codes=())


def test_operating_scope_rejects_blank_shift_codes() -> None:
    with pytest.raises(ValueError, match="shift_codes"):
        OperatingScope(shift_codes=("A", " "))


def test_operating_scope_rejects_default_shift_outside_shift_codes() -> None:
    with pytest.raises(ValueError, match="default_shift_code"):
        OperatingScope(shift_codes=("A",), default_shift_code="B")


def test_operating_scope_rejects_non_boolean_cross_year_flag() -> None:
    with pytest.raises(ValueError, match="allow_cross_year"):
        OperatingScope(allow_cross_year="false")  # type: ignore[arg-type]
