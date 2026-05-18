"""Backward-compatible Procurement data quality import path.

Procurement reconciliation and data-quality checks now live under the
Procurement module. Existing callers can continue importing these names from
``core.validation.reconciler`` during the incremental migration.
"""

from __future__ import annotations

from procurement_data_generator.modules.procurement.data_quality import (
    ProcurementDataQualityEngine,
    ProcurementReconciler,
    format_data_quality_report,
)

__all__ = ["ProcurementDataQualityEngine", "ProcurementReconciler", "format_data_quality_report"]
