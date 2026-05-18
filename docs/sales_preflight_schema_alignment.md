# Sales Phase 0: Preflight Schema Alignment

## Summary

Sales v1 can proceed to module skeleton design. The current Procurement and Production outputs provide the upstream finished-goods inventory, cost, batch, genealogy, material issue, supplier, and component lineage needed for an Order-to-Cash module.

There are no blocking upstream schema gaps for Sales Phase 1. Two naming details should be handled deliberately in the Sales v1 schema:

- Production lineage uses `SourceInventoryTransactionID` for the upstream procurement inventory transaction. If Sales names this field `InventoryTransactionID`, the generator should map it from `ProductionGenealogy.SourceInventoryTransactionID` or use the source name consistently.
- Procurement receipt cost/value fields use `DeliveredUnitPrice`, `AcceptedStockValue`, and `InventoryTransaction.UnitPrice` / `InventoryTransaction.InventoryValue`; there is no generic `UnitCost` column on `InventoryReceiptDetail`.

Sales must start from Production finished goods inventory. It must not consume raw Procurement `Inventory` directly.

## Planned Sales V1 Tables

Sales v1 will use these 18 tables:

1. `CustomerMaster`
2. `CustomerLocation`
3. `SalesChannel`
4. `SalesPriceListHeader`
5. `SalesPriceListLine`
6. `SalesOrderHdr`
7. `SalesOrderLine`
8. `SalesInventoryReservation`
9. `SalesPickListHeader`
10. `SalesPickListLine`
11. `SalesShipmentHeader`
12. `SalesShipmentLine`
13. `SalesInvoiceHeader`
14. `SalesInvoiceLine`
15. `CustomerPaymentReceipt`
16. `SalesReturnHeader`
17. `SalesReturnLine`
18. `SalesShipmentTraceability`

`SalesCreditMemo` is explicitly excluded from Sales v1. Returns are represented operationally by `SalesReturnHeader` and `SalesReturnLine`.

## Upstream Dependency Mapping

| Sales planned dependency | Expected upstream source table | Expected upstream source column | Actual source table | Actual source column | Status | Recommendation |
|---|---|---|---|---|---|---|
| ProductID | ProductMaster | ProductID | ProductMaster | ProductID | FOUND | Use for price list lines, orders, reservations, shipment lines, invoice lines, returns, and finished-goods inventory joins. |
| ProductID | FinishedGoodsInventory | ProductID | FinishedGoodsInventory | ProductID | FOUND | Use with PlantID and WarehouseID to reserve available finished goods. |
| ProductID | FinishedGoodsReceipt | ProductID | FinishedGoodsReceipt | ProductID | FOUND | Use for receipt-level COGS and shipment traceability. |
| PlantID | FinishedGoodsInventory | PlantID | FinishedGoodsInventory | PlantID | FOUND | Preserve current one-plant operating scope. |
| WarehouseID | FinishedGoodsInventory | WarehouseID | FinishedGoodsInventory | WarehouseID | FOUND | Preserve current one-warehouse operating scope. |
| FinishedGoodsInventoryID | FinishedGoodsInventory | FinishedGoodsInventoryID | FinishedGoodsInventory | FinishedGoodsInventoryID | FOUND | Sales reservations should reference this balance row. |
| FinishedGoodsReceiptID | FinishedGoodsReceipt | FinishedGoodsReceiptID | FinishedGoodsReceipt | FinishedGoodsReceiptID | FOUND | Sales shipments should allocate to receipt lots for cost and traceability. |
| FinishedGoodsReceiptID | ProductionGenealogy | FinishedGoodsReceiptID | ProductionGenealogy | FinishedGoodsReceiptID | FOUND | Use to connect customer shipments to consumed components. |
| ProductionBatchID | FinishedGoodsReceipt | ProductionBatchID | FinishedGoodsReceipt | ProductionBatchID | FOUND | Use to trace shipped finished goods to the production batch. |
| ProductionBatchID | ProductionBatch | ProductionBatchID | ProductionBatch | ProductionBatchID | FOUND | Use for batch-level traceability and production dates. |
| ProductionGenealogyID | ProductionGenealogy | ProductionGenealogyID | ProductionGenealogy | ProductionGenealogyID | FOUND | Use in SalesShipmentTraceability rows when expanding shipment lineage by consumed component. |
| MaterialIssueLineID | ProductionGenealogy | MaterialIssueLineID | ProductionGenealogy | MaterialIssueLineID | FOUND | Use to trace from finished goods back to production material consumption. |
| MaterialIssueLineID | MaterialIssueLine | MaterialIssueLineID | MaterialIssueLine | MaterialIssueLineID | FOUND | Use to retrieve issue cost and source procurement lineage. |
| InventoryReceiptDetailID | ProductionGenealogy | InventoryReceiptDetailID | ProductionGenealogy | InventoryReceiptDetailID | FOUND | Use to trace consumed material back to the procurement receipt detail. |
| InventoryReceiptDetailID | InventoryReceiptDetail | InventoryReceiptDetailID | InventoryReceiptDetail | InventoryReceiptDetailID | FOUND | Use for supplier/component receipt lineage. |
| InventoryTransactionID | ProductionGenealogy | InventoryTransactionID | ProductionGenealogy | SourceInventoryTransactionID | NAME_MISMATCH | Either name the Sales traceability field `SourceInventoryTransactionID` or map it to Sales `InventoryTransactionID`. |
| InventoryTransactionID | InventoryTransaction | InventoryTransactionID | InventoryTransaction | InventoryTransactionID | FOUND | Use with ProductionGenealogy.SourceInventoryTransactionID for source stock-in trace. |
| SupplierID | ProductionGenealogy | SupplierID | ProductionGenealogy | SupplierID | FOUND | Use for direct supplier lineage in SalesShipmentTraceability. |
| SupplierID | SupplierMaster | SupplierID | SupplierMaster | SupplierID | FOUND | Join to supplier master for traceability reporting. |
| ComponentID | ProductionGenealogy | ComponentID | ProductionGenealogy | ComponentID | FOUND | Use for component-level traceability. |
| ComponentID | ComponentMaster | ComponentID | ComponentMaster | ComponentID | FOUND | Join to component master for traceability reporting. |
| GoodQuantity | FinishedGoodsReceipt | GoodQuantity | FinishedGoodsReceipt | GoodQuantity | FOUND | Use as the receipt lot quantity available for Sales allocation. |
| GoodQuantity | ProductionOrderLine | GoodQuantity | ProductionOrderLine | GoodQuantity | FOUND | Use as a production validation cross-check. |
| UnitCost | FinishedGoodsReceipt | UnitCost | FinishedGoodsReceipt | UnitCost | FOUND | Use as primary Sales v1 COGS source. |
| UnitProductionCost | ProductionCostSummary | UnitProductionCost | ProductionCostSummary | UnitProductionCost | FOUND | Use as validation cross-check against FinishedGoodsReceipt.UnitCost. |
| OnHandQuantity | FinishedGoodsInventory | OnHandQuantity | FinishedGoodsInventory | OnHandQuantity | FOUND | Sales should reduce this by shipped quantity and add restocked returns. |
| ReservedQuantity | FinishedGoodsInventory | ReservedQuantity | FinishedGoodsInventory | ReservedQuantity | FOUND | Sales should include only active `Reserved` reservations. |
| AvailableQuantity | FinishedGoodsInventory | AvailableQuantity | FinishedGoodsInventory | AvailableQuantity | FOUND | Sales should calculate as OnHandQuantity minus ReservedQuantity. |
| OnHandValue | FinishedGoodsInventory | OnHandValue | FinishedGoodsInventory | OnHandValue | FOUND | Sales should recalculate after shipments/returns using receipt or average cost policy. |
| AcceptedQuantity | InventoryReceiptDetail | AcceptedQuantity | InventoryReceiptDetail | AcceptedQuantity | FOUND | Use for procurement receipt lineage validation only, not direct Sales stock consumption. |
| TransactionQuantity | InventoryTransaction | TransactionQuantity | InventoryTransaction | TransactionQuantity | FOUND | Use for source stock-in traceability validation where needed. |
| UnitCost or UnitPrice | InventoryReceiptDetail | UnitCost or UnitPrice | InventoryReceiptDetail | DeliveredUnitPrice | NAME_MISMATCH | Use `DeliveredUnitPrice` for receipt detail context or `InventoryTransaction.UnitPrice` for stock-in value checks. |
| UnitPrice | InventoryTransaction | UnitPrice | InventoryTransaction | UnitPrice | FOUND | Use for source inventory transaction cost context if Sales traceability needs it. |
| InventoryValue | InventoryTransaction | InventoryValue | InventoryTransaction | InventoryValue | FOUND | Use for source inventory transaction value checks. |
| InventoryValue | InventoryReceiptDetail | InventoryValue | InventoryReceiptDetail | AcceptedStockValue | NAME_MISMATCH | Use `AcceptedStockValue` when validating accepted receipt value. |

## COGS Recommendation

Use Option C:

- Generate Sales COGS from `FinishedGoodsReceipt.UnitCost`.
- Cross-check against `ProductionCostSummary.UnitProductionCost`.

This is the safest v1 approach because `FinishedGoodsReceipt` is the inventory receipt lot Sales will allocate from, and the current Production validation already checks that `FinishedGoodsReceipt.UnitCost` aligns with `ProductionCostSummary.UnitProductionCost`.

## FinishedGoodsInventory Update Recommendation

Sales should update finished goods balances after reservations, shipments, and returns:

```text
OnHandQuantity =
    SUM(FinishedGoodsReceipt.GoodQuantity)
    - SUM(SalesShipmentLine.ShippedQuantity)
    + SUM(SalesReturnLine.RestockedQuantity)

ReservedQuantity =
    SUM(SalesInventoryReservation.ReservedQuantity)
    WHERE ReservationStatus = 'Reserved'

AvailableQuantity =
    OnHandQuantity - ReservedQuantity
```

Reservation status semantics for v1:

- `Reserved` counts toward current reserved quantity.
- `Consumed` does not count as current reserved quantity.
- `Released` does not count as current reserved quantity.

The current `FinishedGoodsInventory` schema has the required fields: `FinishedGoodsInventoryID`, `ProductID`, `PlantID`, `WarehouseID`, `OnHandQuantity`, `ReservedQuantity`, `AvailableQuantity`, and `OnHandValue`.

One implementation detail: `FinishedGoodsInventory` is a product/plant/warehouse balance and does not store `FinishedGoodsReceiptID`. Sales shipment allocation should capture receipt-level allocation in `SalesShipmentLine` or `SalesShipmentTraceability` so COGS and lot traceability remain deterministic.

## Traceability Feasibility

Supplier-to-customer traceability is feasible with the current upstream schema:

```text
SalesShipmentLine
-> FinishedGoodsReceipt
-> ProductionBatch
-> ProductionGenealogy
-> MaterialIssueLine
-> InventoryReceiptDetail
-> InventoryTransaction, where available through SourceInventoryTransactionID
-> SupplierMaster
-> ComponentMaster
-> ProductMaster
```

No required lineage links are missing. The only naming detail is that Production genealogy calls the source procurement transaction `SourceInventoryTransactionID`, while a Sales table might prefer `InventoryTransactionID`.

## Generic Pipeline Readiness

The current architecture is ready for Sales without another major refactor:

- The module plugin contract supports module IDs, role catalogs, prompt sections, generators, validation, and upstream requirements.
- The generic runner already resolves registered modules through the module registry.
- The generic runner already supports dependency checks and upstream handoff for Procurement -> Production.
- Frontend/API metadata and ERD splitting already use module role catalogs for Procurement and Production.

Minimal future changes for Sales Phase 1 and later:

- Add an inert Sales module skeleton, role catalog, prompt sections, plugin, and validation placeholders.
- Register Sales only when its plugin is ready.
- Extend valid generic execution order to support `procurement,production,sales`.
- Reject invalid flows such as `sales`, `production,sales`, `procurement,sales`, `sales,production`, and `sales,procurement` unless explicit upstream data support is added.
- Extend runner upstream context from a single upstream path to a module output map, because Sales may need both Production final data and Procurement master/lineage tables.
- Extend module-aware metadata/ERD filtering so Sales receives Sales tables plus allowed upstream links to Production and Procurement lineage.

## Metadata And ERD Filtering Readiness

The existing generic web adapter already splits combined metadata by registered module role catalog and filters Mermaid ERD lines by allowed table names.

For Sales, the same mechanism should be extended so:

- Procurement receives only Procurement metadata and ERD relationships.
- Production receives Production metadata and ERD relationships plus allowed Procurement upstream links.
- Sales receives Sales metadata and ERD relationships plus allowed upstream links to:
  - `ProductMaster`
  - `FinishedGoodsInventory`
  - `FinishedGoodsReceipt`
  - `ProductionBatch`
  - `ProductionGenealogy`
  - `MaterialIssueLine`
  - `InventoryReceiptDetail`
  - `InventoryTransaction`
  - `SupplierMaster`
  - `ComponentMaster`

Do not require users to upload separate ERDs for each module.

## Industry Profile Readiness

The current `IndustryProfile` contract has `procurement`, `production`, and `shared` sections. It does not yet have a Sales-specific profile section.

Minimal future Sales profile additions should include:

- customer types or categories
- customer name patterns
- sales channels
- payment terms
- customer regions or route-to-market regions
- sales return reasons
- carrier or logistics names
- price, discount, tax, freight, and gross-margin policies

For food manufacturing, expected customer and channel vocabulary should include terms such as:

- Grocery Retailer
- Distributor
- Foodservice
- Convenience Store
- E-commerce
- Regional Wholesaler

Do not hardcode EV, automotive, dealer, or fleet vocabulary as generic Sales behavior.

## Recommended Next Phase

Proceed to Sales Phase 1: add the Sales module skeleton only.

Sales Phase 1 should add the module folder, role catalog, prompt sections, plugin shell, validation shell, and tests, but should not generate Sales data until the Sales schema and dependency mappings are finalized.

## Sales Phase 1 Note

Sales Phase 1 added the Sales module skeleton, Sales v1 role catalog, Sales plugin, prompt sections, validation placeholders, and generator placeholders. Sales is registered in the default module registry, but execution is intentionally not implemented yet.

## Sales Phase 2 Note

Sales Phase 2 added Sales v1 metadata and Mermaid ERD support. The metadata fixture contains exactly the 18 approved Sales v1 tables, excludes `SalesCreditMemo`, and can be validated against the Sales role catalog. Module-aware metadata and ERD filtering can now prepare Sales subsets with allowed upstream links for future Procurement -> Production -> Sales execution. Sales execution is still not implemented; the next phase is Sales Phase 3: Sales master data generator.

## Sales Phase 3 Note

Sales Phase 3 implemented deterministic Sales master/reference generation for `CustomerMaster`, `CustomerLocation`, `SalesChannel`, `SalesPriceListHeader`, and `SalesPriceListLine`. Price list lines require upstream Production `ProductMaster`; costs are used when available to price above unit cost. Customer, channel, payment, currency, and pricing hints are profile-driven. Sales transaction generation and full Sales pipeline execution remain disabled until later Sales phases.

## Sales Phase 4 Note

Sales Phase 4 implemented deterministic order, reservation, pick, and shipment generation for `SalesOrderHdr`, `SalesOrderLine`, `SalesInventoryReservation`, `SalesPickListHeader`, `SalesPickListLine`, `SalesShipmentHeader`, and `SalesShipmentLine`. The generator prevents overselling with internal FinishedGoodsInventory and FinishedGoodsReceipt allocation trackers, but it does not mutate or recalculate FinishedGoodsInventory yet. Invoice, payment, returns, shipment traceability, and full generic Sales execution remain disabled until later Sales phases.

## Sales Phase 5 Note

Sales Phase 5 implemented invoice and customer payment generation for `SalesInvoiceHeader`, `SalesInvoiceLine`, and `CustomerPaymentReceipt`. Invoices are sourced from Sales shipment lines, with deterministic COGS, gross margin, invoice totals, due dates, and fact-derived payment status. Returns, shipment traceability, FinishedGoodsInventory updates, and full generic Sales execution remain disabled until later Sales phases.

## Sales Phase 6 Note

Sales Phase 6 implemented deterministic low-volume customer returns for `SalesReturnHeader` and `SalesReturnLine`. Returns are generated from shipped Sales shipment lines, include food-profile return reasons, and split returned quantity into restocked and scrapped quantities for later inventory rollup. `SalesCreditMemo`, shipment traceability, FinishedGoodsInventory updates, and full generic Sales execution remain disabled until later Sales phases.

## Sales Phase 7 Note

Sales Phase 7 implemented deterministic shipment traceability for `SalesShipmentTraceability`. It links Sales shipment lines to `FinishedGoodsReceipt`, `ProductionBatch`, `ProductionGenealogy`, `MaterialIssueLine`, `InventoryReceiptDetail`, `SupplierMaster`, and `ComponentMaster`, and calculates `AllocatedConsumedQuantity` as `ProductionGenealogy.ConsumedQuantity * SalesShipmentLine.ShippedQuantity / FinishedGoodsReceipt.GoodQuantity`. FinishedGoodsInventory updates and full generic Sales execution remain disabled until later Sales phases.
