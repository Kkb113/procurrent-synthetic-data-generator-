# Sales E2E Validation

Use this checklist to validate the full Procurement -> Production -> Sales MES flow for internal team testing.

## 1. Start The Frontend

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## 2. Frontend Selection

Use the default team flow:

- Procurement checked
- Production checked
- Sales checked
- Profile ID = `food_manufacturing`
- Seed = `42`
- Generate plan using Azure OpenAI = optional; leave unchecked for deterministic local validation
- Build prompt = checked
- Load to SQL = unchecked for the first run

## 3. First Run: Generate Without SQL

Run the pipeline with SQL loading disabled first.

Expected browser/API result:

- Procurement = 25 tables
- Production = 21 tables
- Sales = 18 tables
- Sales validation = passed
- Adjusted FinishedGoodsInventory = available
- SalesCreditMemo = not generated

## 4. Second Run: Generate With SQL Load

After the first run succeeds, run again with Load to SQL enabled using the target SQL Server connection settings.

Do not use SQL load as the first diagnostic step. Generation and validation should pass before loading to SQL.

## 5. SQL Validation

After loading the generated data, run:

```text
sql/mes_procurement_production_sales_validation.sql
```

Expected final status:

```text
SALES_E2E_VALIDATED
```

The SQL pack validates Procurement lifecycle, Production consumption and genealogy, Sales order/shipment/invoice/payment/returns, Sales shipment traceability, final FinishedGoodsInventory, and food-profile vocabulary.

## 6. Troubleshooting

- If EV, battery, or automotive terms appear, confirm `profile_id = food_manufacturing`.
- If Sales fails, check that Production generated `FinishedGoodsReceipt`, `FinishedGoodsInventory`, `ProductionBatch`, and `ProductionGenealogy`.
- If inventory validation fails, inspect Sales shipments, restocked returns, and active `Reserved` reservations.
- If traceability validation fails, inspect `SalesShipmentTraceability`, `ProductionGenealogy`, `MaterialIssueLine`, and `InventoryReceiptDetail`.
- If SQL load fails, rerun generation without SQL first, then retry SQL loading after generation passes.
