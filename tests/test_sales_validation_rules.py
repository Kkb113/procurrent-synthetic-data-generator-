from __future__ import annotations

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.transaction_generator import SalesTransactionGenerator
from procurement_data_generator.modules.sales.validation_rules import SalesDataQualityEngine, validate_sales_generated_data
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_validation_passes_for_valid_generated_dataset() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()

    report = validate_sales_generated_data(
        sales_data,
        upstream_data=upstream,
        adjusted_finished_goods_inventory=adjusted_inventory,
        profile_id="food_manufacturing",
    )

    assert report.overall_status == "passed"
    assert report.error_count == 0
    assert report.checks_run > 0


def test_sales_validation_detects_missing_required_table() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data.pop("SalesShipmentTraceability")

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_REQUIRED_TABLE", "SalesShipmentTraceability")


def test_sales_validation_detects_order_quantity_lifecycle_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesOrderLine"].loc[0, "ReservedQuantity"] = sales_data["SalesOrderLine"].loc[0, "OrderedQuantity"] + 5

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_ORDER_QUANTITY_LIFECYCLE", "SalesOrderLine")


def test_sales_validation_detects_order_financial_formula_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesOrderLine"].loc[0, "LineAmount"] += 99

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_ORDER_FINANCIAL_FORMULA", "SalesOrderLine")


def test_sales_validation_detects_reservation_oversell_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesInventoryReservation"].loc[0, "ReservedQuantity"] = 9999

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_RESERVATION_OVERSELL", "SalesInventoryReservation")


def test_sales_validation_detects_pick_quantity_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesPickListLine"].loc[0, "PickedQuantity"] = sales_data["SalesInventoryReservation"].loc[0, "ReservedQuantity"] + 10

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_PICK_QUANTITY_OR_STATUS", "SalesPickListLine")


def test_sales_validation_detects_shipment_quantity_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesShipmentLine"].loc[0, "ShippedQuantity"] = sales_data["SalesPickListLine"].loc[0, "PickedQuantity"] + 10

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_SHIPMENT_QUANTITY", "SalesShipmentLine")


def test_sales_validation_detects_shipment_cogs_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesShipmentLine"].loc[0, "COGSValue"] += 50

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_SHIPMENT_COGS_FORMULA", "SalesShipmentLine")


def test_sales_validation_detects_invoice_quantity_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesInvoiceLine"].loc[0, "InvoiceQuantity"] += 1

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_INVOICE_LINE_FORMULA", "SalesInvoiceLine")


def test_sales_validation_detects_invoice_total_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesInvoiceHeader"].loc[0, "TotalInvoiceAmount"] += 10

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_INVOICE_TOTAL_FORMULA", "SalesInvoiceHeader")


def test_sales_validation_detects_payment_over_invoice_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    invoice_id = sales_data["SalesInvoiceHeader"].loc[0, "InvoiceID"]
    sales_data["CustomerPaymentReceipt"].loc[
        sales_data["CustomerPaymentReceipt"]["InvoiceID"] == invoice_id,
        "PaidAmount",
    ] = sales_data["SalesInvoiceHeader"].loc[0, "TotalInvoiceAmount"] + 1

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_PAYMENT_OR_INVOICE_STATUS", "SalesInvoiceHeader")


def test_sales_validation_detects_invoice_status_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    unpaid_invoice = sales_data["SalesInvoiceHeader"].iloc[-1]["InvoiceID"]
    sales_data["SalesInvoiceHeader"].loc[sales_data["SalesInvoiceHeader"]["InvoiceID"] == unpaid_invoice, "InvoiceStatus"] = "Paid"

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_PAYMENT_OR_INVOICE_STATUS", "SalesInvoiceHeader")


def test_sales_validation_detects_return_quantity_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesReturnLine"].loc[0, "ReturnedQuantity"] = 999

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_RETURN_QUANTITY_OR_SPLIT", "SalesReturnLine")


def test_sales_validation_detects_return_split_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesReturnLine"].loc[0, "ScrappedQuantity"] += 5

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_RETURN_QUANTITY_OR_SPLIT", "SalesReturnLine")


def test_sales_validation_detects_missing_traceability_for_shipped_line() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    shipment_line_id = sales_data["SalesShipmentLine"].loc[0, "ShipmentLineID"]
    sales_data["SalesShipmentTraceability"] = sales_data["SalesShipmentTraceability"][
        sales_data["SalesShipmentTraceability"]["ShipmentLineID"] != shipment_line_id
    ]

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_TRACEABILITY_ROW_PER_SHIPMENT_LINE", "SalesShipmentTraceability")


def test_sales_validation_detects_traceability_allocation_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    sales_data["SalesShipmentTraceability"].loc[0, "AllocatedConsumedQuantity"] += 5

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_TRACEABILITY_ALLOCATION", "SalesShipmentTraceability")


def test_sales_validation_detects_finished_goods_inventory_rollup_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    adjusted_inventory.loc[0, "OnHandQuantity"] += 1

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_FINISHED_GOODS_INVENTORY_ROLLUP", "FinishedGoodsInventory")


def test_sales_validation_detects_active_reserved_quantity_failure() -> None:
    sales_data, upstream, adjusted_inventory = _valid_sales_dataset()
    adjusted_inventory.loc[0, "ReservedQuantity"] += 1

    report = _validate(sales_data, upstream, adjusted_inventory)

    assert _has_issue(report, "SALES_FINISHED_GOODS_INVENTORY_ROLLUP", "FinishedGoodsInventory")


def _validate(
    sales_data: dict[str, pd.DataFrame],
    upstream: dict[str, pd.DataFrame],
    adjusted_inventory: pd.DataFrame,
):
    return SalesDataQualityEngine().validate_dataset(
        sales_data,
        upstream_data=upstream,
        adjusted_finished_goods_inventory=adjusted_inventory,
        profile_id="food_manufacturing",
    )


def _valid_sales_dataset() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], pd.DataFrame]:
    upstream = _upstream_data()
    sales_master = SalesMasterDataGenerator(
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    ).generate_master_data(upstream_data=upstream)
    generator = SalesTransactionGenerator(
        sales_master_data=sales_master,
        upstream_data=upstream,
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )
    phase4 = generator.generate_transaction_data()
    phase5 = generator.generate_invoice_payment_data(sales_master_data=sales_master, sales_transaction_data=phase4)
    phase6 = generator.generate_returns_data(sales_master_data=sales_master, sales_transaction_data={**phase4, **phase5})
    phase7 = generator.generate_shipment_traceability_data(
        sales_transaction_data={**phase4, **phase5, **phase6},
        upstream_data=upstream,
    )
    sales_data = {**sales_master, **phase4, **phase5, **phase6, **phase7}
    adjusted_inventory = generator.update_finished_goods_inventory_after_sales(
        upstream_data=upstream,
        sales_transaction_data={**phase4, **phase5, **phase6},
    )
    return {name: dataframe.copy(deep=True) for name, dataframe in sales_data.items()}, upstream, adjusted_inventory.copy(deep=True)


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
                "OnHandValue": [1440.0, 1050.0, 1457.5],
                "InventoryStatus": ["Available", "Available", "Available"],
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
                "ReceiptValue": [1440.0, 1050.0, 1457.5],
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


def _has_issue(report, check_type: str, table_name: str | None = None) -> bool:
    return any(
        issue.check_type == check_type and (table_name is None or issue.table_name == table_name)
        for issue in report.errors
    )
