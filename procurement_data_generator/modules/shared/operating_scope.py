"""Shared operating scope rules for Procurement and Production modules."""

PLANT_COUNT = 1
WAREHOUSE_COUNT = 1
ALLOWED_SHIFT_CODES = ("A",)
DEFAULT_SHIFT_CODE = "A"


def is_allowed_shift_code(shift_code):
    """Return whether a shift code is allowed by the current operating scope."""
    return shift_code in ALLOWED_SHIFT_CODES


def get_allowed_shift_codes():
    return ALLOWED_SHIFT_CODES


def get_default_shift_code():
    return DEFAULT_SHIFT_CODE


def get_expected_plant_count():
    return PLANT_COUNT


def get_expected_warehouse_count():
    return WAREHOUSE_COUNT
