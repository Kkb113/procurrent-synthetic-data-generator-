# Synthetic Data Generation Tool - Project Documentation

Last updated: 2026-05-13

This repository generates realistic synthetic enterprise data from metadata, ERD, business scenario, and validated plan inputs. The current active system covers Procurement v2 and a separate Production Execution module within MES context. Deprecated Procurement V1 fixtures are archived for historical reference only and are no longer an active runnable model. Production is connected to Procurement data, but it is not a full MES platform. The current demo operating scope is simplified to one Plant, one Warehouse, and Production Shift A only.

## 1. Current Architecture

```text
Metadata XLSX + Mermaid ERD + Business Scenario + Plan JSON
-> validation
-> deterministic Python generation
-> formulas and reconciliation
-> audit/report artifacts
-> optional SQL Server load
```

Core code lives under `procurement_data_generator/core/`. Domain-specific logic lives under:

```text
procurement_data_generator/modules/procurement/
procurement_data_generator/modules/production/
procurement_data_generator/modules/shared/
```

Phase 1 module adapters are available through `procurement_data_generator/core/modules/`.
They register Procurement and Production as module plugins without changing the existing
Procurement runner or Production command-line workflow.

Phase 2 adds a generic pipeline runner foundation in `procurement_data_generator/core/pipeline/generic_runner.py`.
Existing Procurement and Production entry points remain supported; full Production execution through the generic runner is scheduled for a later phase.

Phase 3 introduces a normalized multi-module-capable LLM plan envelope while preserving legacy single-module plans. Prompt refactoring is intentionally deferred to Phase 4, and generator behavior remains unchanged.

Phase 4 introduces generic MES prompt assembly. Module-specific prompt sections are provided by module plugins; legacy Procurement prompt construction remains supported, generator behavior is unchanged, and Production full generic execution remains deferred to Phase 8.

Procurement v2 is the active FastAPI/backend Procurement pipeline. Production v1 has a dedicated command-line pipeline orchestration script, while the existing Procurement runner remains focused on Procurement v2.

## 2. Procurement v2 Completed State

Procurement v2 is complete and stable for the current 2025-only scope.

Current Procurement v2 behavior:

```text
25-table Procurement v2 model
InventoryReceiptDetail included
InventoryTransaction sourced from InventoryReceiptDetail
Inventory rolled up from InventoryTransaction
POStatus = Received only
LineStatus = Received only
InventoryBalance excluded
UOM-aware quantity precision implemented
Countable components use integer quantities
Bulk/measurable components may use decimals
SQL validation packs updated
Simplified operating scope: exactly one Plant and exactly one Warehouse
```

Procurement final flow:

```text
SupplierMaster / ComponentMaster / Plant / Warehouse
-> PurchaseRequisition
-> PurchaseReqLine
-> RFQHeader
-> RFQLine
-> SupplierQuotation
-> SupplierQuotationLn
-> PurchaseOrderHdr
-> PurchaseOrderLine
-> POSchedule
-> ShipmentHdr
-> ShipmentLine
-> GoodsReceiptHeader
-> GoodsReceiptLine
-> IncomingInspection
-> InspectionResult
-> InventoryReceiptDetail
-> InventoryTransaction
-> Inventory
```

Procurement v2 still also generates `SupplierComponent`, `SupplierInvoice`, and `PaymentTransaction`, bringing the final output to 25 CSV tables. `InventoryBalance.csv` must remain absent.

## 3. Production v1 Completed State

Production v1 is a Production Execution module within MES context. It is implemented through design fixtures, role/plan validation, master generation, transaction generation, reconciliation/data validation, a SQL validation pack, and a dedicated Production pipeline runner.

Production v1 uses the single upstream Procurement Plant and Warehouse. `ProductionShift` uses only `ShiftCode = A`; Shift B and Shift C are out of scope. Multiple WorkCenters remain valid inside the single Plant.

Current Production v1 capabilities:

```text
Production metadata/ERD/scenario/sample plans exist
Production role catalog and plan validation exist
Production master generation exists
Production transaction generation exists
Production reconciliation/data validation exists
Production SQL validation pack exists
Dedicated Production pipeline orchestration exists in scripts/run_production_pipeline.py
```

Production v1 has 21 tables.

Master/setup tables:

1. ProductMaster
2. BOMHeader
3. BOMLine
4. WorkCenter
5. RoutingHeader
6. RoutingOperation
7. ProductionShift

Transaction/execution tables:

8. ProductionOrderHdr
9. ProductionOrderLine
10. ProductionMaterialRequirement
11. MaterialIssueHeader
12. MaterialIssueLine
13. ProductionBatch
14. OperationExecution
15. ProductionQualityInspection
16. ProductionQualityResult
17. ScrapReworkEvent
18. FinishedGoodsReceipt
19. FinishedGoodsInventory
20. ProductionGenealogy
21. ProductionCostSummary

Production flow:

```text
Procurement Inventory
-> ProductionOrderHdr
-> ProductionOrderLine
-> ProductionMaterialRequirement
-> MaterialIssueHeader
-> MaterialIssueLine
-> ProductionBatch
-> OperationExecution
-> ProductionQualityInspection
-> ProductionQualityResult
-> ScrapReworkEvent
-> FinishedGoodsReceipt
-> FinishedGoodsInventory
-> ProductionGenealogy
-> ProductionCostSummary
```

Out of scope for Production v1:

```text
OEE
downtime
maintenance
labor tracking
scheduling optimization
warranty
service
sales/customer/distribution
full MES platform expansion
2026 or multi-year logic
```

## 4. Procurement-to-Production Integration

Procurement creates available component/material inventory. Production consumes that Procurement inventory, executes work orders and batches, creates finished goods, and traces finished goods back to consumed procurement receipt lineage.

Important upstream Procurement tables:

```text
ComponentMaster
Plant
Warehouse
Inventory
InventoryTransaction
InventoryReceiptDetail
SupplierMaster
```

Important Production integration tables:

```text
BOMLine
ProductionMaterialRequirement
MaterialIssueLine
ProductionGenealogy
FinishedGoodsReceipt
FinishedGoodsInventory
```

Key integrated flow:

```text
Inventory
-> MaterialIssueLine
-> ProductionGenealogy
-> FinishedGoodsReceipt
-> FinishedGoodsInventory
```

Traceability rule:

```text
ProductionGenealogy
-> MaterialIssueLine
-> InventoryReceiptDetail
-> InventoryTransaction
-> ComponentMaster / SupplierMaster
```

Production does not change Procurement `InventoryTransaction` into a StockOut table. Production has its own consumption ledger through `MaterialIssueHeader` and `MaterialIssueLine`.

## 5. Current Production Scripts

Create or refresh Production v1 design fixtures:

```powershell
python scripts/create_production_v1_fixtures.py
```

Step 1: run Procurement v2 pipeline.

```powershell
python scripts/run_pipeline.py --metadata input/procurement_v2_metadata.xlsx --erd input/procurement_v2_erd.mmd --scenario input/procurement_v2_business_scenario.txt --plan input/sample_generation_plan_v2_valid.json --output output/v2_runs --seed 42 --load-sql false --build-prompt true --model-version v2
```

Step 2: generate Production master data using Procurement `final_data`.

```powershell
python scripts/generate_production_master_data.py --metadata input/production_v1_metadata.xlsx --plan input/sample_generation_plan_production_v1_valid.json --output output/production_v1_master_data --seed 42 --upstream-data output/v2_runs/<procurement_run>/final_data
```

Step 3: generate Production transaction data.

```powershell
python scripts/generate_production_transaction_data.py --metadata input/production_v1_metadata.xlsx --plan input/sample_generation_plan_production_v1_valid.json --master-data output/production_v1_master_data --upstream-data output/v2_runs/<procurement_run>/final_data --output output/production_v1_transaction_data --seed 42
```

Step 4: validate Production data.

```powershell
python scripts/validate_production_generated_data.py --metadata input/production_v1_metadata.xlsx --plan input/sample_generation_plan_production_v1_valid.json --master-data output/production_v1_master_data --transaction-data output/production_v1_transaction_data --upstream-data output/v2_runs/<procurement_run>/final_data --output output/production_v1_validation
```

Step 5: use the manager-facing SQL validation pack after CSVs are loaded to SQL Server.

```text
docs/production_v1_sql_checks.sql
```

Dedicated Production pipeline command:

```powershell
python scripts/run_production_pipeline.py --metadata input/production_v1_metadata.xlsx --erd input/production_v1_erd.mmd --scenario input/production_v1_business_scenario.txt --plan input/sample_generation_plan_production_v1_valid.json --upstream-data output/v2_runs/<procurement_run>/final_data --output output/production_v1_runs --seed 42
```

## 6. SQL Validation Packs

Procurement SQL validation packs:

```text
docs/procurement_v2_inventory_sql_checks.sql
docs/procurement_v2_lifecycle_quantity_sql_checks.sql
```

Production SQL validation pack:

```text
docs/production_v1_sql_checks.sql
```

The Production SQL pack validates:

```text
21 Production tables
required upstream Procurement tables
Production master/setup lineage
Production order flow
material requirements and issue formulas
InventoryTransaction and InventoryReceiptDetail lineage
material issue inventory caps
operation, quality, scrap/rework formulas
FinishedGoodsReceipt formulas
FinishedGoodsInventory rollup
ProductionGenealogy traceability
ProductionCostSummary formulas
2025-only date scope
countable-UOM integer precision
final IssueName / IssueCount scorecard
```

## 7. Acceptable and Unacceptable Warnings

Acceptable Production warnings:

```text
Row-count warnings because Production skips unfulfillable demand instead of fabricating inventory.
Scrap/rework row counts below target because only some operations generate scrap/rework.
```

These warnings are acceptable only when:

```text
Errors = 0
all FKs are valid
all formulas pass
material issue does not exceed inventory
genealogy is complete
finished goods inventory rollup passes
cost summary passes
dates remain in 2025
UOM precision passes
```

Unacceptable warnings/errors:

```text
broken FK lineage
material issue exceeding inventory availability
invalid genealogy
invalid finished goods inventory rollup
invalid formulas
invalid UOM precision
invalid dates
missing required tables
```

## 8. FastAPI UI/API Status

The FastAPI UI/API currently runs the Procurement pipeline only.

Supported UI/API model versions:

```text
v2 active/default
```

Production v1 is documented in the UI as a command-line workflow only. Do not add `production_v1` as an active UI model option until a future UI/API phase intentionally wires the dedicated Production runner into the app.

## 9. Current Regression Commands

Run the normal local test baseline without SQL Server or live Azure OpenAI calls:

```powershell
pytest -m "not sql and not llm" -q
```

Run the full collected suite and stop at the first failure:

```powershell
pytest -q -x
```

Focused marker runs:

```powershell
pytest -m unit -q
pytest -m integration -q
pytest -m pipeline -q
pytest -m sql -q
pytest -m llm -q
```

The `sql` marker is for tests requiring SQL Server or database connectivity. The `llm` marker is for tests requiring live Azure OpenAI/LLM calls. These are excluded from normal local test runs unless explicitly requested. Tests should not depend on pre-existing generated CSVs under repo-level `output/` folders.

Run Production validation:

```powershell
python scripts/run_production_pipeline.py --metadata input/production_v1_metadata.xlsx --erd input/production_v1_erd.mmd --scenario input/production_v1_business_scenario.txt --plan input/sample_generation_plan_production_v1_valid.json --upstream-data output/v2_runs/<procurement_run>/final_data --output output/production_v1_runs --seed 42
```

Run Procurement v2 pipeline:

```powershell
python scripts/run_pipeline.py --metadata input/procurement_v2_metadata.xlsx --erd input/procurement_v2_erd.mmd --scenario input/procurement_v2_business_scenario.txt --plan input/sample_generation_plan_v2_valid.json --output output/v2_runs --seed 42 --load-sql false --build-prompt true --model-version v2
```

## 10. Current Stable Position

The repository now supports:

```text
Procurement v2 25-table supplier-to-inventory flow as the active Procurement model
Production v1 21-table Production Execution module within MES context
Procurement-to-Production traceability through inventory, receipt detail, stock-in transaction, component, and supplier lineage
shared UOM-aware quantity precision
Python reconciliation and data quality reports
manager-facing SQL validation packs
```

Phase 6 moved the main industry-specific generator assumptions behind `IndustryProfile` access while keeping the default EV profile backward compatible. Python still owns deterministic row generation, formulas, reconciliation, and validation; the LLM remains a planning-only component. The validation-layer split remains Phase 7, and full Production generic-runner execution remains Phase 8.
