"""Sales / Order-to-Cash v1 role catalog."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class SalesRoleDefinition:
    """Expected metadata characteristics for a planned Sales v1 table role."""

    role_name: str
    expected_table_name: str
    table_kind: str
    process_order: int
    purpose: str
    expected_area: str = "Sales"
    required_column_names: tuple[str, ...] = field(default_factory=tuple)
    upstream_notes: tuple[str, ...] = field(default_factory=tuple)


SALES_V1_EXPECTED_TABLES = (
    "CustomerMaster",
    "CustomerLocation",
    "SalesChannel",
    "SalesPriceListHeader",
    "SalesPriceListLine",
    "SalesOrderHdr",
    "SalesOrderLine",
    "SalesInventoryReservation",
    "SalesPickListHeader",
    "SalesPickListLine",
    "SalesShipmentHeader",
    "SalesShipmentLine",
    "SalesInvoiceHeader",
    "SalesInvoiceLine",
    "CustomerPaymentReceipt",
    "SalesReturnHeader",
    "SalesReturnLine",
    "SalesShipmentTraceability",
)


SALES_V1_ROLE_CATALOG: dict[str, SalesRoleDefinition] = {
    "customer_master": SalesRoleDefinition(
        "customer_master",
        "CustomerMaster",
        "master",
        100,
        "Customer account master for Order-to-Cash.",
    ),
    "customer_location": SalesRoleDefinition(
        "customer_location",
        "CustomerLocation",
        "master",
        110,
        "Customer ship-to and bill-to location master.",
    ),
    "sales_channel": SalesRoleDefinition(
        "sales_channel",
        "SalesChannel",
        "reference",
        120,
        "Sales channel reference such as retail, distributor, foodservice, or e-commerce.",
    ),
    "sales_price_list_header": SalesRoleDefinition(
        "sales_price_list_header",
        "SalesPriceListHeader",
        "reference",
        130,
        "Header for channel, customer, or market price lists.",
    ),
    "sales_price_list_line": SalesRoleDefinition(
        "sales_price_list_line",
        "SalesPriceListLine",
        "reference",
        140,
        "Product-level price list line.",
        upstream_notes=("References Production ProductMaster.ProductID.",),
    ),
    "sales_order_header": SalesRoleDefinition(
        "sales_order_header",
        "SalesOrderHdr",
        "transaction",
        200,
        "Sales order header for customer demand.",
    ),
    "sales_order_line": SalesRoleDefinition(
        "sales_order_line",
        "SalesOrderLine",
        "transaction",
        210,
        "Sales order product and quantity line.",
        upstream_notes=("References Production ProductMaster.ProductID.",),
    ),
    "sales_inventory_reservation": SalesRoleDefinition(
        "sales_inventory_reservation",
        "SalesInventoryReservation",
        "transaction",
        220,
        "Finished-goods reservation against SalesOrderLine.",
        upstream_notes=("References Production FinishedGoodsInventory.FinishedGoodsInventoryID.",),
    ),
    "sales_pick_list_header": SalesRoleDefinition(
        "sales_pick_list_header",
        "SalesPickListHeader",
        "transaction",
        230,
        "Warehouse pick list header for Sales fulfillment.",
    ),
    "sales_pick_list_line": SalesRoleDefinition(
        "sales_pick_list_line",
        "SalesPickListLine",
        "transaction",
        240,
        "Pick line for reserved finished goods.",
    ),
    "sales_shipment_header": SalesRoleDefinition(
        "sales_shipment_header",
        "SalesShipmentHeader",
        "transaction",
        250,
        "Customer outbound shipment header.",
    ),
    "sales_shipment_line": SalesRoleDefinition(
        "sales_shipment_line",
        "SalesShipmentLine",
        "transaction",
        260,
        "Finished-goods outbound ledger line for customer shipment.",
        upstream_notes=("Uses FinishedGoodsReceipt.UnitCost for COGS in Sales v1.",),
    ),
    "sales_invoice_header": SalesRoleDefinition(
        "sales_invoice_header",
        "SalesInvoiceHeader",
        "transaction",
        270,
        "Customer invoice header.",
    ),
    "sales_invoice_line": SalesRoleDefinition(
        "sales_invoice_line",
        "SalesInvoiceLine",
        "transaction",
        280,
        "Customer invoice line including COGS and gross margin.",
    ),
    "customer_payment_receipt": SalesRoleDefinition(
        "customer_payment_receipt",
        "CustomerPaymentReceipt",
        "transaction",
        290,
        "Customer payment receipt against Sales invoices.",
    ),
    "sales_return_header": SalesRoleDefinition(
        "sales_return_header",
        "SalesReturnHeader",
        "transaction",
        300,
        "Operational return header for customer returns.",
    ),
    "sales_return_line": SalesRoleDefinition(
        "sales_return_line",
        "SalesReturnLine",
        "transaction",
        310,
        "Operational return line with restocked quantity when applicable.",
    ),
    "sales_shipment_traceability": SalesRoleDefinition(
        "sales_shipment_traceability",
        "SalesShipmentTraceability",
        "traceability",
        320,
        "Customer shipment traceability back through Production and Procurement lineage.",
        upstream_notes=(
            "References FinishedGoodsReceipt, ProductionBatch, ProductionGenealogy, MaterialIssueLine, "
            "InventoryReceiptDetail, InventoryTransaction, SupplierMaster, ComponentMaster, and ProductMaster.",
        ),
    ),
}

SALES_V1_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "customer_master": ("CustomerID", "CustomerCode", "CustomerName", "CustomerType", "Industry", "Country", "Region", "CreditLimit", "PaymentTerms", "CustomerStatus"),
    "customer_location": ("CustomerLocationID", "CustomerID", "LocationType", "AddressLine1", "City", "State", "Country", "PostalCode", "IsDefault"),
    "sales_channel": ("SalesChannelID", "ChannelCode", "ChannelName", "ChannelType", "ChannelStatus"),
    "sales_price_list_header": ("PriceListID", "PriceListName", "CurrencyCode", "EffectiveFromDate", "EffectiveToDate", "PriceListStatus"),
    "sales_price_list_line": ("PriceListLineID", "PriceListID", "ProductID", "UnitPrice", "MinimumOrderQuantity", "DiscountPct", "LineStatus"),
    "sales_order_header": ("SalesOrderID", "SalesOrderNumber", "CustomerID", "BillToLocationID", "ShipToLocationID", "SalesChannelID", "OrderDate", "RequestedShipDate", "PromisedShipDate", "CurrencyCode", "OrderStatus"),
    "sales_order_line": ("SalesOrderLineID", "SalesOrderID", "ProductID", "PlantID", "WarehouseID", "OrderedQuantity", "ReservedQuantity", "ShippedQuantity", "BackorderQuantity", "UOM", "UnitPrice", "DiscountPct", "LineAmount", "DiscountAmount", "NetLineAmount", "LineStatus"),
    "sales_inventory_reservation": ("ReservationID", "SalesOrderLineID", "FinishedGoodsInventoryID", "ProductID", "PlantID", "WarehouseID", "ReservationDate", "ReservedQuantity", "ReleasedQuantity", "ReservationStatus"),
    "sales_pick_list_header": ("PickListID", "SalesOrderID", "WarehouseID", "PickDate", "PickStatus"),
    "sales_pick_list_line": ("PickListLineID", "PickListID", "SalesOrderLineID", "ReservationID", "ProductID", "PickedQuantity", "UOM", "PickLineStatus"),
    "sales_shipment_header": ("ShipmentID", "ShipmentNumber", "SalesOrderID", "CustomerID", "ShipToLocationID", "WarehouseID", "ShipmentDate", "CarrierName", "TrackingNumber", "ShipmentStatus"),
    "sales_shipment_line": ("ShipmentLineID", "ShipmentID", "SalesOrderLineID", "PickListLineID", "FinishedGoodsInventoryID", "FinishedGoodsReceiptID", "ProductionBatchID", "ProductID", "ShippedQuantity", "UOM", "UnitCost", "COGSValue", "ShipmentLineStatus"),
    "sales_invoice_header": ("InvoiceID", "InvoiceNumber", "SalesOrderID", "ShipmentID", "CustomerID", "InvoiceDate", "DueDate", "CurrencyCode", "SubtotalAmount", "DiscountAmount", "TaxAmount", "FreightAmount", "TotalInvoiceAmount", "InvoiceStatus"),
    "sales_invoice_line": ("InvoiceLineID", "InvoiceID", "ShipmentLineID", "SalesOrderLineID", "ProductID", "InvoiceQuantity", "UnitPrice", "DiscountAmount", "TaxAmount", "NetLineAmount", "COGSValue", "GrossMarginAmount", "GrossMarginPct", "LineStatus"),
    "customer_payment_receipt": ("PaymentReceiptID", "InvoiceID", "CustomerID", "PaymentDate", "PaymentMethod", "PaidAmount", "CurrencyCode", "PaymentStatus"),
    "sales_return_header": ("SalesReturnID", "ReturnNumber", "CustomerID", "SalesOrderID", "ShipmentID", "ReturnDate", "ReturnReason", "ReturnStatus"),
    "sales_return_line": ("SalesReturnLineID", "SalesReturnID", "ShipmentLineID", "ProductID", "ReturnedQuantity", "RestockedQuantity", "ScrappedQuantity", "ReturnUnitValue", "ReturnLineStatus"),
    "sales_shipment_traceability": ("SalesTraceabilityID", "ShipmentLineID", "FinishedGoodsReceiptID", "ProductionBatchID", "ProductionGenealogyID", "MaterialIssueLineID", "InventoryReceiptDetailID", "SupplierID", "ComponentID", "ProductID", "ShippedQuantity", "AllocatedConsumedQuantity", "TraceabilityStatus"),
}

SALES_V1_ROLE_CATALOG = {
    role_name: replace(definition, required_column_names=SALES_V1_REQUIRED_COLUMNS[role_name])
    for role_name, definition in SALES_V1_ROLE_CATALOG.items()
}


def get_sales_role_catalog(model_version: str = "v1") -> dict[str, SalesRoleDefinition]:
    """Return the planned Sales v1 role catalog."""

    if model_version != "v1":
        return {}
    return SALES_V1_ROLE_CATALOG
