from __future__ import annotations

import pandas as pd

from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.validation.reconciler import ProcurementReconciler


def test_valid_v2_lifecycle_reconciliation_passes() -> None:
    report = _reconcile(_valid_v2_data())

    assert report.error_count == 0


def test_v2_supplier_quotation_line_component_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["SupplierQuotationLn"].loc[0, "ComponentID"] = 999

    report = _reconcile(data)

    assert _has_issue(report, "V2_QUOTE_COMPONENT_MATCH")


def test_v2_supplier_component_eligibility_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["SupplierComponent"] = data["SupplierComponent"].iloc[0:0]

    report = _reconcile(data)

    assert _has_issue(report, "V2_QUOTE_SUPPLIER_ELIGIBILITY")


def test_v2_multiple_awarded_quotes_warns() -> None:
    data = _valid_v2_data()
    extra_quote = data["SupplierQuotationLn"].iloc[0].copy()
    extra_quote["QuotationLineID"] = 2
    extra_quote["AwardedFlag"] = 1
    data["SupplierQuotationLn"] = pd.concat([data["SupplierQuotationLn"], pd.DataFrame([extra_quote])], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "V2_RFQ_SINGLE_AWARDED_QUOTE", level="warning")


def test_v2_po_from_non_awarded_quote_fails() -> None:
    data = _valid_v2_data()
    data["SupplierQuotationLn"].loc[0, "AwardedFlag"] = 0

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_FROM_AWARDED_QUOTE")


def test_v2_po_supplier_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderHdr"].loc[0, "SupplierID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_SUPPLIER_MATCH")


def test_v2_po_line_price_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderLine"].loc[0, "UnitPrice"] = 11.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_UNIT_PRICE_MATCH")


def test_v2_po_line_amount_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderLine"].loc[0, "LineAmount"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_LINE_AMOUNT")


def test_v2_po_header_total_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderHdr"].loc[0, "TotalAmount"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_HEADER_TOTAL")


def test_v2_schedule_quantity_exceeding_ordered_fails() -> None:
    data = _valid_v2_data()
    data["POSchedule"].loc[0, "ScheduledQuantity"] = 6.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_SCHEDULE_LE_ORDERED")
    assert _has_issue(report, "PO_SCHEDULE_CUMULATIVE_EXCEEDS_ORDERED")


def test_v2_rfq_quantity_exceeding_requested_fails() -> None:
    data = _valid_v2_data()
    data["RFQLine"].loc[0, "RFQQuantity"] = 6.0

    report = _reconcile(data)

    assert _has_issue(report, "RFQ_QUANTITY_EXCEEDS_REQUESTED")


def test_v2_quoted_quantity_exceeding_rfq_fails() -> None:
    data = _valid_v2_data()
    data["SupplierQuotationLn"].loc[0, "QuotedQuantity"] = 6.0

    report = _reconcile(data)

    assert _has_issue(report, "QUOTED_QUANTITY_EXCEEDS_RFQ")


def test_v2_ordered_quantity_exceeding_awarded_quote_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderLine"].loc[0, "OrderedQuantity"] = 6.0

    report = _reconcile(data)

    assert _has_issue(report, "ORDERED_QUANTITY_EXCEEDS_AWARDED_QUOTE")


def test_v2_cumulative_ordered_quantity_exceeding_awarded_quote_fails() -> None:
    data = _valid_v2_data()
    extra = data["PurchaseOrderLine"].iloc[0].copy()
    extra["PurchaseOrderLineID"] = 62
    extra["OrderedQuantity"] = 1.0
    extra["LineAmount"] = 10.0
    data["PurchaseOrderLine"] = pd.concat([data["PurchaseOrderLine"], pd.DataFrame([extra])], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "PO_CUMULATIVE_EXCEEDS_AWARDED_QUOTE")


def test_v2_shipment_quantity_exceeding_schedule_fails() -> None:
    data = _valid_v2_data()
    data["ShipmentLine"].loc[0, "ShippedQuantity"] = 6.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_SHIPMENT_LE_SCHEDULE")
    assert _has_issue(report, "SHIPMENT_CUMULATIVE_EXCEEDS_SCHEDULE")


def test_v2_cumulative_shipment_quantity_exceeding_schedule_fails() -> None:
    data = _valid_v2_data()
    extra = data["ShipmentLine"].iloc[0].copy()
    extra["ShipmentLineID"] = 92
    extra["ShippedQuantity"] = 2.0
    data["ShipmentLine"] = pd.concat([data["ShipmentLine"], pd.DataFrame([extra])], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "SHIPMENT_CUMULATIVE_EXCEEDS_SCHEDULE")
    assert _has_issue(report, "SHIPMENT_CUMULATIVE_EXCEEDS_ORDERED")


def test_v2_receipt_warehouse_plant_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptHeader"].loc[0, "PlantID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "V2_RECEIPT_WAREHOUSE_PLANT")


def test_v2_received_quantity_exceeding_shipped_fails() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptLine"].loc[0, "ReceivedQuantity"] = 6.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_RECEIVED_LE_SHIPPED")
    assert _has_issue(report, "RECEIPT_CUMULATIVE_EXCEEDS_SHIPPED")


def test_v2_cumulative_receipt_quantity_exceeding_shipment_and_ordered_fails() -> None:
    data = _valid_v2_data()
    extra = data["GoodsReceiptLine"].iloc[0].copy()
    extra["GoodsReceiptLineID"] = 112
    extra["ReceivedQuantity"] = 2.0
    extra["ShortQuantity"] = 2.0
    data["GoodsReceiptLine"] = pd.concat([data["GoodsReceiptLine"], pd.DataFrame([extra])], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "RECEIPT_CUMULATIVE_EXCEEDS_SHIPPED")
    assert _has_issue(report, "RECEIPT_CUMULATIVE_EXCEEDS_ORDERED")


def test_v2_short_quantity_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptLine"].loc[0, "ShortQuantity"] = 0.5

    report = _reconcile(data)

    assert _has_issue(report, "V2_SHORT_QTY")


def test_v2_inspection_quantity_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InspectionResult"].loc[0, "RejectedQuantity"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INSPECTION_QTY_TOTAL")
    assert _has_issue(report, "INSPECTION_ACCEPTED_REJECTED_MISMATCH")


def test_v2_inspection_quantity_exceeding_received_fails() -> None:
    data = _valid_v2_data()
    data["InspectionResult"].loc[0, "InspectedQuantity"] = 6.0
    data["InspectionResult"].loc[0, "AcceptedQuantity"] = 6.0
    data["InspectionResult"].loc[0, "RejectedQuantity"] = 0.0

    report = _reconcile(data)

    assert _has_issue(report, "INSPECTION_QUANTITY_EXCEEDS_RECEIVED")


def test_v2_cumulative_accepted_quantity_exceeding_ordered_fails() -> None:
    data = _valid_v2_data()
    extra = data["InspectionResult"].iloc[0].copy()
    extra["InspectionResultID"] = 132
    data["InspectionResult"] = pd.concat([data["InspectionResult"], pd.DataFrame([extra])], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "ACCEPTED_CUMULATIVE_EXCEEDS_ORDERED")


def test_v2_inventory_quantity_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "TransactionQuantity"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ACCEPTED_QTY")
    assert _has_issue(report, "INVENTORY_TRANSACTION_ACCEPTED_MISMATCH")


def test_v2_cumulative_inventory_transaction_quantity_exceeding_ordered_fails() -> None:
    data = _valid_v2_data()
    extra = data["InventoryTransaction"].iloc[0].copy()
    extra["InventoryTransactionID"] = 142
    data["InventoryTransaction"] = pd.concat([data["InventoryTransaction"], pd.DataFrame([extra])], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "INVENTORY_TRANSACTION_CUMULATIVE_EXCEEDS_ORDERED")


def test_v2_inventory_transaction_type_not_stock_in_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "TransactionType"] = "Receipt"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_TRANSACTION_STOCK_IN")


def test_v2_inventory_receipt_detail_missing_fails() -> None:
    data = _valid_v2_data()
    data.pop("InventoryReceiptDetail")

    report = _reconcile(data)

    assert _has_issue(report, "V2_REQUIRED_TABLE_MISSING")


def test_v2_inventory_receipt_detail_lineage_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryReceiptDetail"].loc[0, "SupplierID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_SUPPLIER_LINEAGE")


def test_v2_inventory_receipt_detail_value_formula_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryReceiptDetail"].loc[0, "AcceptedStockValue"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_ACCEPTED_STOCK_VALUE")


def test_v2_inventory_receipt_detail_status_logic_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryReceiptDetail"].loc[0, "PriceVarianceStatus"] = "PriceIncrease"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_PRICE_VARIANCE_STATUS")


def test_v2_inventory_transaction_goods_receipt_line_orphan_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "GoodsReceiptLineID"] = 999

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_GOODS_RECEIPT_LINE_LINEAGE")


def test_v2_inventory_transaction_purchase_order_line_orphan_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "PurchaseOrderLineID"] = 999

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_PO_LINE_RECEIPT_LINEAGE")


def test_v2_inventory_transaction_supplier_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "SupplierID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_SUPPLIER_LINEAGE")


def test_v2_inventory_transaction_po_line_receipt_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptLine"].loc[0, "PurchaseOrderLineID"] = 999

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_PO_LINEAGE")


def test_v2_inventory_transaction_component_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "ComponentID"] = 11

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_COMPONENT_RECEIPT_MATCH")
    assert _has_issue(report, "V2_INVENTORY_COMPONENT_PO_MATCH")


def test_v2_inventory_location_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "WarehouseID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_WAREHOUSE_PLANT")


def test_v2_inventory_transaction_location_lineage_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptHeader"].loc[0, "WarehouseID"] = 1001

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_LOCATION_LINEAGE")


def test_v2_inventory_transaction_unit_price_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "UnitPrice"] = 11.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_UNIT_PRICE_MATCH")


def test_v2_inventory_transaction_value_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "InventoryValue"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_TRANSACTION_VALUE")


def test_v2_inventory_transaction_negative_value_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "InventoryValue"] = -1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_TRANSACTION_VALUE_NON_NEGATIVE")


def test_v2_inventory_transaction_invalid_status_fails() -> None:
    data = _valid_v2_data()
    data["InventoryTransaction"].loc[0, "InventoryStatus"] = "RandomText"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_TRANSACTION_STATUS_ALLOWED")


def test_v2_inventory_snapshot_component_orphan_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "ComponentID"] = 999

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ON_HAND_RECONCILIATION")


def test_v2_inventory_snapshot_warehouse_plant_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "WarehouseID"] = 1001

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_SNAPSHOT_WAREHOUSE_PLANT")


def test_v2_inventory_on_hand_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "OnHandQuantity"] = 4.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ON_HAND_RECONCILIATION")


def test_v2_inventory_available_quantity_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "AvailableQuantity"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_AVAILABLE_RECONCILIATION")


def test_v2_inventory_on_hand_value_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "OnHandValue"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ON_HAND_VALUE_RECONCILIATION")


def test_v2_inventory_available_value_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "AvailableValue"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_AVAILABLE_VALUE_RECONCILIATION")


def test_v2_inventory_negative_values_fail() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "OnHandValue"] = -1.0
    data["Inventory"].loc[0, "AvailableValue"] = -1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ON_HAND_VALUE_NON_NEGATIVE")
    assert _has_issue(report, "V2_INVENTORY_AVAILABLE_VALUE_NON_NEGATIVE")


def test_v2_inventory_available_value_above_on_hand_value_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "AvailableValue"] = 51.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_AVAILABLE_VALUE_LE_ON_HAND_VALUE")


def test_v2_inventory_reserved_above_on_hand_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "ReservedQuantity"] = 6.0
    data["Inventory"].loc[0, "AvailableQuantity"] = -1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_RESERVED_LE_ON_HAND")


def test_v2_inventory_negative_quantity_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "OnHandQuantity"] = -1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_ON_HAND_NON_NEGATIVE")


def test_v2_inventory_last_transaction_date_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "LastTransactionDate"] = "2025-01-14"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_LAST_TRANSACTION_DATE")


def test_v2_inventory_last_updated_before_transaction_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "LastUpdatedDate"] = "2025-01-14"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_LAST_UPDATED_DATE")


def test_v2_inventory_status_logic_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["Inventory"].loc[0, "ReservedQuantity"] = 3.0
    data["Inventory"].loc[0, "AvailableQuantity"] = 0.0
    data["Inventory"].loc[0, "InventoryStatus"] = "Available"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVENTORY_STATUS_LOGIC")


def test_v2_invoice_date_before_receipt_fails() -> None:
    data = _valid_v2_data()
    data["SupplierInvoice"].loc[0, "InvoiceDate"] = "2025-01-01"

    report = _reconcile(data)

    assert _has_issue(report, "V2_RECEIPT_TO_INVOICE_DATE")


def test_v2_invoice_total_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["SupplierInvoice"].loc[0, "TotalInvoiceAmount"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVOICE_TOTAL")


def test_v2_invoice_total_accepts_formula_rounding_at_tolerance_boundary() -> None:
    data = _valid_v2_data()
    expected = (
        data["SupplierInvoice"].loc[0, "InvoiceAmount"]
        + data["SupplierInvoice"].loc[0, "TaxAmount"]
        + data["SupplierInvoice"].loc[0, "FreightAmount"]
    )
    data["SupplierInvoice"].loc[0, "TotalInvoiceAmount"] = expected + 0.01

    report = _reconcile(data)

    assert not _has_issue(report, "V2_INVOICE_TOTAL")


def test_v2_payment_date_before_invoice_fails() -> None:
    data = _valid_v2_data()
    data["PaymentTransaction"].loc[0, "PaymentDate"] = "2025-01-01"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVOICE_TO_PAYMENT_DATE")


def test_v2_payment_amount_above_invoice_total_fails() -> None:
    data = _valid_v2_data()
    data["PaymentTransaction"].loc[0, "PaymentAmount"] = 100.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_PAYMENT_LE_INVOICE")


def test_v2_po_header_closed_with_partial_stock_in_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderHdr"].loc[0, "POStatus"] = "Closed"

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_HEADER_CLOSED_WITH_PARTIAL_STOCK_IN")


def test_v2_po_line_closed_with_partial_stock_in_fails() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderLine"].loc[0, "LineStatus"] = "Closed"

    report = _reconcile(data)

    assert _has_issue(report, "V2_PO_LINE_CLOSED_WITH_PARTIAL_STOCK_IN")


def test_v2_paid_payment_status_with_partial_amount_fails() -> None:
    data = _valid_v2_data()
    data["PaymentTransaction"].loc[0, "PaymentStatus"] = "Paid"

    report = _reconcile(data)

    assert _has_issue(report, "V2_PAYMENT_STATUS_LOGIC")


def test_v2_paid_invoice_status_with_partial_payment_fails() -> None:
    data = _valid_v2_data()
    data["SupplierInvoice"].loc[0, "InvoiceStatus"] = "Paid"

    report = _reconcile(data)

    assert _has_issue(report, "V2_INVOICE_STATUS_LOGIC")


def test_v2_received_status_with_short_quantity_fails() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptLine"].loc[0, "ShortQuantity"] = 0.5

    report = _reconcile(data)

    assert _has_issue(report, "V2_RECEIPT_STATUS_LOGIC")


def test_v2_passed_result_status_with_rejected_quantity_fails() -> None:
    data = _valid_v2_data()
    data["InspectionResult"].loc[0, "RejectedQuantity"] = 1.0

    report = _reconcile(data)

    assert _has_issue(report, "V2_INSPECTION_STATUS_REALISM")


def test_v2_payment_supplier_mismatch_fails() -> None:
    data = _valid_v2_data()
    data["PaymentTransaction"].loc[0, "SupplierID"] = 2

    report = _reconcile(data)

    assert _has_issue(report, "V2_PAYMENT_SUPPLIER_MATCH")


def test_v2_rejection_reason_with_zero_rejected_fails() -> None:
    data = _valid_v2_data()
    data["InspectionResult"].loc[0, "AcceptedQuantity"] = 3.5
    data["InspectionResult"].loc[0, "RejectedQuantity"] = 0.0
    data["InspectionResult"].loc[0, "RejectionRatePct"] = 0.0
    data["InspectionResult"].loc[0, "RejectionReason"] = "Surface Defect"
    data["InspectionResult"].loc[0, "ResultStatus"] = "Passed"
    data["InventoryTransaction"].loc[0, "TransactionQuantity"] = 3.5

    report = _reconcile(data)

    assert _has_issue(report, "V2_REJECTION_REASON_ZERO")


def test_v2_rejection_reason_missing_for_rejected_quantity_fails() -> None:
    data = _valid_v2_data()
    data["InspectionResult"].loc[0, "RejectedQuantity"] = 1.0
    data["InspectionResult"].loc[0, "RejectionReason"] = ""

    report = _reconcile(data)

    assert _has_issue(report, "V2_REJECTION_REASON_REQUIRED")


def test_v2_price_difference_pct_uses_stored_price_difference() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderLine"].loc[0, "UnitPrice"] = 32.0
    data["PurchaseOrderLine"].loc[0, "LineAmount"] = 160.0
    data["PurchaseOrderHdr"].loc[0, "TotalAmount"] = 160.0
    data["InventoryReceiptDetail"].loc[0, "OrderedUnitPrice"] = 32.0
    data["InventoryReceiptDetail"].loc[0, "DeliveredUnitPrice"] = 32.2
    data["InventoryReceiptDetail"].loc[0, "PriceDifference"] = 0.2
    data["InventoryReceiptDetail"].loc[0, "PriceDifferencePct"] = 0.62
    data["InventoryReceiptDetail"].loc[0, "OrderedValue"] = 160.0
    data["InventoryReceiptDetail"].loc[0, "DeliveredValue"] = 161.0
    data["InventoryReceiptDetail"].loc[0, "AcceptedStockValue"] = 161.0
    data["InventoryReceiptDetail"].loc[0, "PriceVarianceStatus"] = "PriceIncrease"
    data["InventoryTransaction"].loc[0, "UnitPrice"] = 32.2
    data["InventoryTransaction"].loc[0, "InventoryValue"] = 161.0
    data["Inventory"].loc[0, "OnHandValue"] = 161.0
    data["Inventory"].loc[0, "AvailableValue"] = 128.8

    report = _reconcile(data)

    assert not _has_issue(report, "V2_INVENTORY_RECEIPT_DETAIL_PRICE_DIFFERENCE_PCT")


def test_v2_countable_component_decimal_quantity_fails_precision_check() -> None:
    data = _valid_v2_data()
    data["PurchaseReqLine"].loc[0, "RequestedQuantity"] = 5.5

    report = _reconcile(data)

    assert _has_issue(report, "V2_INTEGER_QUANTITY_PRECISION_PURCHASEREQLINE_REQUESTEDQUANTITY")


def test_v2_operating_scope_rejects_extra_plant_row() -> None:
    data = _valid_v2_data()
    data["Plant"] = pd.concat([data["Plant"], pd.DataFrame({"PlantID": [200]})], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_PLANT_COUNT")


def test_v2_operating_scope_rejects_extra_warehouse_row() -> None:
    data = _valid_v2_data()
    data["Warehouse"] = pd.concat([data["Warehouse"], pd.DataFrame({"WarehouseID": [1001], "PlantID": [100]})], ignore_index=True)

    report = _reconcile(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_WAREHOUSE_COUNT")


def test_v2_operating_scope_rejects_wrong_plant_reference() -> None:
    data = _valid_v2_data()
    data["PurchaseOrderHdr"].loc[0, "PlantID"] = 200

    report = _reconcile(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_PLANT_REFERENCE")


def test_v2_operating_scope_rejects_wrong_warehouse_reference() -> None:
    data = _valid_v2_data()
    data["GoodsReceiptHeader"].loc[0, "WarehouseID"] = 1001

    report = _reconcile(data)

    assert _has_issue(report, "V2_OPERATING_SCOPE_WAREHOUSE_REFERENCE")


def _reconcile(data: dict[str, pd.DataFrame]):
    return ProcurementReconciler().reconcile_dataset(data, SchemaContract(tables={}), model_version="v2")


def _valid_v2_data() -> dict[str, pd.DataFrame]:
    return {
        "SupplierMaster": pd.DataFrame({"SupplierID": [1]}),
        "ComponentMaster": pd.DataFrame({"ComponentID": [10], "UOM": ["EA"]}),
        "Plant": pd.DataFrame({"PlantID": [100]}),
        "Warehouse": pd.DataFrame({"WarehouseID": [1000], "PlantID": [100]}),
        "SupplierComponent": pd.DataFrame({"SupplierID": [1], "ComponentID": [10]}),
        "PurchaseRequisition": pd.DataFrame({"RequisitionID": [1], "PlantID": [100], "RequisitionDate": ["2025-01-01"], "RequiredDate": ["2025-01-10"]}),
        "PurchaseReqLine": pd.DataFrame({"RequisitionLineID": [11], "RequisitionID": [1], "ComponentID": [10], "RequestedQuantity": [5.0]}),
        "RFQHeader": pd.DataFrame({"RFQID": [21], "RequisitionID": [1], "RFQDate": ["2025-01-02"], "RFQDueDate": ["2025-01-05"]}),
        "RFQLine": pd.DataFrame({"RFQLineID": [22], "RFQID": [21], "RequisitionLineID": [11], "ComponentID": [10], "RFQQuantity": [5.0]}),
        "SupplierQuotation": pd.DataFrame({"QuotationID": [31], "RFQID": [21], "SupplierID": [1], "QuotationDate": ["2025-01-03"], "ValidUntilDate": ["2025-01-20"]}),
        "SupplierQuotationLn": pd.DataFrame({"QuotationLineID": [41], "QuotationID": [31], "RFQLineID": [22], "ComponentID": [10], "QuotedQuantity": [5.0], "QuotedUnitPrice": [10.0], "AwardedFlag": [1], "LineStatus": ["Awarded"]}),
        "PurchaseOrderHdr": pd.DataFrame({"PurchaseOrderID": [51], "SupplierID": [1], "PlantID": [100], "QuotationID": [31], "OrderDate": ["2025-01-04"], "ExpectedDeliveryDate": ["2025-01-15"], "POStatus": ["Received"], "TotalAmount": [50.0]}),
        "PurchaseOrderLine": pd.DataFrame({"PurchaseOrderLineID": [61], "PurchaseOrderID": [51], "QuotationLineID": [41], "ComponentID": [10], "OrderedQuantity": [5.0], "UnitPrice": [10.0], "LineAmount": [50.0], "LineStatus": ["Received"]}),
        "POSchedule": pd.DataFrame({"POScheduleID": [71], "PurchaseOrderLineID": [61], "ScheduledDeliveryDate": ["2025-01-12"], "ScheduledQuantity": [5.0], "ScheduleStatus": ["Shipped"]}),
        "ShipmentHdr": pd.DataFrame({"ShipmentID": [81], "PurchaseOrderID": [51], "SupplierID": [1], "ShipmentDate": ["2025-01-13"], "ShipmentStatus": ["Delivered"]}),
        "ShipmentLine": pd.DataFrame({"ShipmentLineID": [91], "ShipmentID": [81], "POScheduleID": [71], "PurchaseOrderLineID": [61], "ComponentID": [10], "ShippedQuantity": [5.0]}),
        "GoodsReceiptHeader": pd.DataFrame({"GoodsReceiptID": [101], "ShipmentID": [81], "PlantID": [100], "WarehouseID": [1000], "ReceiptDate": ["2025-01-14"], "ReceiptStatus": ["Received"]}),
        "GoodsReceiptLine": pd.DataFrame({"GoodsReceiptLineID": [111], "GoodsReceiptID": [101], "ShipmentLineID": [91], "PurchaseOrderLineID": [61], "ComponentID": [10], "ShippedQuantity": [5.0], "ReceivedQuantity": [5.0], "DamagedQuantity": [0.0], "ShortQuantity": [0.0]}),
        "IncomingInspection": pd.DataFrame({"InspectionID": [121], "GoodsReceiptLineID": [111], "InspectionDate": ["2025-01-15"], "InspectionStatus": ["Passed"]}),
        "InspectionResult": pd.DataFrame({"InspectionResultID": [131], "InspectionID": [121], "InspectedQuantity": [5.0], "AcceptedQuantity": [5.0], "RejectedQuantity": [0.0], "RejectionRatePct": [0.0], "RejectionReason": ["Not Applicable"], "ResultStatus": ["Passed"]}),
        "InventoryReceiptDetail": pd.DataFrame(
            {
                "InventoryReceiptDetailID": [181],
                "InspectionResultID": [131],
                "GoodsReceiptLineID": [111],
                "PurchaseOrderLineID": [61],
                "PurchaseOrderID": [51],
                "SupplierID": [1],
                "ComponentID": [10],
                "PlantID": [100],
                "WarehouseID": [1000],
                "POOrderDate": ["2025-01-04"],
                "ExpectedDeliveryDate": ["2025-01-12"],
                "ActualDeliveryDate": ["2025-01-14"],
                "StockPostedDate": ["2025-01-15"],
                "OrderedQuantity": [5.0],
                "ShippedQuantity": [5.0],
                "ReceivedQuantity": [5.0],
                "InspectedQuantity": [5.0],
                "AcceptedQuantity": [5.0],
                "RejectedQuantity": [0.0],
                "OrderedUnitPrice": [10.0],
                "DeliveredUnitPrice": [10.0],
                "PriceDifference": [0.0],
                "PriceDifferencePct": [0.0],
                "OrderedValue": [50.0],
                "DeliveredValue": [50.0],
                "AcceptedStockValue": [50.0],
                "OrderYear": [2025],
                "DeliveryYear": [2025],
                "CrossYearDeliveryFlag": [0],
                "DeliveryDelayDays": [2],
                "DeliveryStatus": ["Delayed"],
                "PriceVarianceStatus": ["NoChange"],
                "InventoryReceiptStatus": ["Received"],
            }
        ),
        "InventoryTransaction": pd.DataFrame({"InventoryTransactionID": [141], "InspectionResultID": [131], "GoodsReceiptLineID": [111], "PurchaseOrderLineID": [61], "SupplierID": [1], "ComponentID": [10], "PlantID": [100], "WarehouseID": [1000], "TransactionDate": ["2025-01-15"], "TransactionType": ["StockIn"], "TransactionQuantity": [5.0], "UnitPrice": [10.0], "InventoryValue": [50.0], "ReferenceDocument": ["IRD-000181"], "InventoryStatus": ["Posted"]}),
        "Inventory": pd.DataFrame({"InventoryID": [171], "ComponentID": [10], "PlantID": [100], "WarehouseID": [1000], "OnHandQuantity": [5.0], "ReservedQuantity": [1.0], "AvailableQuantity": [4.0], "OnHandValue": [50.0], "AvailableValue": [40.0], "LastTransactionDate": ["2025-01-15"], "LastUpdatedDate": ["2025-01-15"], "InventoryStatus": ["Available"]}),
        "SupplierInvoice": pd.DataFrame({"SupplierInvoiceID": [151], "PurchaseOrderID": [51], "SupplierID": [1], "GoodsReceiptID": [101], "InvoiceDate": ["2025-01-17"], "DueDate": ["2025-02-16"], "InvoiceStatus": ["PartiallyPaid"], "InvoiceAmount": [50.0], "TaxAmount": [1.0], "FreightAmount": [2.0], "TotalInvoiceAmount": [53.0]}),
        "PaymentTransaction": pd.DataFrame({"PaymentTransactionID": [161], "SupplierInvoiceID": [151], "SupplierID": [1], "PaymentDate": ["2025-01-20"], "PaymentAmount": [20.0], "PaymentStatus": ["PartiallyPaid"]}),
    }


def _has_issue(report, check_type: str, level: str = "error") -> bool:
    return any(issue.check_type == check_type and issue.level == level for issue in report.issues)
