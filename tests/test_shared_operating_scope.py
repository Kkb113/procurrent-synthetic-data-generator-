from procurement_data_generator.modules.shared import operating_scope
from procurement_data_generator.modules.shared import (
    ALLOWED_SHIFT_CODES,
    DEFAULT_SHIFT_CODE,
    PLANT_COUNT,
    WAREHOUSE_COUNT,
    get_allowed_shift_codes,
    get_default_shift_code,
    get_expected_plant_count,
    get_expected_warehouse_count,
    is_allowed_shift_code,
)


def test_operating_scope_imports_successfully():
    assert operating_scope is not None


def test_operating_scope_constants_define_simplified_cardinality():
    assert PLANT_COUNT == 1
    assert WAREHOUSE_COUNT == 1
    assert ALLOWED_SHIFT_CODES == ("A",)
    assert DEFAULT_SHIFT_CODE == "A"


def test_shift_code_helper_allows_only_shift_a():
    assert is_allowed_shift_code("A") is True
    assert is_allowed_shift_code("B") is False
    assert is_allowed_shift_code("C") is False


def test_operating_scope_accessors_return_expected_values():
    assert get_expected_plant_count() == 1
    assert get_expected_warehouse_count() == 1
    assert get_default_shift_code() == "A"
    assert get_allowed_shift_codes() == ("A",)
