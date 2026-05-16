from __future__ import annotations

import pytest

from procurement_data_generator.core.validation.reconciler import ProcurementReconciler
from tests.test_reconciler_v2 import _has_issue, _reconcile, _valid_v2_data


def test_procurement_reconciler_validates_active_v2_data() -> None:
    report = _reconcile(_valid_v2_data())

    assert report.error_count == 0


def test_procurement_reconciler_rejects_v2_inventory_receipt_quantity_mismatch() -> None:
    data = _valid_v2_data()
    data["InventoryReceiptDetail"].loc[0, "AcceptedQuantity"] = 4.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_ACCEPTED_QTY")


def test_procurement_reconciler_rejects_v2_inventory_rollup_mismatch() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "OnHandQuantity"] = 99.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ON_HAND_RECONCILIATION")


def test_procurement_reconciler_rejects_v2_multiple_plant_scope() -> None:
    data = _valid_v2_data()
    data["Plant"].loc[1] = {"PlantID": 101}

    report = _reconcile(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_PLANT_COUNT")


def test_procurement_v1_reconciliation_is_no_longer_supported() -> None:
    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        ProcurementReconciler().reconcile_dataset(_valid_v2_data(), schema=None, model_version="v1")
