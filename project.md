# Procurement Data Generation Tool - Project Documentation

Last updated: 2026-05-08

This document explains the complete project as it stands now: what the tool does, how Procurement v1 and Procurement v2 work, what was created or updated, the important files, the SQL validation packs, and the major fixes that were made during development.

## 1. Project Purpose

This project generates realistic synthetic procurement data from metadata, ERD, and business scenario inputs.

The intended architecture is:

```text
Metadata XLSX + Mermaid ERD + Business Scenario
    -> Prompt builder
    -> Azure OpenAI plan JSON generation, optional
    -> Plan shape validation
    -> Plan normalization
    -> Semantic plan validation
    -> Python master/support data generation
    -> Python transaction data generation
    -> Formula execution
    -> Final validation and reconciliation
    -> Audit report
    -> Optional SQL Server load
    -> FastAPI UI/API artifact download
```

The core rule of the project is:

```text
LLM plans.
Python validates.
Python generates.
Python calculates.
Python reconciles.
Python loads to SQL.
```

The LLM is allowed to generate a structured generation plan only. It must not directly generate table rows.

## 2. Current Final Procurement v2 Status

Procurement v2 is the expanded 24-table model for a US-based EV manufacturing procurement scenario.

Final status after the latest strict lifecycle/status fix:

```text
Model version: v2
Tables generated: 24
InventoryTransaction: included
Inventory: included
InventoryBalance: excluded
SQL load: available but optional
FastAPI UI/API: supports v1 and v2 selection
Azure OpenAI plan generation: supported for v2
Final sample-plan pipeline status: passed_with_warnings
Data quality status: passed_with_warnings
Errors: 0
Full pytest: 555 passed, 5 warnings
```

The latest full v2 sample-plan pipeline run used:

```powershell
python scripts/run_pipeline.py --metadata input/procurement_v2_metadata.xlsx --erd input/procurement_v2_erd.mmd --scenario input/procurement_v2_business_scenario.txt --plan input/sample_generation_plan_v2_valid.json --output output/v2_runs --seed 42 --load-sql false --build-prompt true --model-version v2
```

Latest run folder:

```text
output/v2_runs/run_20260507_184438_542505
```

Latest pipeline result:

```text
Status: passed_with_warnings
Tables generated: 24
Total rows generated: 69,179
Data quality status: passed_with_warnings
SQL load: skipped
Audit report: output/v2_runs/run_20260507_184438_542505/reports/audit_report.md
```

The warnings are expected lifecycle row-count warnings. They occur because the generator now refuses to fabricate downstream quantity-bearing rows when valid upstream quoted/ordered/accepted quantity is exhausted.

## 3. Final Procurement v2 Table List

Procurement v2 currently generates these 24 tables:

1. SupplierMaster
2. SupplierComponent
3. ComponentMaster
4. Plant
5. Warehouse
6. PurchaseRequisition
7. PurchaseReqLine
8. RFQHeader
9. RFQLine
10. SupplierQuotation
11. SupplierQuotationLn
12. PurchaseOrderHdr
13. PurchaseOrderLine
14. POSchedule
15. ShipmentHdr
16. ShipmentLine
17. GoodsReceiptHeader
18. GoodsReceiptLine
19. IncomingInspection
20. InspectionResult
21. InventoryTransaction
22. Inventory
23. SupplierInvoice
24. PaymentTransaction

Important:

```text
InventoryTransaction remains included.
Inventory remains included.
InventoryBalance remains excluded.
```

## 4. Main Business Lifecycle

Procurement v2 follows this strict lifecycle:

```text
PurchaseReqLine.RequestedQuantity
    -> RFQLine.RFQQuantity
    -> SupplierQuotationLn.QuotedQuantity
    -> PurchaseOrderLine.OrderedQuantity
    -> POSchedule.ScheduledQuantity
    -> ShipmentLine.ShippedQuantity
    -> GoodsReceiptLine.ReceivedQuantity
    -> InspectionResult.InspectedQuantity
    -> InspectionResult.AcceptedQuantity
    -> InventoryTransaction.TransactionQuantity
    -> Inventory.OnHandQuantity
```

Every downstream quantity must be derived from the previous lifecycle step and must not exceed upstream quantity.

The most important final rules are:

```text
RFQQuantity <= RequestedQuantity
QuotedQuantity <= RFQQuantity
OrderedQuantity <= awarded QuotedQuantity
SUM(OrderedQuantity) by QuotationLineID <= QuotedQuantity
SUM(ScheduledQuantity) by PurchaseOrderLineID <= OrderedQuantity
SUM(ShippedQuantity) by POScheduleID <= ScheduledQuantity
SUM(ShippedQuantity) by PurchaseOrderLineID <= OrderedQuantity
SUM(ReceivedQuantity) by ShipmentLineID <= ShippedQuantity
SUM(ReceivedQuantity) by PurchaseOrderLineID <= OrderedQuantity
InspectedQuantity <= ReceivedQuantity
AcceptedQuantity + RejectedQuantity = InspectedQuantity
SUM(AcceptedQuantity) by PurchaseOrderLineID <= OrderedQuantity
InventoryTransaction.TransactionQuantity = InspectionResult.AcceptedQuantity
SUM(InventoryTransaction.TransactionQuantity) by PurchaseOrderLineID <= OrderedQuantity
Inventory.OnHandQuantity = SUM(InventoryTransaction.TransactionQuantity) by ComponentID + PlantID + WarehouseID
Inventory.OnHandValue = SUM(InventoryTransaction.InventoryValue) by ComponentID + PlantID + WarehouseID
```

## 5. Final Numeric Lifecycle Proof

The latest validated pipeline output produced this lifecycle summary:

```text
TotalRequestedQuantity:        1,908,451.55
TotalRFQQuantity:              1,697,548.35
TotalAwardedQuotedQuantity:      983,780.39
TotalOrderedQuantity:            565,394.17
TotalScheduledQuantity:          565,394.17
TotalShippedQuantity:            462,244.44
TotalReceivedQuantity:           453,978.87
TotalInspectedQuantity:          453,978.87
TotalAcceptedQuantity:           424,589.42
TotalStockInQuantity:            424,589.42
```

The required relationship holds:

```text
TotalRequestedQuantity
>= TotalRFQQuantity
>= TotalAwardedQuotedQuantity
>= TotalOrderedQuantity
>= TotalScheduledQuantity
>= TotalShippedQuantity
>= TotalReceivedQuantity
>= TotalInspectedQuantity
>= TotalAcceptedQuantity
= TotalStockInQuantity
```

Final issue counts:

```text
QuotationLine cumulative over-ordered count: 0
StockIn total > OrderedQuantity count: 0
Closed PO with partial stock-in count: 0
Closed PO line with partial stock-in count: 0
Receipt status invalid count: 0
Payment status invalid count: 0
Invalid status count: 0
Max PO stock-in utilization percentage: 99.79
```

## 6. Inventory and InventoryTransaction Design

### InventoryTransaction

InventoryTransaction is the detailed inbound stock-in ledger.

It records accepted goods posted into inventory after incoming inspection. In the current procurement inbound flow:

```text
TransactionType = StockIn
```

This is intentionally constant because this model covers accepted supplier receipts entering inventory, not stock issue, transfer, adjustment, scrap, or returns.

Final InventoryTransaction columns:

```text
InventoryTransactionID
InspectionResultID
GoodsReceiptLineID
PurchaseOrderLineID
SupplierID
ComponentID
PlantID
WarehouseID
TransactionDate
TransactionType
TransactionQuantity
UnitPrice
InventoryValue
ReferenceDocument
InventoryStatus
```

Key formulas and lineage:

```text
GoodsReceiptLineID = linked IncomingInspection.GoodsReceiptLineID
PurchaseOrderLineID = GoodsReceiptLine.PurchaseOrderLineID
SupplierID = PurchaseOrderHdr.SupplierID through PurchaseOrderLine
ComponentID = GoodsReceiptLine.ComponentID and PurchaseOrderLine.ComponentID
PlantID/WarehouseID = GoodsReceiptHeader location
TransactionDate >= InspectionDate
TransactionType = StockIn
TransactionQuantity = InspectionResult.AcceptedQuantity
UnitPrice = PurchaseOrderLine.UnitPrice
InventoryValue = TransactionQuantity * UnitPrice
```

Allowed InventoryTransaction.InventoryStatus values:

```text
Posted
QualityAccepted
ReceivedToInventory
```

### Inventory

Inventory is the calculated current stock balance table.

It summarizes InventoryTransaction by:

```text
ComponentID + PlantID + WarehouseID
```

Final Inventory columns:

```text
InventoryID
ComponentID
PlantID
WarehouseID
OnHandQuantity
ReservedQuantity
AvailableQuantity
OnHandValue
AvailableValue
LastTransactionDate
LastUpdatedDate
InventoryStatus
```

Key calculations:

```text
OnHandQuantity = SUM(InventoryTransaction.TransactionQuantity)
OnHandValue = SUM(InventoryTransaction.InventoryValue)
ReservedQuantity = deterministic reserved portion of OnHandQuantity
AvailableQuantity = OnHandQuantity - ReservedQuantity
AverageUnitCost = OnHandValue / OnHandQuantity
AvailableValue = AvailableQuantity * AverageUnitCost
LastTransactionDate = MAX(InventoryTransaction.TransactionDate)
LastUpdatedDate = LastTransactionDate
```

InventoryStatus logic:

```text
If OnHandQuantity = 0:
    InventoryStatus = OutOfStock
If OnHandQuantity > 0 and AvailableQuantity = 0:
    InventoryStatus = Hold
If OnHandQuantity > 0 and AvailableQuantity > 0 and AvailableQuantity <= 10% of OnHandQuantity:
    InventoryStatus = LowStock
Otherwise:
    InventoryStatus = Available
```

OutOfStock may be absent because the generator does not create fake zero-stock rows.

## 7. Status Consistency Rules

Statuses are no longer random. They are derived from lifecycle facts.

### PurchaseOrderLine.LineStatus

Derived from scheduled, shipped, received, and stock-in totals.

Important rule:

```text
LineStatus cannot be Closed unless TotalStockInQuantity >= OrderedQuantity - tolerance.
```

### PurchaseOrderHdr.POStatus

Derived from all child PO lines.

Important rule:

```text
POStatus cannot be Closed unless total StockIn quantity for all PO lines >= total OrderedQuantity - tolerance.
```

This fixed the manager-observed issue where a partially stocked PO was marked Closed.

### POSchedule.ScheduleStatus

Derived from shipped quantity:

```text
No shipped quantity: Scheduled or Planned
Partial shipped quantity: PartiallyShipped
Fully shipped quantity: Shipped
Late shipment where allowed: Delayed
```

### ShipmentHdr.ShipmentStatus

Derived from shipped vs received quantity:

```text
No receipt: Shipped or InTransit
Partial receipt: PartiallyDelivered
Full receipt: Delivered
Late where allowed: Delayed
```

### GoodsReceiptHeader.ReceiptStatus

Derived from receipt lines:

```text
Damaged quantity > 0: Damaged
Short quantity > 0: ShortReceived
Partial receipt: Partial
Clean receipt: Received or Closed
```

### IncomingInspection.InspectionStatus and InspectionResult.ResultStatus

Derived from accepted and rejected quantities:

```text
RejectedQuantity = 0: Passed
RejectedQuantity > 0 and AcceptedQuantity > 0: PartiallyRejected
RejectedQuantity > 0 and AcceptedQuantity = 0: Failed
```

RejectionReason:

```text
RejectedQuantity = 0: blank or Not Applicable
RejectedQuantity > 0: populated with a real reason
```

### SupplierInvoice.InvoiceStatus and PaymentTransaction.PaymentStatus

Derived from actual payment amounts:

```text
PaymentAmount = 0: Pending or Failed
0 < PaymentAmount < TotalInvoiceAmount: PartiallyPaid
PaymentAmount >= TotalInvoiceAmount - tolerance: Paid
```

Invoice status is derived from cumulative payment amount:

```text
No payment: Submitted, Approved, Draft, or Overdue
Partial payment: PartiallyPaid
Fully paid: Paid
```

## 8. Financial Realism Tuning

Procurement v2 financial generation was tuned for a US-based EV manufacturing procurement scenario.

The issue fixed:

```text
Unit prices and quantities were both too high too often.
This created unrealistic multi-million-dollar PO lines, POs, invoices, and inventory values.
```

The fix introduced category-aware financial profiles.

Key file:

```text
procurement_data_generator/modules/procurement/financial_realism_profiles.py
```

Generation now uses category-specific ranges such as:

```text
Battery Components: higher unit price, lower quantity
Electrical Components: moderate/high unit price, controlled quantity
Powertrain Components: high unit price, low quantity
Thermal Management: moderate unit price, medium quantity
Mechanical Components: lower unit price, higher quantity
Charging Components: moderate/high unit price, controlled quantity
Safety Components: lower unit price, higher quantity
Packaging Materials: low unit price, high quantity
Maintenance Spares: moderate unit price, lower quantity
```

Important relationships:

```text
ComponentMaster.StandardCost is category-aware.
SupplierComponent.ContractPrice = StandardCost * supplier variation.
SupplierQuotationLn.QuotedUnitPrice = ContractPrice * quote variation.
PurchaseOrderLine.UnitPrice = awarded QuotedUnitPrice.
OrderedQuantity is category-aware and price-aware.
InventoryValue flows naturally from TransactionQuantity * UnitPrice.
```

The goal is to keep high-value rows realistic and mostly limited to categories such as battery, powertrain, electrical/electronics, and charging systems.

## 9. Main Source Code Files

### Core contracts

```text
procurement_data_generator/core/contracts/schema_contract.py
```

Defines metadata schema contracts for tables, columns, keys, ranges, formulas, allowed values, and table roles.

```text
procurement_data_generator/core/contracts/llm_plan_contract.py
```

Defines the structured LLM generation plan format.

```text
procurement_data_generator/core/contracts/validation_report.py
procurement_data_generator/core/contracts/data_quality_report.py
procurement_data_generator/core/contracts/pipeline_report.py
procurement_data_generator/core/contracts/sql_load_report.py
```

Define report structures used throughout validation, data quality, pipeline execution, and SQL load.

### Metadata

```text
procurement_data_generator/core/metadata/metadata_reader.py
```

Loads XLSX metadata into schema contracts.

```text
procurement_data_generator/core/metadata/metadata_validator.py
```

Validates metadata shape, required fields, data types, key definitions, nullability, ranges, formulas, and allowed values.

### ERD

```text
procurement_data_generator/core/erd/mermaid_parser.py
procurement_data_generator/core/erd/erd_validator.py
```

Parse Mermaid ERD files and validate metadata FK relationships against ERD relationships.

### LLM planning

```text
procurement_data_generator/core/llm/prompt_builder.py
```

Builds the LLM planning prompt from metadata, ERD, and business scenario. Supports model_version `v1` and `v2`.

```text
procurement_data_generator/core/llm/azure_openai_client.py
```

Calls Azure OpenAI for plan generation.

```text
procurement_data_generator/core/llm/json_extractor.py
```

Extracts JSON from LLM responses.

```text
procurement_data_generator/core/llm/plan_loader.py
procurement_data_generator/core/llm/plan_normalizer.py
procurement_data_generator/core/llm/plan_validator.py
```

Load, normalize, and validate generation plans. V2 strict validation expects the 24-table model, includes Inventory, and rejects InventoryBalance.

### Procurement module

```text
procurement_data_generator/modules/procurement/role_catalog.py
```

Defines supported procurement roles. V2 includes 24 roles and supports `inventory`, while `inventory_balance` remains unsupported in strict v2.

```text
procurement_data_generator/modules/procurement/role_validator.py
```

Validates that metadata tables match expected procurement roles for v1 or v2.

```text
procurement_data_generator/modules/procurement/name_generators.py
```

Generates business-like names for suppliers, components, carriers, quality tests, and other labels.

```text
procurement_data_generator/modules/procurement/financial_realism_profiles.py
```

Central category-aware financial profile used by v2 master/transaction generation.

```text
procurement_data_generator/modules/procurement/master_generator.py
```

Generates master/support data:

```text
SupplierMaster
SupplierComponent
ComponentMaster
Plant
Warehouse
```

For v2 it generates US locations, USD-oriented supplier/component profiles, category-aware StandardCost, and ContractPrice tied to StandardCost.

```text
procurement_data_generator/modules/procurement/transaction_generator.py
```

Generates v1 and v2 transaction tables. This is the main lifecycle generator.

Important v2 responsibilities:

```text
Generate requisitions, RFQs, quotations, POs, schedules, shipments, receipts, inspections, inventory transactions, inventory, invoices, and payments.
Track remaining quoted quantity by QuotationLineID.
Track remaining ordered quantity by PurchaseOrderLineID.
Track remaining scheduled, shipped, received, accepted, and stock-in quantities.
Set TransactionType = StockIn.
Calculate InventoryTransaction.InventoryValue.
Calculate Inventory.OnHandQuantity, OnHandValue, AvailableQuantity, AvailableValue.
Derive lifecycle statuses from quantities and payments.
Warn, not fail, when valid lifecycle row counts are below metadata target because upstream quantity is exhausted.
```

### Formula execution

```text
procurement_data_generator/core/formulas/formula_engine.py
```

Executes structured formula rules safely. It avoids unsafe arbitrary `eval`.

Important v2 formula examples:

```text
PurchaseOrderLine.LineAmount = OrderedQuantity * UnitPrice
PurchaseOrderHdr.TotalAmount = SUM(PurchaseOrderLine.LineAmount)
SupplierInvoice.TotalInvoiceAmount = InvoiceAmount + TaxAmount + FreightAmount
InventoryTransaction.InventoryValue = TransactionQuantity * UnitPrice
Inventory.OnHandValue = SUM(InventoryTransaction.InventoryValue)
```

### Final validation and reconciliation

```text
procurement_data_generator/core/validation/data_validator.py
```

Runs final schema/data validation over generated CSVs.

```text
procurement_data_generator/core/validation/reconciler.py
```

Runs procurement lifecycle reconciliation and v2-specific strict checks.

Important v2 reconciliation areas:

```text
Supplier eligibility
RFQ/quote/PO component lineage
Awarded quotation to PO lineage
PO totals and line amounts
Lifecycle quantity ceilings
Cumulative quantity checks by QuotationLineID and PurchaseOrderLineID
Receipt, inspection, inventory lineage
InventoryTransaction StockIn and value checks
Inventory stock balance and value rollups
Invoice/payment checks
Lifecycle status consistency checks
InventoryBalance absence
```

### Pipeline

```text
procurement_data_generator/core/pipeline/pipeline_runner.py
```

Orchestrates full pipeline execution:

```text
metadata_validation
role_validation
erd_validation
prompt_building
llm_plan_generation, optional
plan_shape_validation
plan_normalization
plan_semantic_validation
master_generation
transaction_generation
formula_execution
final_data_merge
data_quality_validation
sql_load, optional
audit_report
```

### Audit

```text
procurement_data_generator/core/audit/audit_report.py
```

Generates Markdown and JSON audit reports for pipeline runs, including status, row counts, warnings, errors, data quality, SQL load status, and generated artifacts.

### SQL loading

```text
procurement_data_generator/core/sql/db_config.py
procurement_data_generator/core/sql/ddl_generator.py
procurement_data_generator/core/sql/sql_loader.py
```

Handle SQL Server configuration, DDL generation, table creation, and CSV loading.

SQL load is optional. Unit tests do not require real SQL Server.

## 10. FastAPI UI/API

The FastAPI app lives under:

```text
app/
```

Important files:

```text
app/main.py
```

Creates the FastAPI app and mounts routes/static/templates.

```text
app/routes/ui_routes.py
```

Serves the browser UI.

```text
app/routes/pipeline_routes.py
```

Exposes pipeline run API.

```text
app/routes/artifact_routes.py
```

Exposes artifact download endpoints.

```text
app/services/upload_service.py
```

Handles uploaded metadata/ERD/scenario/plan files.

```text
app/services/pipeline_service.py
```

Converts API form input into pipeline runner execution. Supports `model_version=v1` or `model_version=v2`.

```text
app/services/artifact_service.py
```

Finds and serves generated artifacts including audit reports, pipeline reports, final data ZIP, generated plan, and raw LLM response.

```text
app/templates/index.html
app/static/js/app.js
app/static/css/style.css
```

Plain HTML/CSS/JS MVP UI.

The UI supports:

```text
Metadata XLSX upload
ERD upload or paste
Business scenario input
Plan JSON upload
Azure OpenAI plan generation mode
Build prompt option
SQL load option
Seed input
Model Version: Procurement v1 or Procurement v2
Pipeline run
Download audit report
Download pipeline report
Download final data ZIP
Download generated plan JSON
Download raw LLM response
```

Procurement v1 remains the default unless v2 is explicitly selected.

## 11. Input Fixtures

Important input files:

```text
input/procurement_v2_metadata.xlsx
```

The v2 metadata workbook. It defines 24 tables, columns, data types, keys, ranges, formulas, allowed values, table roles, target rows, and process order.

```text
input/procurement_v2_erd.mmd
```

Mermaid ERD for v2. Includes strict FK relationships, including Inventory and refined InventoryTransaction FKs.

```text
input/procurement_v2_business_scenario.txt
```

Business scenario for US-based EV manufacturing procurement. Explains RFQ, quotation, PO, receipt, inspection, StockIn, inventory, invoice, and payment behavior.

```text
input/sample_generation_plan_v2_valid.json
```

Valid sample v2 plan used for deterministic local testing.

```text
input/sample_generation_plan_v2_invalid.json
```

Invalid v2 plan fixture used by tests.

Other v1 and earlier phase fixtures remain in `input/` for regression coverage.

## 12. Scripts

Important scripts:

```text
scripts/create_procurement_v2_fixtures.py
```

Regenerates v2 metadata, ERD, scenario, and sample plan fixtures.

```text
scripts/build_llm_prompt.py
```

Builds the LLM prompt from metadata, ERD, and scenario.

```text
scripts/generate_llm_plan.py
```

Calls Azure OpenAI to generate a plan JSON.

```text
scripts/validate_generation_plan.py
```

Validates a generation plan against metadata and ERD.

```text
scripts/generate_master_data.py
```

Generates master/support CSV files.

```text
scripts/generate_transaction_data.py
```

Generates transaction/process CSV files.

```text
scripts/execute_formulas.py
```

Executes formula rules and writes formula output.

```text
scripts/validate_generated_data.py
```

Runs final generated data validation and reconciliation.

```text
scripts/run_pipeline.py
```

Runs the full backend pipeline.

```text
scripts/load_to_sql.py
```

Loads generated final data to SQL Server when configured.

```text
scripts/generate_audit_report.py
```

Generates audit report artifacts.

## 13. SQL Validation Packs

SQL check files live in:

```text
docs/
```

### Inventory SQL checks

```text
docs/procurement_v2_inventory_sql_checks.sql
```

Purpose:

```text
Validate InventoryTransaction and Inventory in SQL Server.
Confirm StockIn transaction value.
Confirm Inventory.OnHandQuantity and OnHandValue rollups.
Confirm AvailableQuantity and AvailableValue.
Confirm warehouse/plant consistency.
Confirm InventoryBalance absence.
```

Important Inventory OnHand SQL check:

```sql
WITH TxnBalance AS (
    SELECT
        ComponentID,
        PlantID,
        WarehouseID,
        SUM(TransactionQuantity) AS ExpectedOnHandQuantity
    FROM dbo.InventoryTransaction
    GROUP BY ComponentID, PlantID, WarehouseID
)
SELECT
    COUNT(*) AS BadInventoryOnHandRows,
    MAX(ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity)) AS MaxDifference
FROM dbo.Inventory inv
JOIN TxnBalance tb
    ON inv.ComponentID = tb.ComponentID
   AND inv.PlantID = tb.PlantID
   AND inv.WarehouseID = tb.WarehouseID
WHERE ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity) > 0.0001;
```

Expected:

```text
BadInventoryOnHandRows = 0
```

Important InventoryBalance absence SQL check:

```sql
SELECT COUNT(*) AS InventoryBalanceObjectCount
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'InventoryBalance';
```

Expected:

```text
InventoryBalanceObjectCount = 0
```

### Lifecycle quantity and status SQL checks

```text
docs/procurement_v2_lifecycle_quantity_sql_checks.sql
```

Purpose:

```text
Validate full procurement lifecycle quantity control in SQL Server.
Validate the manager's main issue: StockIn cannot exceed PO ordered quantity.
Validate cumulative ordered quantity cannot exceed awarded quoted quantity.
Validate status consistency for PO, receipt, inspection, invoice, and payment.
```

Manager's main SQL query:

```sql
SELECT
    pol.PurchaseOrderLineID,
    pol.PurchaseOrderID,
    pol.ComponentID,
    pol.OrderedQuantity,
    SUM(it.TransactionQuantity) AS TotalStockInQuantity,
    SUM(it.TransactionQuantity) - pol.OrderedQuantity AS ExcessQuantity
FROM dbo.PurchaseOrderLine pol
JOIN dbo.InventoryTransaction it
    ON pol.PurchaseOrderLineID = it.PurchaseOrderLineID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.PurchaseOrderID,
    pol.ComponentID,
    pol.OrderedQuantity
HAVING SUM(it.TransactionQuantity) > pol.OrderedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;
```

Expected:

```text
No rows returned.
```

Quotation-to-PO cumulative SQL check:

```sql
SELECT
    sqln.QuotationLineID,
    sqln.QuotedQuantity,
    SUM(pol.OrderedQuantity) AS TotalOrderedQuantity,
    SUM(pol.OrderedQuantity) - sqln.QuotedQuantity AS ExcessQuantity
FROM dbo.SupplierQuotationLn sqln
JOIN dbo.PurchaseOrderLine pol
    ON sqln.QuotationLineID = pol.QuotationLineID
GROUP BY
    sqln.QuotationLineID,
    sqln.QuotedQuantity
HAVING SUM(pol.OrderedQuantity) > sqln.QuotedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;
```

Expected:

```text
No rows returned.
```

Closed PO header with partial stock-in SQL check:

```sql
SELECT
    poh.PurchaseOrderID,
    poh.POStatus,
    SUM(pol.OrderedQuantity) AS TotalOrderedQuantity,
    COALESCE(SUM(stock.TotalStockInQuantity), 0) AS TotalStockInQuantity
FROM dbo.PurchaseOrderHdr poh
JOIN dbo.PurchaseOrderLine pol
    ON poh.PurchaseOrderID = pol.PurchaseOrderID
LEFT JOIN (
    SELECT PurchaseOrderLineID, SUM(TransactionQuantity) AS TotalStockInQuantity
    FROM dbo.InventoryTransaction
    GROUP BY PurchaseOrderLineID
) stock
    ON pol.PurchaseOrderLineID = stock.PurchaseOrderLineID
WHERE poh.POStatus = 'Closed'
GROUP BY
    poh.PurchaseOrderID,
    poh.POStatus
HAVING COALESCE(SUM(stock.TotalStockInQuantity), 0) < SUM(pol.OrderedQuantity) - 0.0001;
```

Expected:

```text
No rows returned.
```

The SQL file also includes final scorecards where every `IssueCount` should be `0`.

## 14. Major Work Completed

### Phase group: v1 foundation

Built the original Procurement v1 tool with:

```text
Metadata validation
Role validation
ERD validation
LLM prompt building
Plan validation
Master data generation
Transaction generation
Formula execution
Data validation/reconciliation
Audit report
SQL load
FastAPI UI/API
Artifact downloads
```

v1 remains supported and regression-tested.

### Procurement v2 creation

Added the Procurement v2 expanded model:

```text
V2 role catalog
V2 metadata XLSX
V2 ERD
V2 business scenario
V2 prompt guidance
V2 Azure OpenAI planning instructions
V2 semantic plan validation
V2 master/support generation
V2 transaction lifecycle generation
V2 formula execution
V2 final validation/reconciliation
V2 audit report and pipeline support
V2 FastAPI UI/API model selection
```

### Inventory extension

Added Inventory as the 24th v2 table:

```text
InventoryTransaction remains detailed StockIn ledger.
Inventory added as calculated current stock balance.
InventoryBalance remains excluded.
```

Added Inventory metadata, ERD relationships, generation, validation, audit/pipeline wiring, final ZIP behavior, UI helper text, and SQL checks.

### InventoryTransaction refinement

Updated InventoryTransaction to include supplier and value traceability:

```text
GoodsReceiptLineID
PurchaseOrderLineID
SupplierID
UnitPrice
InventoryValue
InventoryStatus
```

Added generation and validation for:

```text
TransactionType = StockIn
TransactionQuantity = AcceptedQuantity
UnitPrice = PO line UnitPrice
InventoryValue = TransactionQuantity * UnitPrice
SupplierID lineage through PO header
GoodsReceiptLine lineage through inspection
Plant/Warehouse lineage through receipt header
```

### Financial realism tuning

Added category-aware generation so EV procurement financial values are realistic.

Fixed:

```text
Unrealistic average PO totals
Unrealistic invoice totals
Too many million-dollar PO lines
Low-value categories producing huge purchase values
```

### Quantity lifecycle fix

Fixed the manager-reported issue:

```text
SUM(InventoryTransaction.TransactionQuantity) by PurchaseOrderLineID
must be <= PurchaseOrderLine.OrderedQuantity
```

Then added final validation and SQL checks so it cannot silently regress.

### Final strict lifecycle/status fix

Added:

```text
SUM(PurchaseOrderLine.OrderedQuantity) by QuotationLineID <= SupplierQuotationLn.QuotedQuantity
Strict lifecycle status derivation
PO header/line cannot be Closed if partially stocked
Receipt status cannot hide short/damaged quantity
Inspection status must match accepted/rejected quantities
Payment status must match payment amount
Invoice status must match cumulative payment amount
SQL status consistency checks
```

## 15. Commands Used for Current Validation

Generate v2 master data:

```powershell
python scripts/generate_master_data.py --metadata input/procurement_v2_metadata.xlsx --plan input/sample_generation_plan_v2_valid.json --output output/v2_master_data --seed 42 --model-version v2
```

Generate v2 transaction data:

```powershell
python scripts/generate_transaction_data.py --metadata input/procurement_v2_metadata.xlsx --plan input/sample_generation_plan_v2_valid.json --erd input/procurement_v2_erd.mmd --output output/v2_transaction_data --seed 42 --model-version v2
```

Execute formulas:

```powershell
python scripts/execute_formulas.py --metadata input/procurement_v2_metadata.xlsx --plan input/sample_generation_plan_v2_valid.json --input-folder output/v2_transaction_data --output-folder output/v2_formula_data --model-version v2
```

Validate generated data:

```powershell
python scripts/validate_generated_data.py --metadata input/procurement_v2_metadata.xlsx --data-folder output/v2_master_data --data-folder output/v2_transaction_data --data-folder output/v2_formula_data --plan input/sample_generation_plan_v2_valid.json --model-version v2
```

Run full pipeline:

```powershell
python scripts/run_pipeline.py --metadata input/procurement_v2_metadata.xlsx --erd input/procurement_v2_erd.mmd --scenario input/procurement_v2_business_scenario.txt --plan input/sample_generation_plan_v2_valid.json --output output/v2_runs --seed 42 --load-sql false --build-prompt true --model-version v2
```

Run full tests:

```powershell
python -m pytest -q
```

Latest test result:

```text
555 passed, 5 warnings
```

## 16. Test Suite Overview

Important tests:

```text
tests/test_procurement_v2_fixtures.py
```

Validates v2 metadata, ERD, scenario, Inventory, and InventoryBalance absence.

```text
tests/test_procurement_role_catalog.py
```

Validates v1/v2 supported roles and strict unsupported roles.

```text
tests/test_prompt_builder_v2.py
```

Validates v2 prompt guidance, table count, Inventory, InventoryTransaction, StockIn, and InventoryBalance exclusion.

```text
tests/test_plan_validator_v2.py
```

Validates v2 sample plan, required roles, lifecycle, Inventory, formulas, and semantic rules.

```text
tests/test_master_generator_v2.py
```

Validates v2 master data generation and financial realism at master level.

```text
tests/test_transaction_generator_v2.py
```

Validates v2 lifecycle generation:

```text
FKs
Supplier eligibility
RFQ/quote/PO lineage
Financial realism
Cumulative quantity rules
InventoryTransaction StockIn and value
Inventory rollups
Status logic
Payment/invoice behavior
Determinism
```

```text
tests/test_formula_engine_v2.py
```

Validates v2 formula execution and no infinity values.

```text
tests/test_reconciler_v2.py
```

Validates final v2 reconciliation failures for bad lineage, bad quantities, bad Inventory, bad status, bad payment, and bad Invoice cases.

```text
tests/test_data_validator_v2.py
```

Validates final data quality report behavior for v2.

```text
tests/test_pipeline_runner_v2.py
```

Validates v2 full backend pipeline using sample plan and mocked Azure where needed.

```text
tests/test_pipeline_api_v2.py
tests/test_fastapi_app.py
tests/test_artifact_api.py
```

Validate UI/API behavior, model version selection, and artifact downloads.

```text
tests/test_sql_check_files.py
```

Validates SQL check files exist and include required lifecycle/status checks.

v1 regression tests remain:

```text
tests/test_transaction_generator.py
tests/test_reconciler.py
tests/test_data_validator.py
tests/test_pipeline_runner.py
```

## 17. Output Artifacts

Pipeline output folders include:

```text
master_data/
transaction_data/
formula_data/
final_data/
metadata/
prompt/
reports/
```

Important report files:

```text
reports/pipeline_run_report.json
reports/pipeline_run_report.md
reports/data_quality_report.json
reports/data_quality_report.md
reports/formula_execution_report.json
reports/audit_report.json
reports/audit_report.md
```

Final data contains exactly 24 CSV files for v2.

Expected:

```text
Inventory.csv present
InventoryTransaction.csv present
InventoryBalance.csv absent
```

## 18. Environment and SQL Server Notes

Configuration is read from:

```text
.env
.env.example
```

Important SQL-related settings:

```text
DB_SERVER
DB_NAME
DB_SCHEMA
DB_DRIVER
DB_TRUSTED_CONNECTION
DB_USERNAME
DB_PASSWORD
IF_TABLE_EXISTS
BATCH_SIZE
```

SQL Server loading is optional and not required for tests.

During SQL connectivity exploration, `sqlcmd` was installed, but the environment could not connect to SQL Server due to an ODBC/client encryption/connectivity issue:

```text
Microsoft ODBC Driver 17 for SQL Server:
Encryption not supported on the client.
SSL Provider: No credentials are available in the security package.
Client unable to establish connection.
```

The SQL queries themselves are documented and were logically validated against generated CSV output with pandas-equivalent checks.

## 19. Key Design Decisions

1. Procurement v1 remains supported and unchanged as default.
2. Procurement v2 must be selected explicitly in UI/API/CLI.
3. InventoryTransaction is retained as detailed StockIn ledger.
4. Inventory is retained as calculated current stock balance.
5. InventoryBalance is excluded from v2.
6. LLM can generate plan JSON only, not rows.
7. Python owns row generation and all calculations.
8. Validation must fail on real lifecycle/quantity/status errors.
9. Row-count mismatches for derived lifecycle tables can be warnings when the generator refuses to fabricate invalid downstream rows.
10. SQL checks are manager-facing proof artifacts and must return zero issues when run on loaded valid data.

## 20. Known Acceptable Warnings

The final strict lifecycle generator may produce fewer rows than metadata target for quantity-bearing downstream tables:

```text
PurchaseOrderLine
POSchedule
ShipmentLine
GoodsReceiptLine
InspectionResult
InventoryTransaction
Inventory
```

Reason:

```text
The generator tracks and consumes upstream quantity.
When awarded quoted quantity, ordered quantity, shipped quantity, or accepted quantity is exhausted, it stops producing downstream positive quantity rows.
It does not create fake rows to hit target counts.
```

These warnings are acceptable only when:

```text
Errors = 0
All lifecycle quantity checks pass
All status consistency checks pass
Inventory reconciliation passes
InventoryBalance is absent
```

## 21. How to Demo the Project

Run backend sample-plan pipeline:

```powershell
python scripts/run_pipeline.py --metadata input/procurement_v2_metadata.xlsx --erd input/procurement_v2_erd.mmd --scenario input/procurement_v2_business_scenario.txt --plan input/sample_generation_plan_v2_valid.json --output output/v2_runs --seed 42 --load-sql false --build-prompt true --model-version v2
```

Run UI:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Use:

```text
Metadata: input/procurement_v2_metadata.xlsx
ERD: input/procurement_v2_erd.mmd
Scenario: input/procurement_v2_business_scenario.txt
Plan: input/sample_generation_plan_v2_valid.json
Model Version: Procurement v2
Load SQL: unchecked unless SQL Server is configured
Seed: 42
```

Expected:

```text
Pipeline status: passed or passed_with_warnings
Tables generated: 24
Data quality: passed or passed_with_warnings
Errors: 0
Inventory.csv included
InventoryBalance.csv absent
Final data ZIP downloads
Audit report downloads
Pipeline report downloads
```

## 22. Executive Summary

The project is now a complete Procurement v1/v2 synthetic data generation tool with:

```text
Metadata-driven schema understanding
Mermaid ERD validation
Azure OpenAI plan generation support
Safe JSON plan validation and normalization
Deterministic Python data generation
EV procurement financial realism
Strict procurement lifecycle quantity control
InventoryTransaction StockIn ledger
Inventory calculated stock balance
Formula execution
Final reconciliation and data quality reports
SQL Server load support
Manager-facing SQL validation packs
FastAPI UI/API
Artifact downloads
Comprehensive pytest coverage
```

The final critical procurement issue is fixed:

```text
No PO line can have StockIn quantity greater than OrderedQuantity.
No quotation line can be over-ordered by cumulative PO lines.
No partially stocked PO or PO line is marked Closed.
Statuses reflect actual lifecycle quantities and payments.
```

