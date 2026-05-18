"""Sales v1 metadata fixture support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from procurement_data_generator.core.metadata.metadata_validator import REQUIRED_METADATA_COLUMNS
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_ROLE_CATALOG


@dataclass(frozen=True)
class SalesColumnSpec:
    """Metadata row details for one Sales column."""

    column_name: str
    data_type: str
    key_type: str | None = None
    related_table: str | None = None
    related_column: str | None = None
    nullable: str = "No"
    generation_type: str = "category"
    allowed_values: tuple[str, ...] = ()
    min_value: Any | None = None
    max_value: Any | None = None
    formula: str | None = None


@dataclass(frozen=True)
class SalesTableSpec:
    """Metadata fixture details for one Sales table."""

    table_name: str
    table_role: str
    process_order: int
    target_rows: int
    columns: tuple[SalesColumnSpec, ...]


def _pk(name: str) -> SalesColumnSpec:
    return SalesColumnSpec(name, "int", key_type="PK", generation_type="sequence_id")


def _fk(name: str, related_table: str, related_column: str) -> SalesColumnSpec:
    return SalesColumnSpec(name, "int", key_type="FK", related_table=related_table, related_column=related_column, generation_type="foreign_key")


def _varchar(name: str, generation_type: str = "category", nullable: str = "No") -> SalesColumnSpec:
    return SalesColumnSpec(name, "varchar", nullable=nullable, generation_type=generation_type)


def _status(name: str, values: tuple[str, ...]) -> SalesColumnSpec:
    return SalesColumnSpec(name, "varchar", generation_type="status", allowed_values=values)


def _decimal(name: str, min_value: float | int | None = None, max_value: float | int | None = None) -> SalesColumnSpec:
    return SalesColumnSpec(name, "decimal", generation_type="decimal_range", min_value=min_value, max_value=max_value)


def _date(name: str) -> SalesColumnSpec:
    return SalesColumnSpec(name, "date", generation_type="date_range")


def _bit(name: str) -> SalesColumnSpec:
    return SalesColumnSpec(name, "bit", generation_type="integer_range", allowed_values=("0", "1"), min_value=0, max_value=1)


def _calculated(name: str, formula: str) -> SalesColumnSpec:
    return SalesColumnSpec(name, "decimal", generation_type="calculated", formula=formula)


SALES_V1_TABLE_SPECS: tuple[SalesTableSpec, ...] = (
    SalesTableSpec(
        "CustomerMaster",
        "customer_master",
        100,
        100,
        (
            _pk("CustomerID"),
            _varchar("CustomerCode"),
            _varchar("CustomerName", "faker_company"),
            _status("CustomerType", ("Grocery Retailer", "Distributor", "Foodservice", "Convenience Store", "E-commerce", "Regional Wholesaler")),
            _varchar("Industry"),
            _varchar("Country"),
            _varchar("Region"),
            _decimal("CreditLimit", 1000, 1000000),
            _status("PaymentTerms", ("Net15", "Net30", "Net45", "DueOnReceipt")),
            _status("CustomerStatus", ("Active", "Inactive", "Hold")),
        ),
    ),
    SalesTableSpec(
        "CustomerLocation",
        "customer_location",
        110,
        150,
        (
            _pk("CustomerLocationID"),
            _fk("CustomerID", "CustomerMaster", "CustomerID"),
            _status("LocationType", ("Billing", "Shipping", "Both")),
            _varchar("AddressLine1"),
            _varchar("City"),
            _varchar("State"),
            _varchar("Country"),
            _varchar("PostalCode"),
            _bit("IsDefault"),
        ),
    ),
    SalesTableSpec(
        "SalesChannel",
        "sales_channel",
        120,
        6,
        (
            _pk("SalesChannelID"),
            _varchar("ChannelCode"),
            _varchar("ChannelName"),
            _status("ChannelType", ("Grocery Retailer", "Distributor", "Foodservice", "Convenience Store", "E-commerce", "Regional Wholesaler")),
            _status("ChannelStatus", ("Active", "Inactive")),
        ),
    ),
    SalesTableSpec(
        "SalesPriceListHeader",
        "sales_price_list_header",
        130,
        2,
        (
            _pk("PriceListID"),
            _varchar("PriceListName"),
            _varchar("CurrencyCode"),
            _date("EffectiveFromDate"),
            _date("EffectiveToDate"),
            _status("PriceListStatus", ("Active", "Expired")),
        ),
    ),
    SalesTableSpec(
        "SalesPriceListLine",
        "sales_price_list_line",
        140,
        60,
        (
            _pk("PriceListLineID"),
            _fk("PriceListID", "SalesPriceListHeader", "PriceListID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _decimal("UnitPrice", 1, 10000),
            _decimal("MinimumOrderQuantity", 1, 1000),
            _decimal("DiscountPct", 0, 50),
            _status("LineStatus", ("Active", "Inactive")),
        ),
    ),
    SalesTableSpec(
        "SalesOrderHdr",
        "sales_order_header",
        200,
        500,
        (
            _pk("SalesOrderID"),
            _varchar("SalesOrderNumber"),
            _fk("CustomerID", "CustomerMaster", "CustomerID"),
            _fk("BillToLocationID", "CustomerLocation", "CustomerLocationID"),
            _fk("ShipToLocationID", "CustomerLocation", "CustomerLocationID"),
            _fk("SalesChannelID", "SalesChannel", "SalesChannelID"),
            _date("OrderDate"),
            _date("RequestedShipDate"),
            _date("PromisedShipDate"),
            _varchar("CurrencyCode"),
            _status("OrderStatus", ("Closed", "PartiallyShipped", "Backordered", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "SalesOrderLine",
        "sales_order_line",
        210,
        1000,
        (
            _pk("SalesOrderLineID"),
            _fk("SalesOrderID", "SalesOrderHdr", "SalesOrderID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _fk("PlantID", "Plant", "PlantID"),
            _fk("WarehouseID", "Warehouse", "WarehouseID"),
            _decimal("OrderedQuantity", 1, 10000),
            _decimal("ReservedQuantity", 0, 10000),
            _decimal("ShippedQuantity", 0, 10000),
            _decimal("BackorderQuantity", 0, 10000),
            _varchar("UOM"),
            _decimal("UnitPrice", 1, 10000),
            _decimal("DiscountPct", 0, 50),
            _calculated("LineAmount", "OrderedQuantity * UnitPrice"),
            _calculated("DiscountAmount", "LineAmount * DiscountPct / 100"),
            _calculated("NetLineAmount", "LineAmount - DiscountAmount"),
            _status("LineStatus", ("Closed", "PartiallyShipped", "Backordered", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "SalesInventoryReservation",
        "sales_inventory_reservation",
        220,
        1000,
        (
            _pk("ReservationID"),
            _fk("SalesOrderLineID", "SalesOrderLine", "SalesOrderLineID"),
            _fk("FinishedGoodsInventoryID", "FinishedGoodsInventory", "FinishedGoodsInventoryID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _fk("PlantID", "Plant", "PlantID"),
            _fk("WarehouseID", "Warehouse", "WarehouseID"),
            _date("ReservationDate"),
            _decimal("ReservedQuantity", 0, 10000),
            _decimal("ReleasedQuantity", 0, 10000),
            _status("ReservationStatus", ("Reserved", "Released", "Consumed")),
        ),
    ),
    SalesTableSpec(
        "SalesPickListHeader",
        "sales_pick_list_header",
        230,
        500,
        (
            _pk("PickListID"),
            _fk("SalesOrderID", "SalesOrderHdr", "SalesOrderID"),
            _fk("WarehouseID", "Warehouse", "WarehouseID"),
            _date("PickDate"),
            _status("PickStatus", ("Created", "Picked", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "SalesPickListLine",
        "sales_pick_list_line",
        240,
        1000,
        (
            _pk("PickListLineID"),
            _fk("PickListID", "SalesPickListHeader", "PickListID"),
            _fk("SalesOrderLineID", "SalesOrderLine", "SalesOrderLineID"),
            _fk("ReservationID", "SalesInventoryReservation", "ReservationID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _decimal("PickedQuantity", 0, 10000),
            _varchar("UOM"),
            _status("PickLineStatus", ("Picked", "ShortPicked", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "SalesShipmentHeader",
        "sales_shipment_header",
        250,
        500,
        (
            _pk("ShipmentID"),
            _varchar("ShipmentNumber"),
            _fk("SalesOrderID", "SalesOrderHdr", "SalesOrderID"),
            _fk("CustomerID", "CustomerMaster", "CustomerID"),
            _fk("ShipToLocationID", "CustomerLocation", "CustomerLocationID"),
            _fk("WarehouseID", "Warehouse", "WarehouseID"),
            _date("ShipmentDate"),
            _varchar("CarrierName"),
            _varchar("TrackingNumber"),
            _status("ShipmentStatus", ("Shipped", "Delivered", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "SalesShipmentLine",
        "sales_shipment_line",
        260,
        1000,
        (
            _pk("ShipmentLineID"),
            _fk("ShipmentID", "SalesShipmentHeader", "ShipmentID"),
            _fk("SalesOrderLineID", "SalesOrderLine", "SalesOrderLineID"),
            _fk("PickListLineID", "SalesPickListLine", "PickListLineID"),
            _fk("FinishedGoodsInventoryID", "FinishedGoodsInventory", "FinishedGoodsInventoryID"),
            _fk("FinishedGoodsReceiptID", "FinishedGoodsReceipt", "FinishedGoodsReceiptID"),
            _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _decimal("ShippedQuantity", 0, 10000),
            _varchar("UOM"),
            _decimal("UnitCost", 0, 10000),
            _calculated("COGSValue", "ShippedQuantity * UnitCost"),
            _status("ShipmentLineStatus", ("Shipped", "Delivered")),
        ),
    ),
    SalesTableSpec(
        "SalesInvoiceHeader",
        "sales_invoice_header",
        270,
        500,
        (
            _pk("InvoiceID"),
            _varchar("InvoiceNumber"),
            _fk("SalesOrderID", "SalesOrderHdr", "SalesOrderID"),
            _fk("ShipmentID", "SalesShipmentHeader", "ShipmentID"),
            _fk("CustomerID", "CustomerMaster", "CustomerID"),
            _date("InvoiceDate"),
            _date("DueDate"),
            _varchar("CurrencyCode"),
            _decimal("SubtotalAmount", 0, 10000000),
            _decimal("DiscountAmount", 0, 1000000),
            _decimal("TaxAmount", 0, 1000000),
            _decimal("FreightAmount", 0, 1000000),
            _calculated("TotalInvoiceAmount", "SubtotalAmount - DiscountAmount + TaxAmount + FreightAmount"),
            _status("InvoiceStatus", ("Open", "PartiallyPaid", "Paid", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "SalesInvoiceLine",
        "sales_invoice_line",
        280,
        1000,
        (
            _pk("InvoiceLineID"),
            _fk("InvoiceID", "SalesInvoiceHeader", "InvoiceID"),
            _fk("ShipmentLineID", "SalesShipmentLine", "ShipmentLineID"),
            _fk("SalesOrderLineID", "SalesOrderLine", "SalesOrderLineID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _decimal("InvoiceQuantity", 0, 10000),
            _decimal("UnitPrice", 1, 10000),
            _decimal("DiscountAmount", 0, 1000000),
            _decimal("TaxAmount", 0, 1000000),
            _calculated("NetLineAmount", "InvoiceQuantity * UnitPrice - DiscountAmount"),
            _calculated("COGSValue", "InvoiceQuantity * UnitCost"),
            _calculated("GrossMarginAmount", "NetLineAmount - COGSValue"),
            _calculated("GrossMarginPct", "GrossMarginAmount / NetLineAmount * 100"),
            _status("LineStatus", ("Closed", "Cancelled")),
        ),
    ),
    SalesTableSpec(
        "CustomerPaymentReceipt",
        "customer_payment_receipt",
        290,
        500,
        (
            _pk("PaymentReceiptID"),
            _fk("InvoiceID", "SalesInvoiceHeader", "InvoiceID"),
            _fk("CustomerID", "CustomerMaster", "CustomerID"),
            _date("PaymentDate"),
            _status("PaymentMethod", ("ACH", "Card", "Wire", "Check")),
            _decimal("PaidAmount", 0, 10000000),
            _varchar("CurrencyCode"),
            _status("PaymentStatus", ("Received", "Partial", "Failed")),
        ),
    ),
    SalesTableSpec(
        "SalesReturnHeader",
        "sales_return_header",
        300,
        25,
        (
            _pk("SalesReturnID"),
            _varchar("ReturnNumber"),
            _fk("CustomerID", "CustomerMaster", "CustomerID"),
            _fk("SalesOrderID", "SalesOrderHdr", "SalesOrderID"),
            _fk("ShipmentID", "SalesShipmentHeader", "ShipmentID"),
            _date("ReturnDate"),
            _varchar("ReturnReason"),
            _status("ReturnStatus", ("Requested", "Approved", "Received", "Rejected")),
        ),
    ),
    SalesTableSpec(
        "SalesReturnLine",
        "sales_return_line",
        310,
        50,
        (
            _pk("SalesReturnLineID"),
            _fk("SalesReturnID", "SalesReturnHeader", "SalesReturnID"),
            _fk("ShipmentLineID", "SalesShipmentLine", "ShipmentLineID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _decimal("ReturnedQuantity", 0, 10000),
            _decimal("RestockedQuantity", 0, 10000),
            _decimal("ScrappedQuantity", 0, 10000),
            _decimal("ReturnUnitValue", 0, 10000),
            _status("ReturnLineStatus", ("Received", "Restocked", "Scrapped")),
        ),
    ),
    SalesTableSpec(
        "SalesShipmentTraceability",
        "sales_shipment_traceability",
        320,
        1000,
        (
            _pk("SalesTraceabilityID"),
            _fk("ShipmentLineID", "SalesShipmentLine", "ShipmentLineID"),
            _fk("FinishedGoodsReceiptID", "FinishedGoodsReceipt", "FinishedGoodsReceiptID"),
            _fk("ProductionBatchID", "ProductionBatch", "ProductionBatchID"),
            _fk("ProductionGenealogyID", "ProductionGenealogy", "ProductionGenealogyID"),
            _fk("MaterialIssueLineID", "MaterialIssueLine", "MaterialIssueLineID"),
            _fk("InventoryReceiptDetailID", "InventoryReceiptDetail", "InventoryReceiptDetailID"),
            _fk("SupplierID", "SupplierMaster", "SupplierID"),
            _fk("ComponentID", "ComponentMaster", "ComponentID"),
            _fk("ProductID", "ProductMaster", "ProductID"),
            _decimal("ShippedQuantity", 0, 10000),
            _decimal("AllocatedConsumedQuantity", 0, 10000),
            _status("TraceabilityStatus", ("Traced",)),
        ),
    ),
)


def build_sales_v1_metadata_dataframe() -> pd.DataFrame:
    """Return Sales v1 metadata rows in the repository metadata format."""

    rows: list[dict[str, Any]] = []
    for table in SALES_V1_TABLE_SPECS:
        role_definition = SALES_V1_ROLE_CATALOG[table.table_role]
        for column in table.columns:
            rows.append(
                {
                    "TableName": table.table_name,
                    "ProcessOrder": table.process_order,
                    "Area": role_definition.expected_area,
                    "TableRole": table.table_role,
                    "TargetRows": table.target_rows,
                    "ColumnName": column.column_name,
                    "DataType": column.data_type,
                    "KeyType": column.key_type,
                    "RelatedTable": column.related_table,
                    "RelatedColumn": column.related_column,
                    "Nullable": column.nullable,
                    "GenerationType": column.generation_type,
                    "AllowedValues": ", ".join(column.allowed_values),
                    "MinValue": column.min_value,
                    "MaxValue": column.max_value,
                    "Formula": column.formula,
                }
            )
    return pd.DataFrame(rows, columns=REQUIRED_METADATA_COLUMNS)


def write_sales_v1_metadata_xlsx(path: str | Path) -> Path:
    """Write the Sales v1 metadata fixture to an XLSX file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        build_sales_v1_metadata_dataframe().to_excel(writer, sheet_name="Metadata", index=False)
    return output_path
