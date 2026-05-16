from __future__ import annotations

from pathlib import Path

import pytest
import pandas.testing as pdt

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"

EXPECTED_TRANSACTION_TABLES = {
    "PurchaseRequisition",
    "PurchaseReqLine",
    "RFQHeader",
    "RFQLine",
    "SupplierQuotation",
    "SupplierQuotationLn",
    "PurchaseOrderHdr",
    "PurchaseOrderLine",
    "POSchedule",
    "ShipmentHdr",
    "ShipmentLine",
    "GoodsReceiptHeader",
    "GoodsReceiptLine",
    "IncomingInspection",
    "InspectionResult",
    "InventoryReceiptDetail",
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
}


def test_procurement_transaction_generation_uses_active_v2_lifecycle() -> None:
    _, data = _generate(seed=42)

    assert set(data) == EXPECTED_TRANSACTION_TABLES
    assert "InventoryReceiptDetail" in data
    assert "InventoryTransaction" in data
    assert "Inventory" in data
    assert "InventoryBalance" not in data
    assert set(data["PurchaseOrderHdr"]["POStatus"]) == {"Received"}
    assert set(data["PurchaseOrderLine"]["LineStatus"]) == {"Received"}


def test_procurement_v2_inventory_transaction_sources_from_receipt_detail() -> None:
    _, data = _generate(seed=42)

    receipt_inspection_ids = set(data["InventoryReceiptDetail"]["InspectionResultID"])
    assert set(data["InventoryTransaction"]["InspectionResultID"]).issubset(receipt_inspection_ids)

    merged = data["InventoryTransaction"].merge(
        data["InventoryReceiptDetail"][
            [
                "InspectionResultID",
                "AcceptedQuantity",
                "DeliveredUnitPrice",
                "ComponentID",
                "PlantID",
                "WarehouseID",
            ]
        ],
        on="InspectionResultID",
        suffixes=("", "_Receipt"),
    )
    assert (merged["TransactionQuantity"].round(4) == merged["AcceptedQuantity"].round(4)).all()
    assert (merged["UnitPrice"].round(4) == merged["DeliveredUnitPrice"].round(4)).all()
    assert (merged["ComponentID"] == merged["ComponentID_Receipt"]).all()
    assert (merged["PlantID"] == merged["PlantID_Receipt"]).all()
    assert (merged["WarehouseID"] == merged["WarehouseID_Receipt"]).all()


def test_procurement_v2_transaction_generation_is_deterministic_for_same_seed() -> None:
    _, first = _generate(seed=42)
    _, second = _generate(seed=42)

    for table_name in EXPECTED_TRANSACTION_TABLES:
        pdt.assert_frame_equal(first[table_name], second[table_name])


def test_procurement_v1_transaction_generation_is_no_longer_supported() -> None:
    schema_result = load_metadata_schema(METADATA)
    plan_result = load_llm_plan_json(PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None
    master_data, master_report = ProcurementMasterDataGenerator().generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
        model_version="v2",
    )
    assert master_report.is_valid, [issue.message for issue in master_report.errors]

    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        ProcurementTransactionGenerator().generate_transaction_data(
            schema_result.schema,
            plan_result.plan,
            master_data,
            seed=42,
            model_version="v1",
        )


def _generate(seed: int):
    schema_result = load_metadata_schema(METADATA)
    plan_result = load_llm_plan_json(PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None

    master_data, master_report = ProcurementMasterDataGenerator().generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=seed,
        model_version="v2",
    )
    assert master_report.is_valid, [issue.message for issue in master_report.errors]

    transaction_data, transaction_report = ProcurementTransactionGenerator().generate_transaction_data(
        schema_result.schema,
        plan_result.plan,
        master_data,
        seed=seed,
        model_version="v2",
    )
    assert transaction_report.is_valid, [issue.message for issue in transaction_report.errors]
    return master_data, transaction_data
