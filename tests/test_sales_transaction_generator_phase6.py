from __future__ import annotations

import re

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.transaction_generator import (
    SALES_PHASE6_TRANSACTION_TABLES,
    SalesTransactionGenerator,
)
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_transaction_generator_can_generate_phase6_return_tables() -> None:
    phase6 = _generate_phase6()

    assert tuple(phase6) == SALES_PHASE6_TRANSACTION_TABLES
    assert set(phase6) == {"SalesReturnHeader", "SalesReturnLine"}
    assert "SalesCreditMemo" not in phase6
    assert "SalesShipmentTraceability" not in phase6


def test_sales_phase6_required_columns_and_primary_keys() -> None:
    phase6 = _generate_phase6()
    expected_columns = {
        "SalesReturnHeader": (
            "SalesReturnID",
            "ReturnNumber",
            "CustomerID",
            "SalesOrderID",
            "ShipmentID",
            "ReturnDate",
            "ReturnReason",
            "ReturnStatus",
        ),
        "SalesReturnLine": (
            "SalesReturnLineID",
            "SalesReturnID",
            "ShipmentLineID",
            "ProductID",
            "ReturnedQuantity",
            "RestockedQuantity",
            "ScrappedQuantity",
            "ReturnUnitValue",
            "ReturnLineStatus",
        ),
    }

    for table_name, columns in expected_columns.items():
        assert tuple(phase6[table_name].columns) == columns
        assert not phase6[table_name].empty
    assert phase6["SalesReturnHeader"]["SalesReturnID"].is_unique
    assert phase6["SalesReturnLine"]["SalesReturnLineID"].is_unique


def test_sales_phase6_return_foreign_keys_are_valid() -> None:
    sales_master, phase4, _, phase6 = _generate_all()
    return_header = phase6["SalesReturnHeader"]
    return_line = phase6["SalesReturnLine"]
    shipment_line_product = phase4["SalesShipmentLine"].set_index("ShipmentLineID")["ProductID"].to_dict()

    assert set(return_header["CustomerID"]).issubset(set(sales_master["CustomerMaster"]["CustomerID"]))
    assert set(return_header["SalesOrderID"]).issubset(set(phase4["SalesOrderHdr"]["SalesOrderID"]))
    assert set(return_header["ShipmentID"]).issubset(set(phase4["SalesShipmentHeader"]["ShipmentID"]))
    assert set(return_line["SalesReturnID"]).issubset(set(return_header["SalesReturnID"]))
    assert set(return_line["ShipmentLineID"]).issubset(set(phase4["SalesShipmentLine"]["ShipmentLineID"]))
    for row in return_line.itertuples(index=False):
        assert row.ProductID == shipment_line_product[row.ShipmentLineID]


def test_sales_phase6_return_quantities_are_valid_and_balanced() -> None:
    _, phase4, _, phase6 = _generate_all()
    shipped_quantity_by_line = phase4["SalesShipmentLine"].set_index("ShipmentLineID")["ShippedQuantity"].to_dict()
    return_line = phase6["SalesReturnLine"]

    assert (return_line["ReturnedQuantity"] > 0).all()
    assert (return_line["RestockedQuantity"] >= 0).all()
    assert (return_line["ScrappedQuantity"] >= 0).all()
    for row in return_line.itertuples(index=False):
        assert row.ReturnedQuantity <= shipped_quantity_by_line[row.ShipmentLineID]
        assert row.ReturnedQuantity == pytest.approx(round(row.RestockedQuantity + row.ScrappedQuantity, 2))
        if row.RestockedQuantity > 0 and row.ScrappedQuantity == 0:
            assert row.ReturnLineStatus == "Restocked"
        elif row.ScrappedQuantity > 0 and row.RestockedQuantity == 0:
            assert row.ReturnLineStatus == "Scrapped"
        else:
            assert row.ReturnLineStatus == "Received"


def test_sales_phase6_return_dates_values_and_reasons_are_valid() -> None:
    _, phase4, phase5, phase6 = _generate_all()
    shipment_date_by_id = phase4["SalesShipmentHeader"].set_index("ShipmentID")["ShipmentDate"].to_dict()
    invoice_unit_price_by_shipment_line = phase5["SalesInvoiceLine"].set_index("ShipmentLineID")["UnitPrice"].to_dict()

    for header in phase6["SalesReturnHeader"].itertuples(index=False):
        assert header.ReturnDate >= shipment_date_by_id[header.ShipmentID]
        assert header.ReturnReason in FOOD_MANUFACTURING_PROFILE.sales.return_reasons
        assert header.ReturnStatus in {"Received", "Approved", "Requested", "Rejected"}
    for line in phase6["SalesReturnLine"].itertuples(index=False):
        assert line.ReturnUnitValue > 0
        assert line.ReturnUnitValue == invoice_unit_price_by_shipment_line[line.ShipmentLineID]


def test_sales_phase6_does_not_mutate_finished_goods_inventory() -> None:
    upstream = _upstream_data()
    original_inventory = upstream["FinishedGoodsInventory"].copy(deep=True)
    _generate_all(upstream=upstream)

    pd.testing.assert_frame_equal(upstream["FinishedGoodsInventory"], original_inventory)


def test_sales_phase6_generation_is_deterministic_for_same_inputs() -> None:
    first = _generate_phase6()
    second = _generate_phase6()

    for table_name in SALES_PHASE6_TRANSACTION_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])


def test_sales_phase6_missing_required_inputs_fail_clearly() -> None:
    sales_master, phase4, phase5, _ = _generate_all()
    combined = {**phase4, **phase5}

    with pytest.raises(ValueError, match="SalesShipmentLine"):
        _generator(sales_master).generate_returns_data(
            sales_master_data=sales_master,
            sales_transaction_data={k: v for k, v in combined.items() if k != "SalesShipmentLine"},
        )
    with pytest.raises(ValueError, match="SalesShipmentHeader"):
        _generator(sales_master).generate_returns_data(
            sales_master_data=sales_master,
            sales_transaction_data={k: v for k, v in combined.items() if k != "SalesShipmentHeader"},
        )
    with pytest.raises(ValueError, match="Sales master data CustomerMaster"):
        _generator(sales_master).generate_returns_data(sales_master_data={}, sales_transaction_data=combined)


def test_sales_phase6_food_profile_return_output_has_no_ev_vocabulary() -> None:
    phase6 = _generate_phase6()

    assert _context_row_count(phase6["SalesReturnHeader"], ["ReturnReason"], ("Damaged Packaging", "Seal Failure")) > 0
    _assert_ev_terms_absent(phase6["SalesReturnHeader"], ["ReturnReason", "ReturnStatus"])
    _assert_ev_terms_absent(phase6["SalesReturnLine"], ["ReturnLineStatus"])


def _generate_all(
    upstream: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    sales_master = _sales_master_data(upstream=upstream)
    generator = _generator(sales_master, upstream=upstream)
    phase4 = generator.generate_transaction_data()
    phase5 = generator.generate_invoice_payment_data(sales_master_data=sales_master, sales_transaction_data=phase4)
    phase6 = generator.generate_returns_data(sales_master_data=sales_master, sales_transaction_data={**phase4, **phase5})
    return sales_master, phase4, phase5, phase6


def _generate_phase6() -> dict[str, pd.DataFrame]:
    return _generate_all()[3]


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


def _sales_master_data(upstream: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    return SalesMasterDataGenerator(
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    ).generate_master_data(upstream_data=upstream if upstream is not None else _upstream_data())


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
    }


def _context_row_count(dataframe: pd.DataFrame, columns: list[str], terms: tuple[str, ...]) -> int:
    lowered_terms = tuple(term.lower() for term in terms)
    count = 0
    for _, row in dataframe.iterrows():
        row_text = " ".join(str(row[column]) for column in columns if column in dataframe.columns).lower()
        if any(term in row_text for term in lowered_terms):
            count += 1
    return count


def _assert_ev_terms_absent(dataframe: pd.DataFrame, columns: list[str]) -> None:
    text = " ".join(str(value) for column in columns for value in dataframe[column].dropna().tolist())
    for term in ("Battery", "Automotive", "Chassis", "Drive Unit", "Power Electronics", "Dealer", "Fleet"):
        assert term.lower() not in text.lower()
    assert re.search(r"(?<![A-Za-z])EV(?![A-Za-z])", text, flags=re.IGNORECASE) is None
