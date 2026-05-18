"""Backward-compatible generated data validator import path.

New generic validation lives in :mod:`procurement_data_generator.core.validation.generic_validator`.
The historical ``GeneratedDataValidator`` entry point remains Procurement v2
compatible and delegates to the Procurement module-owned validator.
"""

from __future__ import annotations

from procurement_data_generator.core.validation.generic_validator import GenericGeneratedDataValidator, _json_safe
from procurement_data_generator.modules.procurement.validation_rules import ProcurementGeneratedDataValidator


class GeneratedDataValidator(ProcurementGeneratedDataValidator):
    """Compatibility alias for the existing Procurement v2 validator."""


__all__ = ["GeneratedDataValidator", "GenericGeneratedDataValidator", "_json_safe"]
