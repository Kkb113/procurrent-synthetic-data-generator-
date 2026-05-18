from __future__ import annotations

import re

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.transaction_generator import (
    SALES_PHASE7_TRANSACTION_TABLES,
    SalesTransactionGenerator,
)
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_transaction_generator_can_generate_phase7_traceability_table() -> None:
    phase7 = _generate_phase7()

    assert tuple(phase7) == SALES_PHASE7_TRANSACTION_TABLES
    assert set(phase7) == {"SalesShipmentTraceability"}
    assert "SalesCreditMemo" not in phase7


def test_sales_phase7_required_columns_and_primary_key() -> None:
    traceability = _generate_phase7()["SalesShipmentTraceability"]

    assert tuple(traceability.columns) == (
        "SalesTraceabilityID",
        "ShipmentLineID",
        "FinishedGoodsReceiptID",
        "ProductionBatchID",
        "ProductionGenealogyID",
        "MaterialIssueLineID",
        "InventoryReceiptDetailID",
        "SupplierID",
        "ComponentID",
        "ProductID",
        "ShippedQuantity",
        "AllocatedConsumedQuantity",
        "TraceabilityStatus",
    )
    assert not traceability.empty
    assert traceability["SalesTraceabilityID"].is_unique


def test_sales_phase7_traceability_foreign_keys_are_valid() -> None:
    _, phase4, _, _, phase7, upstream = _generate_all()
    traceability = phase7["SalesShipmentTraceability"]

    assert set(traceability["ShipmentLineID"]).issubset(set(phase4["SalesShipmentLine"]["ShipmentLineID"]))
    assert set(traceability["FinishedGoodsReceiptID"]).issubset(set(upstream["FinishedGoodsReceipt"]["FinishedGoodsReceiptID"]))
    assert set(traceability["ProductionBatchID"]).issubset(set(upstream["ProductionBatch"]["ProductionBatchID"]))
    assert set(traceability["ProductionGenealogyID"]).issubset(set(upstream["ProductionGenealogy"]["ProductionGenealogyID"]))
    assert set(traceability["MaterialIssueLineID"]).issubset(set(upstream["MaterialIssueLine"]["MaterialIssueLineID"]))
    assert set(traceability["InventoryReceiptDetailID"]).issubset(set(upstream["InventoryReceiptDetail"]["InventoryReceiptDetailID"]))
    assert set(traceability["SupplierID"]).issubset(set(upstream["SupplierMaster"]["SupplierID"]))
    assert set(traceability["ComponentID"]).issubset(set(upstream["ComponentMaster"]["ComponentID"]))
    assert set(traceability["ProductID"]).issubset(set(upstream["ProductMaster"]["ProductID"]))


def test_sales_phase7_every_shipped_line_has_traceability() -> None:
    _, phase4, _, _, phase7, _ = _generate_all()
    shipped_lines = phase4["SalesShipmentLine"][phase4["SalesShipmentLine"]["ShippedQuantity"] > 0]

    assert set(shipped_lines["ShipmentLineID"]).issubset(set(phase7["SalesShipmentTraceability"]["ShipmentLineID"]))


def test_sales_phase7_allocated_consumed_quantity_formula_is_correct() -> None:
    _, phase4, _, _, phase7, upstream = _generate_all()
    traceability = phase7["SalesShipmentTraceability"]
    merged = (
        traceability.merge(
            phase4["SalesShipmentLine"][["ShipmentLineID", "ShippedQuantity"]],
            on="ShipmentLineID",
            suffixes=("", "_shipment"),
        )
        .merge(upstream["FinishedGoodsReceipt"][["FinishedGoodsReceiptID", "GoodQuantity"]], on="FinishedGoodsReceiptID")
        .merge(upstream["ProductionGenealogy"][["ProductionGenealogyID", "ConsumedQuantity"]], on="ProductionGenealogyID")
    )
    expected = (merged["ConsumedQuantity"] * merged["ShippedQuantity"] / merged["GoodQuantity"]).round(2)

    assert (merged["AllocatedConsumedQuantity"] >= 0).all()
    assert (merged["AllocatedConsumedQuantity"].round(2) == expected).all()
    assert (merged["AllocatedConsumedQuantity"] <= merged["ConsumedQuantity"]).all()


def test_sales_phase7_traceability_status_is_traced() -> None:
    traceability = _generate_phase7()["SalesShipmentTraceability"]

    assert set(traceability["TraceabilityStatus"]) == {"Traced"}


def test_sales_phase7_missing_required_lineage_fails_clearly() -> None:
    sales_master, phase4, upstream = _phase4_context()

    with pytest.raises(ValueError, match="ProductionGenealogy"):
        _generator(sales_master, upstream).generate_shipment_traceability_data(
            sales_transaction_data=phase4,
            upstream_data={k: v for k, v in upstream.items() if k != "ProductionGenealogy"},
        )
    with pytest.raises(ValueError, match="InventoryReceiptDetail"):
        _generator(sales_master, upstream).generate_shipment_traceability_data(
            sales_transaction_data=phase4,
            upstream_data={k: v for k, v in upstream.items() if k != "InventoryReceiptDetail"},
        )
    with pytest.raises(ValueError, match="SupplierMaster"):
        _generator(sales_master, upstream).generate_shipment_traceability_data(
            sales_transaction_data=phase4,
            upstream_data={k: v for k, v in upstream.items() if k != "SupplierMaster"},
        )
    with pytest.raises(ValueError, match="ComponentMaster"):
        _generator(sales_master, upstream).generate_shipment_traceability_data(
            sales_transaction_data=phase4,
            upstream_data={k: v for k, v in upstream.items() if k != "ComponentMaster"},
        )


def test_sales_phase7_does_not_mutate_finished_goods_inventory() -> None:
    upstream = _upstream_data()
    original_inventory = upstream["FinishedGoodsInventory"].copy(deep=True)
    _generate_all(upstream=upstream)

    pd.testing.assert_frame_equal(upstream["FinishedGoodsInventory"], original_inventory)


def test_sales_phase7_generation_is_deterministic_for_same_inputs() -> None:
    first = _generate_phase7()
    second = _generate_phase7()

    for table_name in SALES_PHASE7_TRANSACTION_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])


def test_sales_phase7_food_profile_traceability_output_has_no_ev_vocabulary() -> None:
    traceability = _generate_phase7()["SalesShipmentTraceability"]

    _assert_ev_terms_absent(traceability, ["TraceabilityStatus"])


def _generate_all(
    upstream: dict[str, pd.DataFrame] | None = None,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    upstream_data = upstream if upstream is not None else _upstream_data()
    sales_master = _sales_master_data(upstream_data)
    generator = _generator(sales_master, upstream_data)
    phase4 = generator.generate_transaction_data()
    phase5 = generator.generate_invoice_payment_data(sales_master_data=sales_master, sales_transaction_data=phase4)
    phase6 = generator.generate_returns_data(sales_master_data=sales_master, sales_transaction_data={**phase4, **phase5})
    phase7 = generator.generate_shipment_traceability_data(
        sales_transaction_data={**phase4, **phase5, **phase6},
        upstream_data=upstream_data,
    )
    return sales_master, phase4, phase5, phase6, phase7, upstream_data


def _generate_phase7() -> dict[str, pd.DataFrame]:
    return _generate_all()[4]


def _phase4_context() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    upstream = _upstream_data()
    sales_master = _sales_master_data(upstream)
    phase4 = _generator(sales_master, upstream).generate_transaction_data()
    return sales_master, phase4, upstream


def _generator(
    sales_master_data: dict[str, pd.DataFrame],
    upstream: dict[str, pd.DataFrame] | None = None,
) -> SalesTransactionGenerator:
    return SalesTransactionGenerator(
        sales_master_data=sales_master_data,
        upstream_data=upstream if upstream is not None else _upstream_data(),
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )


def _sales_master_data(upstream: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return SalesMasterDataGenerator(
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    ).generate_master_data(upstream_data=upstream)


def _upstream_data() -> dict[str, pd.DataFrame]:
    return {
        "ProductMaster": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "ProductName": ["Potato Chips", "Corn Snacks", "Seasoned Snack Mix"],
                "ProductCategory": ["Potato Chips", "Corn Snacks", "Seasoned Snack Mix"],
                "UOM": ["EA", "EA", "EA"],
            }
        ),
        "FinishedGoodsInventory": pd.DataFrame(
            {
                "FinishedGoodsInventoryID": [401, 402, 403],
                "ProductID": [101, 102, 103],
                "PlantID": [1, 1, 1],
                "WarehouseID": [1, 1, 1],
                "OnHandQuantity": [120.0, 100.0, 110.0],
                "ReservedQuantity": [0.0, 0.0, 0.0],
                "AvailableQuantity": [120.0, 100.0, 110.0],
            }
        ),
        "FinishedGoodsReceipt": pd.DataFrame(
            {
                "FinishedGoodsReceiptID": [501, 502, 503],
                "ProductID": [101, 102, 103],
                "PlantID": [1, 1, 1],
                "WarehouseID": [1, 1, 1],
                "ProductionBatchID": [601, 602, 603],
                "GoodQuantity": [120.0, 100.0, 110.0],
                "UnitCost": [12.0, 10.5, 13.25],
            }
        ),
        "ProductionBatch": pd.DataFrame(
            {
                "ProductionBatchID": [601, 602, 603],
                "ProductID": [101, 102, 103],
            }
        ),
        "ProductionCostSummary": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "UnitProductionCost": [12.25, 10.75, 13.5],
            }
        ),
        "ProductionGenealogy": pd.DataFrame(
            {
                "ProductionGenealogyID": [1201, 1202, 1203],
                "FinishedGoodsReceiptID": [501, 502, 503],
                "ProductionBatchID": [601, 602, 603],
                "MaterialIssueLineID": [701, 702, 703],
                "ComponentID": [1001, 1002, 1003],
                "InventoryReceiptDetailID": [801, 802, 803],
                "SupplierID": [1101, 1102, 1103],
                "ConsumedQuantity": [48.0, 40.0, 44.0],
                "TraceabilityStatus": ["Traced", "Traced", "Traced"],
            }
        ),
        "MaterialIssueLine": pd.DataFrame(
            {
                "MaterialIssueLineID": [701, 702, 703],
                "InventoryReceiptDetailID": [801, 802, 803],
                "SourceInventoryTransactionID": [901, 902, 903],
                "ComponentID": [1001, 1002, 1003],
                "IssuedQuantity": [48.0, 40.0, 44.0],
            }
        ),
        "InventoryReceiptDetail": pd.DataFrame(
            {
                "InventoryReceiptDetailID": [801, 802, 803],
                "InventoryTransactionID": [901, 902, 903],
                "SupplierID": [1101, 1102, 1103],
                "ComponentID": [1001, 1002, 1003],
                "AcceptedQuantity": [48.0, 40.0, 44.0],
            }
        ),
        "SupplierMaster": pd.DataFrame(
            {
                "SupplierID": [1101, 1102, 1103],
                "SupplierName": ["Ingredient Supplier", "Oil Supplier", "Packaging Supplier"],
            }
        ),
        "ComponentMaster": pd.DataFrame(
            {
                "ComponentID": [1001, 1002, 1003],
                "ComponentName": ["Potato Flakes", "Edible Oil", "Packaging Film Roll"],
            }
        ),
    }


def _assert_ev_terms_absent(dataframe: pd.DataFrame, columns: list[str]) -> None:
    text = " ".join(str(value) for column in columns for value in dataframe[column].dropna().tolist())
    for term in ("Battery", "Automotive", "Chassis", "Drive Unit", "Power Electronics", "Dealer", "Fleet"):
        assert term.lower() not in text.lower()
    assert re.search(r"(?<![A-Za-z])EV(?![A-Za-z])", text, flags=re.IGNORECASE) is None
