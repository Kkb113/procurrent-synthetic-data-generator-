"""Sales / Order-to-Cash v1 role catalog."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SalesRoleDefinition:
    """Expected metadata characteristics for a planned Sales v1 table role."""

    role_name: str
    expected_table_name: str
    table_kind: str
    process_order: int
    purpose: str
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
        10,
        "Customer account master for Order-to-Cash.",
    ),
    "customer_location": SalesRoleDefinition(
        "customer_location",
        "CustomerLocation",
        "master",
        20,
        "Customer ship-to and bill-to location master.",
    ),
    "sales_channel": SalesRoleDefinition(
        "sales_channel",
        "SalesChannel",
        "reference",
        30,
        "Sales channel reference such as retail, distributor, foodservice, or e-commerce.",
    ),
    "sales_price_list_header": SalesRoleDefinition(
        "sales_price_list_header",
        "SalesPriceListHeader",
        "reference",
        40,
        "Header for channel, customer, or market price lists.",
    ),
    "sales_price_list_line": SalesRoleDefinition(
        "sales_price_list_line",
        "SalesPriceListLine",
        "reference",
        41,
        "Product-level price list line.",
        ("References Production ProductMaster.ProductID.",),
    ),
    "sales_order_header": SalesRoleDefinition(
        "sales_order_header",
        "SalesOrderHdr",
        "transaction",
        50,
        "Sales order header for customer demand.",
    ),
    "sales_order_line": SalesRoleDefinition(
        "sales_order_line",
        "SalesOrderLine",
        "transaction",
        51,
        "Sales order product and quantity line.",
        ("References Production ProductMaster.ProductID.",),
    ),
    "sales_inventory_reservation": SalesRoleDefinition(
        "sales_inventory_reservation",
        "SalesInventoryReservation",
        "transaction",
        60,
        "Finished-goods reservation against SalesOrderLine.",
        ("References Production FinishedGoodsInventory.FinishedGoodsInventoryID.",),
    ),
    "sales_pick_list_header": SalesRoleDefinition(
        "sales_pick_list_header",
        "SalesPickListHeader",
        "transaction",
        70,
        "Warehouse pick list header for Sales fulfillment.",
    ),
    "sales_pick_list_line": SalesRoleDefinition(
        "sales_pick_list_line",
        "SalesPickListLine",
        "transaction",
        71,
        "Pick line for reserved finished goods.",
    ),
    "sales_shipment_header": SalesRoleDefinition(
        "sales_shipment_header",
        "SalesShipmentHeader",
        "transaction",
        80,
        "Customer outbound shipment header.",
    ),
    "sales_shipment_line": SalesRoleDefinition(
        "sales_shipment_line",
        "SalesShipmentLine",
        "transaction",
        81,
        "Finished-goods outbound ledger line for customer shipment.",
        ("Uses FinishedGoodsReceipt.UnitCost for COGS in Sales v1.",),
    ),
    "sales_invoice_header": SalesRoleDefinition(
        "sales_invoice_header",
        "SalesInvoiceHeader",
        "transaction",
        90,
        "Customer invoice header.",
    ),
    "sales_invoice_line": SalesRoleDefinition(
        "sales_invoice_line",
        "SalesInvoiceLine",
        "transaction",
        91,
        "Customer invoice line including COGS and gross margin.",
    ),
    "customer_payment_receipt": SalesRoleDefinition(
        "customer_payment_receipt",
        "CustomerPaymentReceipt",
        "transaction",
        100,
        "Customer payment receipt against Sales invoices.",
    ),
    "sales_return_header": SalesRoleDefinition(
        "sales_return_header",
        "SalesReturnHeader",
        "transaction",
        110,
        "Operational return header for customer returns.",
    ),
    "sales_return_line": SalesRoleDefinition(
        "sales_return_line",
        "SalesReturnLine",
        "transaction",
        111,
        "Operational return line with restocked quantity when applicable.",
    ),
    "sales_shipment_traceability": SalesRoleDefinition(
        "sales_shipment_traceability",
        "SalesShipmentTraceability",
        "traceability",
        120,
        "Customer shipment traceability back through Production and Procurement lineage.",
        (
            "References FinishedGoodsReceipt, ProductionBatch, ProductionGenealogy, MaterialIssueLine, "
            "InventoryReceiptDetail, InventoryTransaction, SupplierMaster, ComponentMaster, and ProductMaster.",
        ),
    ),
}


def get_sales_role_catalog(model_version: str = "v1") -> dict[str, SalesRoleDefinition]:
    """Return the planned Sales v1 role catalog."""

    if model_version != "v1":
        return {}
    return SALES_V1_ROLE_CATALOG

