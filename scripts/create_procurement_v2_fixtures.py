"""Create Procurement v2 metadata, ERD, and scenario fixtures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "input"

HEADERS = [
    "TableName",
    "ProcessOrder",
    "Process",
    "Area",
    "TableRole",
    "TargetRows",
    "ColumnName",
    "DataType",
    "KeyType",
    "RelatedTable",
    "RelatedColumn",
    "Nullable",
    "AllowedValues",
    "MinValue",
    "MaxValue",
    "Purpose",
    "GenerationType",
    "Formula",
]

TABLES = [
    {
        "table": "SupplierMaster",
        "order": 1,
        "process": "Supplier Master",
        "area": "Master",
        "role": "supplier_master",
        "rows": 80,
        "columns": [
            ("SupplierID", "int", "PK", None, None, "No", "", "", "", "Supplier primary key", "sequence_id", ""),
            ("SupplierCode", "varchar(30)", "", None, None, "No", "", "", "", "Supplier code", "category", ""),
            ("SupplierName", "varchar(200)", "", None, None, "No", "", "", "", "Supplier name", "vendor_name", ""),
            ("SupplierCategory", "varchar(80)", "", None, None, "No", "Battery,Electrical,Mechanical,Packaging,Maintenance,Logistics,Electronics", "", "", "Supplier category", "category", ""),
            ("SupplierCity", "varchar(100)", "", None, None, "No", "Detroit,Austin,Fremont,Phoenix,Nashville,Columbus,Reno,Greenville,Chicago,Atlanta", "", "", "Supplier city", "category", ""),
            ("SupplierState", "varchar(100)", "", None, None, "No", "Michigan,Texas,California,Arizona,Tennessee,Ohio,Nevada,South Carolina,Illinois,Georgia", "", "", "Supplier state", "category", ""),
            ("SupplierCountry", "varchar(50)", "", None, None, "No", "USA", "", "", "Supplier country", "category", ""),
            ("SupplierZipCode", "varchar(20)", "", None, None, "No", "", "", "", "Supplier zip code", "category", ""),
            ("PaymentTerms", "varchar(50)", "", None, None, "No", "Net 30,Net 45,Net 60,Advance,2/10 Net 30", "", "", "Supplier payment terms", "category", ""),
            ("LeadTimeDays", "int", "", None, None, "No", "", 3, 60, "Supplier lead time", "integer_range", ""),
            ("QualityRating", "decimal(5,2)", "", None, None, "No", "", 70, 100, "Supplier quality rating", "decimal_range", ""),
            ("Status", "varchar(40)", "", None, None, "No", "Active,Inactive,OnHold", "", "", "Supplier status", "status", ""),
        ],
    },
    {
        "table": "ComponentMaster",
        "order": 2,
        "process": "Component Master",
        "area": "Master",
        "role": "component_master",
        "rows": 300,
        "columns": [
            ("ComponentID", "int", "PK", None, None, "No", "", "", "", "Component primary key", "sequence_id", ""),
            ("ComponentCode", "varchar(40)", "", None, None, "No", "", "", "", "Component code", "category", ""),
            ("ComponentName", "varchar(200)", "", None, None, "No", "", "", "", "Component name", "material_name", ""),
            ("ComponentCategory", "varchar(100)", "", None, None, "No", "Battery,Electrical,Mechanical,Packaging,Maintenance,Safety,Electronics", "", "", "Component category", "category", ""),
            ("UOM", "varchar(30)", "", None, None, "No", "Each,Box,Kg,Meter,Roll,Liter,Set", "", "", "Unit of measure", "category", ""),
            ("StandardCost", "decimal(18,2)", "", None, None, "No", "", 1, 5000, "Standard cost in USD", "decimal_range", ""),
            ("CurrencyCode", "varchar(10)", "", None, None, "No", "USD", "", "", "Currency code", "category", ""),
            ("SafetyCriticalFlag", "bit", "", None, None, "No", "0,1", "", "", "Safety critical flag", "category", ""),
            ("Status", "varchar(40)", "", None, None, "No", "Active,Inactive,Obsolete", "", "", "Component status", "status", ""),
        ],
    },
    {
        "table": "Plant",
        "order": 3,
        "process": "Plant Master",
        "area": "Master",
        "role": "plant_dimension",
        "rows": 3,
        "columns": [
            ("PlantID", "int", "PK", None, None, "No", "", "", "", "Plant primary key", "sequence_id", ""),
            ("PlantCode", "varchar(30)", "", None, None, "No", "", "", "", "Plant code", "category", ""),
            ("PlantName", "varchar(150)", "", None, None, "No", "", "", "", "Plant name", "plant_name", ""),
            ("PlantCity", "varchar(100)", "", None, None, "No", "Detroit,Austin,Fremont,Phoenix,Nashville,Columbus,Reno,Greenville", "", "", "Plant city", "category", ""),
            ("PlantState", "varchar(100)", "", None, None, "No", "Michigan,Texas,California,Arizona,Tennessee,Ohio,Nevada,South Carolina", "", "", "Plant state", "category", ""),
            ("PlantCountry", "varchar(50)", "", None, None, "No", "USA", "", "", "Plant country", "category", ""),
            ("PlantZipCode", "varchar(20)", "", None, None, "No", "", "", "", "Plant zip code", "category", ""),
            ("Status", "varchar(40)", "", None, None, "No", "Active,Inactive", "", "", "Plant status", "status", ""),
        ],
    },
    {
        "table": "Warehouse",
        "order": 4,
        "process": "Warehouse Master",
        "area": "Master",
        "role": "warehouse_dimension",
        "rows": 9,
        "columns": [
            ("WarehouseID", "int", "PK", None, None, "No", "", "", "", "Warehouse primary key", "sequence_id", ""),
            ("PlantID", "int", "FK", "Plant", "PlantID", "No", "", "", "", "Plant FK", "foreign_key", ""),
            ("WarehouseCode", "varchar(30)", "", None, None, "No", "", "", "", "Warehouse code", "category", ""),
            ("WarehouseName", "varchar(150)", "", None, None, "No", "", "", "", "Warehouse name", "warehouse_name", ""),
            ("WarehouseType", "varchar(80)", "", None, None, "No", "Raw Material,Quality Hold,Rejected Material,Maintenance Spares,Inbound,Packaging,Finished Goods Staging", "", "", "Warehouse type", "category", ""),
            ("WarehouseLocation", "varchar(200)", "", None, None, "No", "", "", "", "Warehouse location", "category", ""),
            ("WarehouseCity", "varchar(100)", "", None, None, "No", "Detroit,Austin,Fremont,Phoenix,Nashville,Columbus,Reno,Greenville", "", "", "Warehouse city", "category", ""),
            ("WarehouseState", "varchar(100)", "", None, None, "No", "Michigan,Texas,California,Arizona,Tennessee,Ohio,Nevada,South Carolina", "", "", "Warehouse state", "category", ""),
            ("WarehouseCountry", "varchar(50)", "", None, None, "No", "USA", "", "", "Warehouse country", "category", ""),
            ("WarehouseZipCode", "varchar(20)", "", None, None, "No", "", "", "", "Warehouse zip code", "category", ""),
            ("Status", "varchar(40)", "", None, None, "No", "Active,Inactive,OnHold", "", "", "Warehouse status", "status", ""),
        ],
    },
    {
        "table": "SupplierComponent",
        "order": 5,
        "process": "Supplier Component",
        "area": "Master",
        "role": "supplier_component",
        "rows": 450,
        "columns": [
            ("SupplierComponentID", "int", "PK", None, None, "No", "", "", "", "Supplier-component key", "sequence_id", ""),
            ("SupplierID", "int", "FK", "SupplierMaster", "SupplierID", "No", "", "", "", "Supplier FK", "foreign_key", ""),
            ("ComponentID", "int", "FK", "ComponentMaster", "ComponentID", "No", "", "", "", "Component FK", "foreign_key", ""),
            ("PreferredSupplierFlag", "bit", "", None, None, "No", "0,1", "", "", "Preferred supplier flag", "category", ""),
            ("MinOrderQuantity", "decimal(18,2)", "", None, None, "No", "", 1, 1000, "Minimum order quantity", "decimal_range", ""),
            ("LeadTimeDays", "int", "", None, None, "No", "", 3, 60, "Supplier component lead time", "integer_range", ""),
            ("ContractPrice", "decimal(18,2)", "", None, None, "No", "", 1, 5000, "Contract price in USD", "decimal_range", ""),
            ("CurrencyCode", "varchar(10)", "", None, None, "No", "USD", "", "", "Currency code", "category", ""),
            ("Status", "varchar(40)", "", None, None, "No", "Active,Inactive,Expired", "", "", "Supplier component status", "status", ""),
        ],
    },
]


def main() -> int:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _metadata_rows()
    _write_metadata(rows)
    _write_erd()
    _write_scenario()
    print(f"Created {INPUT_DIR / 'procurement_v2_metadata.xlsx'}")
    print(f"Metadata rows: {len(rows)}")
    print(f"Total target rows: {sum({row['TableName']: row['TargetRows'] for row in rows}.values())}")
    print(f"Created {INPUT_DIR / 'procurement_v2_erd.mmd'}")
    print(f"Created {INPUT_DIR / 'procurement_v2_business_scenario.txt'}")
    return 0


def _metadata_rows() -> list[dict]:
    rows = []
    for table in _all_tables():
        for column in table["columns"]:
            (
                column_name,
                data_type,
                key_type,
                related_table,
                related_column,
                nullable,
                allowed_values,
                min_value,
                max_value,
                purpose,
                generation_type,
                formula,
            ) = column
            rows.append(
                {
                    "TableName": table["table"],
                    "ProcessOrder": table["order"],
                    "Process": table["process"],
                    "Area": table["area"],
                    "TableRole": table["role"],
                    "TargetRows": table["rows"],
                    "ColumnName": column_name,
                    "DataType": data_type,
                    "KeyType": key_type,
                    "RelatedTable": related_table,
                    "RelatedColumn": related_column,
                    "Nullable": nullable,
                    "AllowedValues": allowed_values,
                    "MinValue": min_value,
                    "MaxValue": max_value,
                    "Purpose": purpose,
                    "GenerationType": generation_type,
                    "Formula": formula,
                }
            )
    return rows


def _all_tables() -> list[dict]:
    tables = list(TABLES)
    tables.extend(
        [
            _table("PurchaseRequisition", 10, "Purchase Requisition", "Procurement", "purchase_requisition", 2200, [
                _pk("RequisitionID"), _fk("PlantID", "Plant", "PlantID"), _date("RequisitionDate", "date_range", "2025-01-01", "2025-12-31"),
                _date("RequiredDate", "date_offset"), ("RequesterName", "varchar(120)", "", None, None, "No", "", "", "", "Requester name", "faker_person", ""),
                _cat("Department", "Production,Maintenance,Quality,Engineering,Warehouse,Procurement"), _cat("Priority", "Low,Medium,High,Urgent"),
                _status("Status", "Draft,Submitted,Approved,ConvertedToRFQ,Cancelled"),
            ]),
            _table("PurchaseReqLine", 11, "Purchase Requisition Line", "Procurement", "purchase_req_line", 6600, [
                _pk("RequisitionLineID"), _fk("RequisitionID", "PurchaseRequisition", "RequisitionID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _decimal("RequestedQuantity", 1, 1000), _date("RequiredDate", "date_offset"), _status("LineStatus", "Open,Approved,ConvertedToRFQ,Cancelled"),
            ]),
            _table("RFQHeader", 20, "RFQ", "Procurement", "rfq_header", 1900, [
                _pk("RFQID"), _fk("RequisitionID", "PurchaseRequisition", "RequisitionID"), _date("RFQDate", "date_offset"), _date("RFQDueDate", "date_offset"),
                ("BuyerName", "varchar(120)", "", None, None, "No", "", "", "", "Buyer name", "faker_person", ""), _status("RFQStatus", "Created,Sent,Closed,Cancelled"),
            ]),
            _table("RFQLine", 21, "RFQ Line", "Procurement", "rfq_line", 6200, [
                _pk("RFQLineID"), _fk("RFQID", "RFQHeader", "RFQID"), _fk("RequisitionLineID", "PurchaseReqLine", "RequisitionLineID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _decimal_named("RFQQuantity", 1, 1000), _date("RequiredDate", "date_offset"), _status("LineStatus", "Open,Quoted,Awarded,Closed"),
            ]),
            _table("SupplierQuotation", 30, "Supplier Quotation", "Procurement", "supplier_quotation", 3800, [
                _pk("QuotationID"), _fk("RFQID", "RFQHeader", "RFQID"), _fk("SupplierID", "SupplierMaster", "SupplierID"),
                _date("QuotationDate", "date_offset"), _date("ValidUntilDate", "date_offset"), _status("QuotationStatus", "Submitted,UnderReview,Awarded,Rejected,Expired"), _usd(),
            ]),
            _table("SupplierQuotationLn", 31, "Supplier Quotation Line", "Procurement", "supplier_quotation_line", 10500, [
                _pk("QuotationLineID"), _fk("QuotationID", "SupplierQuotation", "QuotationID"), _fk("RFQLineID", "RFQLine", "RFQLineID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _decimal_named("QuotedQuantity", 1, 1000), _decimal_named("QuotedUnitPrice", 1, 6000), _calc("QuotedLineAmount", "QuotedQuantity * QuotedUnitPrice"),
                ("LeadTimeDays", "int", "", None, None, "No", "", 3, 75, "Lead time days", "integer_range", ""), _cat("AwardedFlag", "0,1", "bit"), _status("LineStatus", "Quoted,Awarded,Rejected"),
            ]),
            _table("PurchaseOrderHdr", 40, "Purchase Order", "Procurement", "purchase_order_header", 1800, [
                _pk("PurchaseOrderID"), _fk("SupplierID", "SupplierMaster", "SupplierID"), _fk("PlantID", "Plant", "PlantID"), _fk("QuotationID", "SupplierQuotation", "QuotationID"),
                _date("OrderDate", "date_offset"), _date("ExpectedDeliveryDate", "date_offset"), _status("POStatus", "Created,Approved,Sent,PartiallyReceived,Closed,Cancelled"),
                _calc("TotalAmount", "SUM(PurchaseOrderLine.LineAmount)"), _usd(),
            ]),
            _table("PurchaseOrderLine", 41, "Purchase Order Line", "Procurement", "purchase_order_line", 5400, [
                _pk("PurchaseOrderLineID"), _fk("PurchaseOrderID", "PurchaseOrderHdr", "PurchaseOrderID"), _fk("QuotationLineID", "SupplierQuotationLn", "QuotationLineID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _decimal_named("OrderedQuantity", 1, 1000), _decimal_named("UnitPrice", 1, 6000), _calc("LineAmount", "OrderedQuantity * UnitPrice"), _decimal_named("OpenQuantity", 0, 1000),
                _status("LineStatus", "Open,Scheduled,PartiallyShipped,PartiallyReceived,Closed"),
            ]),
            _table("POSchedule", 50, "PO Schedule", "Procurement", "po_schedule", 6500, [
                _pk("POScheduleID"), _fk("PurchaseOrderLineID", "PurchaseOrderLine", "PurchaseOrderLineID"), _date("ScheduledDeliveryDate", "date_offset"),
                _decimal_named("ScheduledQuantity", 1, 1000), _status("ScheduleStatus", "Planned,Scheduled,PartiallyShipped,Shipped,Delayed"),
            ]),
            _table("ShipmentHdr", 60, "Shipment", "Logistics", "shipment_header", 1700, [
                _pk("ShipmentID"), _fk("PurchaseOrderID", "PurchaseOrderHdr", "PurchaseOrderID"), _fk("SupplierID", "SupplierMaster", "SupplierID"), _date("ShipmentDate", "date_offset"),
                _cat("CarrierName", ""), _cat("TrackingNumber", ""), _status("ShipmentStatus", "Planned,Shipped,InTransit,Delivered,Delayed,PartiallyDelivered"),
            ]),
            _table("ShipmentLine", 61, "Shipment Line", "Logistics", "shipment_line", 5800, [
                _pk("ShipmentLineID"), _fk("ShipmentID", "ShipmentHdr", "ShipmentID"), _fk("POScheduleID", "POSchedule", "POScheduleID"), _fk("PurchaseOrderLineID", "PurchaseOrderLine", "PurchaseOrderLineID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _decimal_named("ShippedQuantity", 1, 1000),
            ]),
            _table("GoodsReceiptHeader", 70, "Goods Receipt", "Logistics", "goods_receipt_header", 1700, [
                _pk("GoodsReceiptID"), _fk("ShipmentID", "ShipmentHdr", "ShipmentID"), _fk("PlantID", "Plant", "PlantID"), _fk("WarehouseID", "Warehouse", "WarehouseID"),
                _date("ReceiptDate", "date_offset"), _status("ReceiptStatus", "Received,Partial,ShortReceived,Damaged,Closed"),
            ]),
            _table("GoodsReceiptLine", 71, "Goods Receipt Line", "Logistics", "goods_receipt_line", 5800, [
                _pk("GoodsReceiptLineID"), _fk("GoodsReceiptID", "GoodsReceiptHeader", "GoodsReceiptID"), _fk("ShipmentLineID", "ShipmentLine", "ShipmentLineID"), _fk("PurchaseOrderLineID", "PurchaseOrderLine", "PurchaseOrderLineID"), _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _decimal_named("ShippedQuantity", 1, 1000), _decimal_named("ReceivedQuantity", 0, 1000), _decimal_named("DamagedQuantity", 0, 100), _calc("ShortQuantity", "ShippedQuantity - ReceivedQuantity"),
            ]),
            _table("IncomingInspection", 80, "Incoming Inspection", "Quality", "incoming_inspection", 5800, [
                _pk("InspectionID"), _fk("GoodsReceiptLineID", "GoodsReceiptLine", "GoodsReceiptLineID"), _date("InspectionDate", "date_offset"),
                ("InspectorName", "varchar(120)", "", None, None, "No", "", "", "", "Inspector name", "faker_person", ""), _status("InspectionStatus", "Pending,Passed,PartiallyRejected,Failed,Completed"),
            ]),
            _table("InspectionResult", 81, "Inspection Result", "Quality", "inspection_result", 5800, [
                _pk("InspectionResultID"), _fk("InspectionID", "IncomingInspection", "InspectionID"), _cat("TestName", "Visual Inspection,Dimensional Check,Electrical Test,Packaging Check,Documentation Review,Thermal Test"),
                _decimal_named("InspectedQuantity", 0, 1000), _decimal_named("AcceptedQuantity", 0, 1000), _calc("RejectedQuantity", "InspectedQuantity - AcceptedQuantity"),
                ("RejectionRatePct", "decimal(5,2)", "", None, None, "Yes", "", "", "", "Rejection percentage", "calculated", "RejectedQuantity / InspectedQuantity * 100"),
                ("RejectionReason", "varchar(150)", "", None, None, "Yes", "Not Applicable,Dimension Out of Tolerance,Surface Defect,Electrical Test Failure,Packaging Damage,Material Contamination,Wrong Specification,Thermal Stress Failure,Supplier Documentation Issue,Visual Defect,Functional Test Failure", "", "", "Rejection reason", "category", ""),
                _status("ResultStatus", "Passed,PartiallyRejected,Failed"),
            ]),
            _table("InventoryTransaction", 90, "Inventory Transaction", "Inventory", "inventory_transaction", 5500, [
                _pk("InventoryTransactionID"),
                _fk("InspectionResultID", "InspectionResult", "InspectionResultID"),
                _fk("GoodsReceiptLineID", "GoodsReceiptLine", "GoodsReceiptLineID"),
                _fk("PurchaseOrderLineID", "PurchaseOrderLine", "PurchaseOrderLineID"),
                _fk("SupplierID", "SupplierMaster", "SupplierID"),
                _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _fk("PlantID", "Plant", "PlantID"),
                _fk("WarehouseID", "Warehouse", "WarehouseID"),
                _date("TransactionDate", "date_offset", "2025-01-01", "2025-12-31"),
                _status("TransactionType", "StockIn"),
                ("TransactionQuantity", "decimal(18,2)", "", None, None, "No", "", 0, 1000000, "Accepted quantity posted to inventory; equals InspectionResult.AcceptedQuantity", "decimal_range", "InspectionResult.AcceptedQuantity"),
                ("UnitPrice", "decimal(18,2)", "", None, None, "No", "", 0, 6000, "Unit price from PurchaseOrderLine.UnitPrice", "decimal_range", "PurchaseOrderLine.UnitPrice"),
                _calc_range("InventoryValue", "TransactionQuantity * UnitPrice", 0, 100000000),
                _cat("ReferenceDocument", "", "varchar(80)"),
                _status("InventoryStatus", "Posted,QualityAccepted,ReceivedToInventory"),
            ]),
            _table("Inventory", 95, "Inventory Balance", "Inventory", "inventory", 3000, [
                _pk("InventoryID"),
                _fk("ComponentID", "ComponentMaster", "ComponentID"),
                _fk("PlantID", "Plant", "PlantID"),
                _fk("WarehouseID", "Warehouse", "WarehouseID"),
                _calc_range("OnHandQuantity", "SUM(InventoryTransaction.TransactionQuantity) GROUP BY ComponentID, PlantID, WarehouseID", 0, 1000000),
                _decimal_named("ReservedQuantity", 0, 100000),
                _calc_range("AvailableQuantity", "OnHandQuantity - ReservedQuantity", 0, 1000000),
                _calc_range("OnHandValue", "SUM(InventoryTransaction.InventoryValue) GROUP BY ComponentID, PlantID, WarehouseID", 0, 100000000),
                _calc_range("AvailableValue", "AvailableQuantity * (OnHandValue / OnHandQuantity)", 0, 100000000),
                ("LastTransactionDate", "date", "", None, None, "No", "", "2025-01-01", "2025-12-31", "Last inventory transaction date", "calculated", "MAX(InventoryTransaction.TransactionDate) GROUP BY ComponentID, PlantID, WarehouseID"),
                _date("LastUpdatedDate", "date_range", "2025-01-01", "2025-12-31"),
                _status("InventoryStatus", "Available,LowStock,OutOfStock,Hold"),
            ]),
            _table("SupplierInvoice", 100, "Supplier Invoice", "Finance", "supplier_invoice", 1700, [
                _pk("SupplierInvoiceID"), _fk("PurchaseOrderID", "PurchaseOrderHdr", "PurchaseOrderID"), _fk("SupplierID", "SupplierMaster", "SupplierID"), _fk("GoodsReceiptID", "GoodsReceiptHeader", "GoodsReceiptID"),
                _date("InvoiceDate", "date_offset"), _date("DueDate", "date_offset"), _status("InvoiceStatus", "Draft,Submitted,Approved,PartiallyPaid,Paid,Overdue"),
                _calc("InvoiceAmount", "SUM(received PO value)"), _decimal_named("TaxAmount", 0, 5000), _decimal_named("FreightAmount", 0, 3000), _calc("TotalInvoiceAmount", "InvoiceAmount + TaxAmount + FreightAmount"), _usd(),
            ]),
            _table("PaymentTransaction", 110, "Payment Transaction", "Finance", "payment_transaction", 1700, [
                _pk("PaymentTransactionID"), _fk("SupplierInvoiceID", "SupplierInvoice", "SupplierInvoiceID"), _fk("SupplierID", "SupplierMaster", "SupplierID"),
                _date("PaymentDate", "date_offset"), _decimal_named("PaymentAmount", 0, 1000000), _cat("PaymentMethod", "ACH,Wire Transfer,Check,Credit Transfer"), _status("PaymentStatus", "Pending,Paid,PartiallyPaid,Failed"), _usd(),
            ]),
        ]
    )
    return tables


def _table(name, order, process, area, role, rows, columns):
    return {"table": name, "order": order, "process": process, "area": area, "role": role, "rows": rows, "columns": columns}


def _pk(name):
    return (name, "int", "PK", None, None, "No", "", "", "", f"{name} primary key", "sequence_id", "")


def _fk(name, table, column):
    return (name, "int", "FK", table, column, "No", "", "", "", f"{name} foreign key", "foreign_key", "")


def _cat(name, values, data_type="varchar(80)"):
    return (name, data_type, "", None, None, "No", values, "", "", name, "category", "")


def _status(name, values):
    return (name, "varchar(40)", "", None, None, "No", values, "", "", name, "status", "")


def _date(name, generation_type, min_value="", max_value=""):
    return (name, "date", "", None, None, "No", "", min_value, max_value, name, generation_type, "")


def _decimal(name, min_value, max_value):
    return _decimal_named(name, min_value, max_value)


def _decimal_named(name, min_value, max_value):
    return (name, "decimal(18,2)", "", None, None, "No", "", min_value, max_value, name, "decimal_range", "")


def _calc(name, formula):
    return (name, "decimal(18,2)", "", None, None, "No", "", "", "", name, "calculated", formula)


def _calc_range(name, formula, min_value, max_value):
    return (name, "decimal(18,2)", "", None, None, "No", "", min_value, max_value, name, "calculated", formula)


def _usd():
    return ("CurrencyCode", "varchar(10)", "", None, None, "No", "USD", "", "", "Currency code", "category", "")


def _write_metadata(rows: list[dict]) -> None:
    path = INPUT_DIR / "procurement_v2_metadata.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=HEADERS).to_excel(writer, sheet_name="Metadata", index=False)
        summary = pd.DataFrame(
            [
                {"Metric": "Tables", "Value": len({row["TableName"] for row in rows})},
                {"Metric": "MetadataRows", "Value": len(rows)},
                {"Metric": "TotalTargetRows", "Value": sum({row["TableName"]: row["TargetRows"] for row in rows}.values())},
            ]
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)


def _write_erd() -> None:
    erd = """erDiagram
    SupplierMaster ||--o{ SupplierComponent : supplies
    ComponentMaster ||--o{ SupplierComponent : sourced_as
    Plant ||--o{ Warehouse : contains
    Plant ||--o{ PurchaseRequisition : requests
    PurchaseRequisition ||--o{ PurchaseReqLine : contains
    ComponentMaster ||--o{ PurchaseReqLine : requested_component
    PurchaseRequisition ||--o{ RFQHeader : creates
    RFQHeader ||--o{ RFQLine : contains
    PurchaseReqLine ||--o{ RFQLine : rfq_for_line
    ComponentMaster ||--o{ RFQLine : quoted_component
    RFQHeader ||--o{ SupplierQuotation : receives
    SupplierMaster ||--o{ SupplierQuotation : submits
    SupplierQuotation ||--o{ SupplierQuotationLn : contains
    RFQLine ||--o{ SupplierQuotationLn : quoted_line
    ComponentMaster ||--o{ SupplierQuotationLn : quoted_component
    SupplierQuotation ||--o{ PurchaseOrderHdr : awarded_to_po
    SupplierMaster ||--o{ PurchaseOrderHdr : supplier_for_po
    Plant ||--o{ PurchaseOrderHdr : po_for_plant
    PurchaseOrderHdr ||--o{ PurchaseOrderLine : contains
    SupplierQuotationLn ||--o{ PurchaseOrderLine : awarded_line
    ComponentMaster ||--o{ PurchaseOrderLine : ordered_component
    PurchaseOrderLine ||--o{ POSchedule : scheduled_as
    POSchedule ||--o{ ShipmentLine : shipped_schedule
    PurchaseOrderHdr ||--o{ ShipmentHdr : shipped_against
    SupplierMaster ||--o{ ShipmentHdr : ships
    ShipmentHdr ||--o{ ShipmentLine : contains
    PurchaseOrderLine ||--o{ ShipmentLine : shipped_po_line
    ComponentMaster ||--o{ ShipmentLine : shipped_component
    ShipmentHdr ||--o{ GoodsReceiptHeader : received_as
    Plant ||--o{ GoodsReceiptHeader : received_at
    Warehouse ||--o{ GoodsReceiptHeader : received_into
    GoodsReceiptHeader ||--o{ GoodsReceiptLine : contains
    ShipmentLine ||--o{ GoodsReceiptLine : received_line
    PurchaseOrderLine ||--o{ GoodsReceiptLine : received_po_line
    ComponentMaster ||--o{ GoodsReceiptLine : received_component
    GoodsReceiptLine ||--o{ IncomingInspection : inspected_by
    IncomingInspection ||--o{ InspectionResult : contains
    InspectionResult ||--o{ InventoryTransaction : posts_inventory
    SupplierMaster ||--o{ InventoryTransaction : supplied_inventory
    GoodsReceiptLine ||--o{ InventoryTransaction : received_inventory_line
    PurchaseOrderLine ||--o{ InventoryTransaction : inventory_po_line
    ComponentMaster ||--o{ InventoryTransaction : inventory_component
    Plant ||--o{ InventoryTransaction : inventory_plant
    Warehouse ||--o{ InventoryTransaction : inventory_warehouse
    ComponentMaster ||--o{ Inventory : inventory_component
    Plant ||--o{ Inventory : inventory_plant
    Warehouse ||--o{ Inventory : inventory_warehouse
    PurchaseOrderHdr ||--o{ SupplierInvoice : invoiced_po
    SupplierMaster ||--o{ SupplierInvoice : invoices
    GoodsReceiptHeader ||--o{ SupplierInvoice : invoice_for_receipt
    SupplierInvoice ||--o{ PaymentTransaction : paid_by
    SupplierMaster ||--o{ PaymentTransaction : payment_to_supplier
"""
    (INPUT_DIR / "procurement_v2_erd.mmd").write_text(erd, encoding="utf-8")


def _write_scenario() -> None:
    scenario = """Generate procurement data for the 2025 calendar year only, from 2025-01-01 to 2025-12-31, for a US-based EV manufacturing procurement process.

The business should include US-based plants and warehouses, supplier sourcing, RFQ, supplier quotation, awarded quotation, purchase order, PO schedules, supplier shipments, goods receipts, incoming quality inspection, inventory posting, current inventory balance, supplier invoices, and payment transactions.

InventoryTransaction records each accepted StockIn posting into inventory after incoming inspection. It should include supplier, component, plant, warehouse, transaction date, quantity, unit price, inventory value, and references to the goods receipt line, purchase order line, and inspection result. TransactionType should be StockIn for this inbound procurement scenario.

The process should include InventoryTransaction as the detailed inbound stock posting ledger and Inventory as the current calculated stock balance by Component, Plant, and Warehouse. Inventory should store OnHandQuantity, ReservedQuantity, AvailableQuantity, OnHandValue, AvailableValue, LastTransactionDate, LastUpdatedDate, and InventoryStatus.

Inventory.OnHandQuantity is calculated from InventoryTransaction.TransactionQuantity grouped by ComponentID, PlantID, and WarehouseID. Inventory.OnHandValue is calculated from InventoryTransaction.InventoryValue grouped by ComponentID, PlantID, and WarehouseID. Inventory.AvailableQuantity equals OnHandQuantity minus ReservedQuantity. Inventory.AvailableValue is derived from AvailableQuantity and average unit cost.

Use USD for all financial values.

Include realistic behavior:
- supplier-component eligibility
- multiple supplier quotations per RFQ
- awarded and rejected quotation lines
- partial deliveries
- delayed shipments
- short receipts
- damaged receipt quantities
- quality rejections
- inventory posting only for accepted quantity
- invoices after goods receipts
- partial/pending/paid payment behavior
- lifecycle-based status diversity

Do not generate data outside 2025.
"""
    (INPUT_DIR / "procurement_v2_business_scenario.txt").write_text(scenario, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
