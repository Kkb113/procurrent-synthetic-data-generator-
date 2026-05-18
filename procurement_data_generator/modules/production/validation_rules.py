"""Production-specific validation rule accessors.

Production v1 generated-data reconciliation already lives in the Production
module. This file provides the module-owned validation boundary used by
plugins and Phase 7 tests without changing the existing validation behavior.
"""

from __future__ import annotations

from procurement_data_generator.modules.production.reconciler_rules import get_production_reconciler_rules


def get_production_validation_rules() -> tuple[str, ...]:
    """Return the active Production generated-data validation rule groups."""

    return get_production_reconciler_rules()


__all__ = ["get_production_validation_rules"]
