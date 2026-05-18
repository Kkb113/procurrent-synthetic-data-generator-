from __future__ import annotations

import re

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.transaction_generator import (
    SALES_PHASE5_TRANSACTION_TABLES,
    SalesTransactionGenerator,
)
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_transaction_generator_can_generate_phase5_invoice_payment_tables() -> None:
    phase5 = _generate_phase5()

    assert tuple(phase5) == SALES_PHASE5_TRANSACTION_TABLES
    assert set(phase5) == {"SalesInvoiceHeader", "SalesInvoiceLine", "CustomerPaymentReceipt"}
    for table_name in ("SalesReturnHeader", "SalesReturnLine", "SalesShipmentTraceability"):
        assert table_name not in phase5


def test_sales_phase5_required_columns_and_primary_keys() -> None:
    phase5 = _generate_phase5()
    expected_columns = {
        "SalesInvoiceHeader": (
            "InvoiceID",
            "InvoiceNumber",
            "SalesOrderID",
            "ShipmentID",
            "CustomerID",
            "InvoiceDate",
            "DueDate",
            "CurrencyCode",
            "SubtotalAmount",
            "DiscountAmount",
            "TaxAmount",
            "FreightAmount",
            "TotalInvoiceAmount",
            "InvoiceStatus",
        ),
        "SalesInvoiceLine": (
            "InvoiceLineID",
            "InvoiceID",
            "ShipmentLineID",
            "SalesOrderLineID",
            "ProductID",
            "InvoiceQuantity",
            "UnitPrice",
            "DiscountAmount",
            "TaxAmount",
            "NetLineAmount",
            "COGSValue",
            "GrossMarginAmount",
            "GrossMarginPct",
            "LineStatus",
        ),
        "CustomerPaymentReceipt": (
            "PaymentReceiptID",
            "InvoiceID",
            "CustomerID",
            "PaymentDate",
            "PaymentMethod",
            "PaidAmount",
            "CurrencyCode",
            "PaymentStatus",
        ),
    }
    pk_columns = {
        "SalesInvoiceHeader": "InvoiceID",
        "SalesInvoiceLine": "InvoiceLineID",
        "CustomerPaymentReceipt": "PaymentReceiptID",
    }

    for table_name, columns in expected_columns.items():
        assert tuple(phase5[table_name].columns) == columns
        assert phase5[table_name][pk_columns[table_name]].is_unique
        assert not phase5[table_name].empty


def test_sales_phase5_foreign_keys_are_valid() -> None:
    sales_master, phase4, phase5 = _generate_all()
    invoice_header = phase5["SalesInvoiceHeader"]
    invoice_line = phase5["SalesInvoiceLine"]
    payment = phase5["CustomerPaymentReceipt"]

    assert set(invoice_header["SalesOrderID"]).issubset(set(phase4["SalesOrderHdr"]["SalesOrderID"]))
    assert set(invoice_header["ShipmentID"]).issubset(set(phase4["SalesShipmentHeader"]["ShipmentID"]))
    assert set(invoice_header["CustomerID"]).issubset(set(sales_master["CustomerMaster"]["CustomerID"]))
    assert set(invoice_line["InvoiceID"]).issubset(set(invoice_header["InvoiceID"]))
    assert set(invoice_line["ShipmentLineID"]).issubset(set(phase4["SalesShipmentLine"]["ShipmentLineID"]))
    assert set(invoice_line["SalesOrderLineID"]).issubset(set(phase4["SalesOrderLine"]["SalesOrderLineID"]))
    assert set(payment["InvoiceID"]).issubset(set(invoice_header["InvoiceID"]))
    assert set(payment["CustomerID"]).issubset(set(sales_master["CustomerMaster"]["CustomerID"]))

    shipment_products = phase4["SalesShipmentLine"].set_index("ShipmentLineID")["ProductID"].to_dict()
    order_products = phase4["SalesOrderLine"].set_index("SalesOrderLineID")["ProductID"].to_dict()
    for row in invoice_line.itertuples(index=False):
        assert row.ProductID == shipment_products[row.ShipmentLineID]
        assert row.ProductID == order_products[row.SalesOrderLineID]


def test_sales_phase5_invoice_line_quantities_cogs_and_margin_reconcile() -> None:
    _, phase4, phase5 = _generate_all()
    shipment_line = phase4["SalesShipmentLine"].set_index("ShipmentLineID")
    invoice_line = phase5["SalesInvoiceLine"]

    for row in invoice_line.itertuples(index=False):
        shipment = shipment_line.loc[row.ShipmentLineID]
        assert row.InvoiceQuantity == shipment["ShippedQuantity"]
        assert row.COGSValue == round(row.InvoiceQuantity * shipment["UnitCost"], 2)
        assert row.GrossMarginAmount == round(row.NetLineAmount - row.COGSValue, 2)
        expected_pct = round(row.GrossMarginAmount / row.NetLineAmount, 4) if row.NetLineAmount > 0 else 0.0
        assert row.GrossMarginPct == pytest.approx(expected_pct)
        assert row.LineStatus == "Invoiced"


def test_sales_phase5_invoice_header_totals_reconcile() -> None:
    phase5 = _generate_phase5()
    invoice_header = phase5["SalesInvoiceHeader"]
    invoice_line = phase5["SalesInvoiceLine"].copy()
    invoice_line["GrossLineAmount"] = (invoice_line["InvoiceQuantity"] * invoice_line["UnitPrice"]).round(2)

    for header in invoice_header.itertuples(index=False):
        lines = invoice_line[invoice_line["InvoiceID"] == header.InvoiceID]
        assert header.SubtotalAmount == pytest.approx(round(lines["GrossLineAmount"].sum(), 2))
        assert header.DiscountAmount == pytest.approx(round(lines["DiscountAmount"].sum(), 2))
        assert header.TaxAmount == pytest.approx(round(lines["TaxAmount"].sum(), 2))
        expected_total = round(header.SubtotalAmount - header.DiscountAmount + header.TaxAmount + header.FreightAmount, 2)
        assert header.TotalInvoiceAmount == pytest.approx(expected_total)


def test_sales_phase5_payments_do_not_exceed_invoice_totals_and_statuses_are_fact_derived() -> None:
    phase5 = _generate_phase5()
    invoice_header = phase5["SalesInvoiceHeader"]
    payment = phase5["CustomerPaymentReceipt"]
    paid_by_invoice = payment.groupby("InvoiceID")["PaidAmount"].sum().to_dict()

    assert {"Paid", "PartiallyPaid", "Open"}.issubset(set(invoice_header["InvoiceStatus"]))
    for header in invoice_header.itertuples(index=False):
        paid_amount = round(float(paid_by_invoice.get(header.InvoiceID, 0.0)), 2)
        assert paid_amount <= header.TotalInvoiceAmount
        if paid_amount >= header.TotalInvoiceAmount:
            assert header.InvoiceStatus == "Paid"
        elif paid_amount > 0:
            assert header.InvoiceStatus == "PartiallyPaid"
        else:
            assert header.InvoiceStatus == "Open"

    for row in payment.itertuples(index=False):
        invoice = invoice_header[invoice_header["InvoiceID"] == row.InvoiceID].iloc[0]
        assert row.PaymentDate >= invoice["InvoiceDate"]
        assert row.PaymentStatus in {"Received", "Partial"}
        if row.PaymentStatus == "Received":
            assert row.PaidAmount == invoice["TotalInvoiceAmount"]
        if row.PaymentStatus == "Partial":
            assert 0 < row.PaidAmount < invoice["TotalInvoiceAmount"]


def test_sales_phase5_due_dates_respect_customer_payment_terms() -> None:
    sales_master, phase4, phase5 = _generate_all()
    terms_by_customer = sales_master["CustomerMaster"].set_index("CustomerID")["PaymentTerms"].to_dict()

    for header in phase5["SalesInvoiceHeader"].itertuples(index=False):
        terms = terms_by_customer[header.CustomerID]
        expected_days = _payment_term_days(terms)
        assert header.DueDate >= header.InvoiceDate
        assert (header.DueDate - header.InvoiceDate).days == expected_days


def test_sales_phase5_generation_is_deterministic_for_same_inputs() -> None:
    first = _generate_phase5()
    second = _generate_phase5()

    for table_name in SALES_PHASE5_TRANSACTION_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])


def test_sales_phase5_missing_required_inputs_fail_clearly() -> None:
    sales_master, phase4, _ = _generate_all()

    with pytest.raises(ValueError, match="SalesShipmentLine"):
        _generator(sales_master).generate_invoice_payment_data(
            sales_master_data=sales_master,
            sales_transaction_data={k: v for k, v in phase4.items() if k != "SalesShipmentLine"},
        )
    with pytest.raises(ValueError, match="SalesShipmentHeader"):
        _generator(sales_master).generate_invoice_payment_data(
            sales_master_data=sales_master,
            sales_transaction_data={k: v for k, v in phase4.items() if k != "SalesShipmentHeader"},
        )
    with pytest.raises(ValueError, match="Sales master data CustomerMaster"):
        _generator(sales_master).generate_invoice_payment_data(sales_master_data={}, sales_transaction_data=phase4)


def test_sales_phase5_food_profile_invoice_payment_text_has_no_ev_vocabulary() -> None:
    phase5 = _generate_phase5()
    payment = phase5["CustomerPaymentReceipt"]

    assert _context_row_count(payment, ["PaymentMethod"], ("BankTransfer", "UPI", "OnlineTransfer")) > 0
    _assert_ev_terms_absent(payment, ["PaymentMethod", "PaymentStatus"])
    _assert_ev_terms_absent(phase5["SalesInvoiceHeader"], ["InvoiceNumber", "CurrencyCode", "InvoiceStatus"])


def _generate_all() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    sales_master = _sales_master_data()
    generator = _generator(sales_master)
    phase4 = generator.generate_transaction_data()
    phase5 = generator.generate_invoice_payment_data(sales_master_data=sales_master, sales_transaction_data=phase4)
    return sales_master, phase4, phase5


def _generate_phase5() -> dict[str, pd.DataFrame]:
    return _generate_all()[2]


def _generator(sales_master_data: dict[str, pd.DataFrame]) -> SalesTransactionGenerator:
    return SalesTransactionGenerator(
        sales_master_data=sales_master_data,
        upstream_data=_upstream_data(),
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )


def _sales_master_data() -> dict[str, pd.DataFrame]:
    return SalesMasterDataGenerator(
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    ).generate_master_data(upstream_data=_upstream_data())


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


def _payment_term_days(payment_terms: str) -> int:
    normalized = str(payment_terms or "").strip().lower().replace(" ", "")
    digits = "".join(character for character in normalized if character.isdigit())
    if digits:
        return int(digits)
    if normalized in {"dueonreceipt", "cod", "cash"}:
        return 0
    return 30


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
