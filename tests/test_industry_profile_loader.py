from __future__ import annotations

import pytest

from procurement_data_generator.modules.shared.industry_profiles import (
    DEFAULT_INDUSTRY_PROFILE_ID,
    EV_MANUFACTURING_PROFILE,
    GENERIC_MES_PROFILE,
    get_default_industry_profile,
    get_industry_profile,
    get_industry_profile_or_default,
    get_supported_industry_profile_ids,
)


def test_default_industry_profile_is_ev_manufacturing() -> None:
    profile = get_default_industry_profile()

    assert DEFAULT_INDUSTRY_PROFILE_ID == "ev_manufacturing"
    assert profile is EV_MANUFACTURING_PROFILE


def test_get_industry_profile_loads_known_profiles() -> None:
    assert get_industry_profile("ev_manufacturing") is EV_MANUFACTURING_PROFILE
    assert get_industry_profile("generic_mes") is GENERIC_MES_PROFILE


def test_get_industry_profile_or_default_uses_ev_when_blank() -> None:
    assert get_industry_profile_or_default(None) is EV_MANUFACTURING_PROFILE
    assert get_industry_profile_or_default("") is EV_MANUFACTURING_PROFILE


def test_get_industry_profile_is_case_and_whitespace_tolerant() -> None:
    assert get_industry_profile(" EV_MANUFACTURING ") is EV_MANUFACTURING_PROFILE


def test_unknown_industry_profile_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Unknown industry profile"):
        get_industry_profile("unknown")


def test_supported_profile_ids_are_exposed() -> None:
    assert get_supported_industry_profile_ids() == ("ev_manufacturing", "generic_mes")
