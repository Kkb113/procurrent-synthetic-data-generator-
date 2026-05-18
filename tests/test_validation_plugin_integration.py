from __future__ import annotations

import pytest

from procurement_data_generator.core.modules.registry import create_default_module_registry
from procurement_data_generator.modules.procurement.data_quality import ProcurementDataQualityEngine


@pytest.mark.unit
def test_default_registry_exposes_procurement_validation_capability() -> None:
    plugin = create_default_module_registry().get("procurement")

    assert isinstance(plugin.create_data_quality_engine(), ProcurementDataQualityEngine)
    assert "procurement_v2_expected_tables" in plugin.get_validation_rules()


@pytest.mark.unit
def test_default_registry_exposes_production_validation_capability() -> None:
    plugin = create_default_module_registry().get("production")

    assert "production_genealogy_traceability" in plugin.get_validation_rules()
    assert "production_cost_summary" in plugin.get_validation_rules()


@pytest.mark.unit
def test_production_quality_engine_remains_explicitly_unsupported_until_phase_8() -> None:
    plugin = create_default_module_registry().get("production")

    with pytest.raises(NotImplementedError, match="validate_production_generated_data"):
        plugin.create_data_quality_engine()
