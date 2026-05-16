"""Procurement table role catalogs for metadata validation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcurementRoleDefinition:
    """Expected metadata characteristics for a supported procurement role."""

    role_name: str
    expected_area: str
    is_master_table: bool
    expected_process_stage: str
    required_column_names: tuple[str, ...] = field(default_factory=tuple)
    recommended_column_names: tuple[str, ...] = field(default_factory=tuple)
    expected_parent_roles: tuple[str, ...] = field(default_factory=tuple)


PROCUREMENT_V2_ROLE_CATALOG: dict[str, ProcurementRoleDefinition] = {
    "supplier_master": ProcurementRoleDefinition(
        role_name="supplier_master",
        expected_area="Master",
        is_master_table=True,
        expected_process_stage="Supplier Master",
        recommended_column_names=(
            "SupplierID",
            "SupplierName",
            "SupplierCategory",
            "SupplierCity",
            "SupplierState",
            "SupplierCountry",
            "Status",
        ),
    ),
    "supplier_component": ProcurementRoleDefinition(
        role_name="supplier_component",
        expected_area="Master",
        is_master_table=True,
        expected_process_stage="Supplier Component",
        recommended_column_names=(
            "SupplierComponentID",
            "SupplierID",
            "ComponentID",
            "ContractPrice",
            "CurrencyCode",
            "LeadTimeDays",
            "Status",
        ),
        expected_parent_roles=("supplier_master", "component_master"),
    ),
    "component_master": ProcurementRoleDefinition(
        role_name="component_master",
        expected_area="Master",
        is_master_table=True,
        expected_process_stage="Component Master",
        recommended_column_names=(
            "ComponentID",
            "ComponentName",
            "ComponentCategory",
            "UOM",
            "StandardCost",
            "CurrencyCode",
            "Status",
        ),
    ),
    "plant_dimension": ProcurementRoleDefinition(
        role_name="plant_dimension",
        expected_area="Master",
        is_master_table=True,
        expected_process_stage="Plant Master",
        recommended_column_names=(
            "PlantID",
            "PlantName",
            "PlantCity",
            "PlantState",
            "PlantCountry",
            "PlantZipCode",
            "Status",
        ),
    ),
    "warehouse_dimension": ProcurementRoleDefinition(
        role_name="warehouse_dimension",
        expected_area="Master",
        is_master_table=True,
        expected_process_stage="Warehouse Master",
        recommended_column_names=(
            "WarehouseID",
            "PlantID",
            "WarehouseName",
            "WarehouseType",
            "WarehouseLocation",
            "WarehouseCity",
            "WarehouseState",
            "WarehouseCountry",
            "WarehouseZipCode",
            "Status",
        ),
        expected_parent_roles=("plant_dimension",),
    ),
    "purchase_requisition": ProcurementRoleDefinition(
        role_name="purchase_requisition",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="Purchase Requisition",
        recommended_column_names=("RequisitionID", "PlantID", "RequisitionDate", "RequiredDate", "Status"),
        expected_parent_roles=("plant_dimension",),
    ),
    "purchase_req_line": ProcurementRoleDefinition(
        role_name="purchase_req_line",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="Purchase Requisition",
        recommended_column_names=("RequisitionLineID", "RequisitionID", "ComponentID", "RequestedQuantity", "LineStatus"),
        expected_parent_roles=("purchase_requisition", "component_master"),
    ),
    "rfq_header": ProcurementRoleDefinition(
        role_name="rfq_header",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="RFQ",
        recommended_column_names=("RFQID", "RequisitionID", "RFQDate", "RFQDueDate", "RFQStatus"),
        expected_parent_roles=("purchase_requisition",),
    ),
    "rfq_line": ProcurementRoleDefinition(
        role_name="rfq_line",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="RFQ",
        recommended_column_names=("RFQLineID", "RFQID", "RequisitionLineID", "ComponentID", "RFQQuantity", "LineStatus"),
        expected_parent_roles=("rfq_header", "purchase_req_line", "component_master"),
    ),
    "supplier_quotation": ProcurementRoleDefinition(
        role_name="supplier_quotation",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="Supplier Quotation",
        recommended_column_names=(
            "QuotationID",
            "RFQID",
            "SupplierID",
            "QuotationDate",
            "ValidUntilDate",
            "QuotationStatus",
            "CurrencyCode",
        ),
        expected_parent_roles=("rfq_header", "supplier_master"),
    ),
    "supplier_quotation_line": ProcurementRoleDefinition(
        role_name="supplier_quotation_line",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="Supplier Quotation",
        recommended_column_names=(
            "QuotationLineID",
            "QuotationID",
            "RFQLineID",
            "ComponentID",
            "QuotedQuantity",
            "QuotedUnitPrice",
            "QuotedLineAmount",
            "AwardedFlag",
            "LineStatus",
        ),
        expected_parent_roles=("supplier_quotation", "rfq_line", "component_master"),
    ),
    "purchase_order_header": ProcurementRoleDefinition(
        role_name="purchase_order_header",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="Purchase Order",
        recommended_column_names=(
            "PurchaseOrderID",
            "SupplierID",
            "PlantID",
            "QuotationID",
            "OrderDate",
            "ExpectedDeliveryDate",
            "POStatus",
            "TotalAmount",
            "CurrencyCode",
        ),
        expected_parent_roles=("supplier_master", "plant_dimension", "supplier_quotation"),
    ),
    "purchase_order_line": ProcurementRoleDefinition(
        role_name="purchase_order_line",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="Purchase Order",
        recommended_column_names=(
            "PurchaseOrderLineID",
            "PurchaseOrderID",
            "QuotationLineID",
            "ComponentID",
            "OrderedQuantity",
            "UnitPrice",
            "LineAmount",
            "LineStatus",
        ),
        expected_parent_roles=("purchase_order_header", "supplier_quotation_line", "component_master"),
    ),
    "po_schedule": ProcurementRoleDefinition(
        role_name="po_schedule",
        expected_area="Procurement",
        is_master_table=False,
        expected_process_stage="PO Schedule",
        recommended_column_names=("POScheduleID", "PurchaseOrderLineID", "ScheduledDeliveryDate", "ScheduledQuantity", "ScheduleStatus"),
        expected_parent_roles=("purchase_order_line",),
    ),
    "shipment_header": ProcurementRoleDefinition(
        role_name="shipment_header",
        expected_area="Logistics",
        is_master_table=False,
        expected_process_stage="Shipment",
        recommended_column_names=("ShipmentID", "PurchaseOrderID", "SupplierID", "ShipmentDate", "CarrierName", "TrackingNumber", "ShipmentStatus"),
        expected_parent_roles=("purchase_order_header", "supplier_master"),
    ),
    "shipment_line": ProcurementRoleDefinition(
        role_name="shipment_line",
        expected_area="Logistics",
        is_master_table=False,
        expected_process_stage="Shipment",
        recommended_column_names=("ShipmentLineID", "ShipmentID", "POScheduleID", "PurchaseOrderLineID", "ComponentID", "ShippedQuantity"),
        expected_parent_roles=("shipment_header", "po_schedule", "purchase_order_line", "component_master"),
    ),
    "goods_receipt_header": ProcurementRoleDefinition(
        role_name="goods_receipt_header",
        expected_area="Logistics",
        is_master_table=False,
        expected_process_stage="Goods Receipt",
        recommended_column_names=("GoodsReceiptID", "ShipmentID", "PlantID", "WarehouseID", "ReceiptDate", "ReceiptStatus"),
        expected_parent_roles=("shipment_header", "plant_dimension", "warehouse_dimension"),
    ),
    "goods_receipt_line": ProcurementRoleDefinition(
        role_name="goods_receipt_line",
        expected_area="Logistics",
        is_master_table=False,
        expected_process_stage="Goods Receipt",
        recommended_column_names=(
            "GoodsReceiptLineID",
            "GoodsReceiptID",
            "ShipmentLineID",
            "PurchaseOrderLineID",
            "ComponentID",
            "ShippedQuantity",
            "ReceivedQuantity",
            "DamagedQuantity",
            "ShortQuantity",
        ),
        expected_parent_roles=("goods_receipt_header", "shipment_line", "purchase_order_line", "component_master"),
    ),
    "incoming_inspection": ProcurementRoleDefinition(
        role_name="incoming_inspection",
        expected_area="Quality",
        is_master_table=False,
        expected_process_stage="Incoming Inspection",
        recommended_column_names=("InspectionID", "GoodsReceiptLineID", "InspectionDate", "InspectorName", "InspectionStatus"),
        expected_parent_roles=("goods_receipt_line",),
    ),
    "inspection_result": ProcurementRoleDefinition(
        role_name="inspection_result",
        expected_area="Quality",
        is_master_table=False,
        expected_process_stage="Inspection Result",
        recommended_column_names=(
            "InspectionResultID",
            "InspectionID",
            "TestName",
            "InspectedQuantity",
            "AcceptedQuantity",
            "RejectedQuantity",
            "RejectionRatePct",
            "RejectionReason",
            "ResultStatus",
        ),
        expected_parent_roles=("incoming_inspection",),
    ),
    "inventory_receipt_detail": ProcurementRoleDefinition(
        role_name="inventory_receipt_detail",
        expected_area="Inventory",
        is_master_table=False,
        expected_process_stage="Inventory Receipt Detail",
        recommended_column_names=(
            "InventoryReceiptDetailID",
            "InspectionResultID",
            "GoodsReceiptLineID",
            "PurchaseOrderLineID",
            "PurchaseOrderID",
            "SupplierID",
            "ComponentID",
            "PlantID",
            "WarehouseID",
            "POOrderDate",
            "ExpectedDeliveryDate",
            "ActualDeliveryDate",
            "StockPostedDate",
            "OrderedQuantity",
            "ShippedQuantity",
            "ReceivedQuantity",
            "InspectedQuantity",
            "AcceptedQuantity",
            "RejectedQuantity",
            "OrderedUnitPrice",
            "DeliveredUnitPrice",
            "PriceDifference",
            "PriceDifferencePct",
            "OrderedValue",
            "DeliveredValue",
            "AcceptedStockValue",
            "OrderYear",
            "DeliveryYear",
            "CrossYearDeliveryFlag",
            "DeliveryDelayDays",
            "DeliveryStatus",
            "PriceVarianceStatus",
            "InventoryReceiptStatus",
        ),
        expected_parent_roles=(
            "inspection_result",
            "goods_receipt_line",
            "purchase_order_line",
            "purchase_order_header",
            "supplier_master",
            "component_master",
            "plant_dimension",
            "warehouse_dimension",
        ),
    ),
    "inventory_transaction": ProcurementRoleDefinition(
        role_name="inventory_transaction",
        expected_area="Inventory",
        is_master_table=False,
        expected_process_stage="Inventory Transaction",
        recommended_column_names=(
            "InventoryTransactionID",
            "InspectionResultID",
            "GoodsReceiptLineID",
            "PurchaseOrderLineID",
            "SupplierID",
            "ComponentID",
            "PlantID",
            "WarehouseID",
            "TransactionDate",
            "TransactionType",
            "TransactionQuantity",
            "UnitPrice",
            "InventoryValue",
            "ReferenceDocument",
            "InventoryStatus",
        ),
        expected_parent_roles=(
            "inspection_result",
            "goods_receipt_line",
            "purchase_order_line",
            "supplier_master",
            "component_master",
            "plant_dimension",
            "warehouse_dimension",
        ),
    ),
    "inventory": ProcurementRoleDefinition(
        role_name="inventory",
        expected_area="Inventory",
        is_master_table=False,
        expected_process_stage="Inventory Balance",
        recommended_column_names=(
            "InventoryID",
            "ComponentID",
            "PlantID",
            "WarehouseID",
            "OnHandQuantity",
            "ReservedQuantity",
            "AvailableQuantity",
            "OnHandValue",
            "AvailableValue",
            "LastTransactionDate",
            "LastUpdatedDate",
            "InventoryStatus",
        ),
        expected_parent_roles=("component_master", "plant_dimension", "warehouse_dimension", "inventory_transaction"),
    ),
    "supplier_invoice": ProcurementRoleDefinition(
        role_name="supplier_invoice",
        expected_area="Finance",
        is_master_table=False,
        expected_process_stage="Supplier Invoice",
        recommended_column_names=(
            "SupplierInvoiceID",
            "PurchaseOrderID",
            "SupplierID",
            "GoodsReceiptID",
            "InvoiceDate",
            "DueDate",
            "InvoiceStatus",
            "InvoiceAmount",
            "TaxAmount",
            "FreightAmount",
            "TotalInvoiceAmount",
            "CurrencyCode",
        ),
        expected_parent_roles=("purchase_order_header", "supplier_master", "goods_receipt_header"),
    ),
    "payment_transaction": ProcurementRoleDefinition(
        role_name="payment_transaction",
        expected_area="Finance",
        is_master_table=False,
        expected_process_stage="Payment Transaction",
        recommended_column_names=(
            "PaymentTransactionID",
            "SupplierInvoiceID",
            "SupplierID",
            "PaymentDate",
            "PaymentAmount",
            "PaymentMethod",
            "PaymentStatus",
            "CurrencyCode",
        ),
        expected_parent_roles=("supplier_invoice", "supplier_master"),
    ),
}

PROCUREMENT_V1_UNSUPPORTED_MESSAGE = "Procurement V1 is deprecated and no longer supported. Use Procurement V2."

# Generic aliases are retained for existing imports, but now point to the active Procurement v2 model.
PROCUREMENT_ROLE_CATALOG = PROCUREMENT_V2_ROLE_CATALOG

PROCUREMENT_ROLE_CATALOGS = {
    "v2": PROCUREMENT_V2_ROLE_CATALOG,
}

SUPPORTED_PROCUREMENT_ROLES = tuple(PROCUREMENT_V2_ROLE_CATALOG.keys())
SUPPORTED_PROCUREMENT_V2_ROLES = tuple(PROCUREMENT_V2_ROLE_CATALOG.keys())


def get_procurement_role_catalog(model_version: str = "v2") -> dict[str, ProcurementRoleDefinition]:
    """Return the role catalog for a supported procurement model version."""

    if model_version != "v2":
        raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
    try:
        return PROCUREMENT_ROLE_CATALOGS[model_version]
    except KeyError as exc:
        raise ValueError("model_version must be 'v2'.") from exc


def get_procurement_role(role_name: str, model_version: str = "v2") -> ProcurementRoleDefinition | None:
    """Return a role definition if the role is supported."""

    return get_procurement_role_catalog(model_version).get(role_name)
