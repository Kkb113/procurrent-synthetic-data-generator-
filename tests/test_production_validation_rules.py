from __future__ import annotations

import pytest

from procurement_data_generator.modules.production.reconciler_rules import get_production_reconciler_rules
from procurement_data_generator.modules.production.validation_rules import get_production_validation_rules


@pytest.mark.unit
def test_production_validation_rules_are_module_owned() -> None:
    rules = get_production_validation_rules()

    assert rules == get_production_reconciler_rules()
    assert "production_genealogy_traceability" in rules
    assert "production_cost_summary" in rules
    assert "material_issue_inventory_cap" in rules
