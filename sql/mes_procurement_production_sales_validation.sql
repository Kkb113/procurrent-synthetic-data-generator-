/*
MES Procurement -> Production -> Sales SQL validation pack.

Target database: SQL Server / T-SQL, generated tables loaded under dbo.

Purpose:
Validate the complete internal MES synthetic dataset after the browser/API or
CLI generates and loads the final combined output.

Expected usage:
- Run after generated CSVs are loaded to SQL Server.
- Detail checks should return zero rows unless a section says it is a summary.
- Final readiness should return SALES_E2E_VALIDATED.
- SalesCreditMemo is not part of Sales v1 and is not required by this pack.

Validated flow:
Supplier -> Procurement -> Raw/Component Inventory -> Production
-> Finished Goods Inventory -> Sales Order -> Shipment -> Invoice
-> Payment -> Customer

Traceability:
Customer Shipment -> FinishedGoodsReceipt -> ProductionBatch
-> ProductionGenealogy -> MaterialIssueLine -> InventoryReceiptDetail
-> SupplierMaster -> ComponentMaster
*/

/* ============================================================
SECTION 1 - TABLE PRESENCE AND ROW-COUNT READINESS
============================================================ */

-- 1A. Expected v1 table presence. Expected: no rows.
WITH ExpectedTables AS (
    SELECT ModuleName, TableName
    FROM (VALUES
        ('Procurement', 'SupplierMaster'),
        ('Procurement', 'SupplierComponent'),
        ('Procurement', 'ComponentMaster'),
        ('Procurement', 'Plant'),
        ('Procurement', 'Warehouse'),
        ('Procurement', 'PurchaseRequisition'),
        ('Procurement', 'PurchaseReqLine'),
        ('Procurement', 'RFQHeader'),
        ('Procurement', 'RFQLine'),
        ('Procurement', 'SupplierQuotation'),
        ('Procurement', 'SupplierQuotationLn'),
        ('Procurement', 'PurchaseOrderHdr'),
        ('Procurement', 'PurchaseOrderLine'),
        ('Procurement', 'POSchedule'),
        ('Procurement', 'ShipmentHdr'),
        ('Procurement', 'ShipmentLine'),
        ('Procurement', 'GoodsReceiptHeader'),
        ('Procurement', 'GoodsReceiptLine'),
        ('Procurement', 'IncomingInspection'),
        ('Procurement', 'InspectionResult'),
        ('Procurement', 'InventoryReceiptDetail'),
        ('Procurement', 'InventoryTransaction'),
        ('Procurement', 'Inventory'),
        ('Procurement', 'SupplierInvoice'),
        ('Procurement', 'PaymentTransaction'),
        ('Production', 'ProductMaster'),
        ('Production', 'BOMHeader'),
        ('Production', 'BOMLine'),
        ('Production', 'WorkCenter'),
        ('Production', 'RoutingHeader'),
        ('Production', 'RoutingOperation'),
        ('Production', 'ProductionShift'),
        ('Production', 'ProductionOrderHdr'),
        ('Production', 'ProductionOrderLine'),
        ('Production', 'ProductionMaterialRequirement'),
        ('Production', 'MaterialIssueHeader'),
        ('Production', 'MaterialIssueLine'),
        ('Production', 'ProductionBatch'),
        ('Production', 'OperationExecution'),
        ('Production', 'ProductionQualityInspection'),
        ('Production', 'ProductionQualityResult'),
        ('Production', 'ScrapReworkEvent'),
        ('Production', 'FinishedGoodsReceipt'),
        ('Production', 'FinishedGoodsInventory'),
        ('Production', 'ProductionGenealogy'),
        ('Production', 'ProductionCostSummary'),
        ('Sales', 'CustomerMaster'),
        ('Sales', 'CustomerLocation'),
        ('Sales', 'SalesChannel'),
        ('Sales', 'SalesPriceListHeader'),
        ('Sales', 'SalesPriceListLine'),
        ('Sales', 'SalesOrderHdr'),
        ('Sales', 'SalesOrderLine'),
        ('Sales', 'SalesInventoryReservation'),
        ('Sales', 'SalesPickListHeader'),
        ('Sales', 'SalesPickListLine'),
        ('Sales', 'SalesShipmentHeader'),
        ('Sales', 'SalesShipmentLine'),
        ('Sales', 'SalesInvoiceHeader'),
        ('Sales', 'SalesInvoiceLine'),
        ('Sales', 'CustomerPaymentReceipt'),
        ('Sales', 'SalesReturnHeader'),
        ('Sales', 'SalesReturnLine'),
        ('Sales', 'SalesShipmentTraceability')
    ) v(ModuleName, TableName)
)
SELECT e.ModuleName, e.TableName AS MissingTable
FROM ExpectedTables e
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
WHERE t.TABLE_NAME IS NULL;

-- 1B. Expected module table counts from metadata. Expected: 25, 21, 18.
WITH ExpectedTables AS (
    SELECT ModuleName, TableName
    FROM (VALUES
        ('Procurement', 'SupplierMaster'), ('Procurement', 'SupplierComponent'), ('Procurement', 'ComponentMaster'),
        ('Procurement', 'Plant'), ('Procurement', 'Warehouse'), ('Procurement', 'PurchaseRequisition'),
        ('Procurement', 'PurchaseReqLine'), ('Procurement', 'RFQHeader'), ('Procurement', 'RFQLine'),
        ('Procurement', 'SupplierQuotation'), ('Procurement', 'SupplierQuotationLn'), ('Procurement', 'PurchaseOrderHdr'),
        ('Procurement', 'PurchaseOrderLine'), ('Procurement', 'POSchedule'), ('Procurement', 'ShipmentHdr'),
        ('Procurement', 'ShipmentLine'), ('Procurement', 'GoodsReceiptHeader'), ('Procurement', 'GoodsReceiptLine'),
        ('Procurement', 'IncomingInspection'), ('Procurement', 'InspectionResult'), ('Procurement', 'InventoryReceiptDetail'),
        ('Procurement', 'InventoryTransaction'), ('Procurement', 'Inventory'), ('Procurement', 'SupplierInvoice'),
        ('Procurement', 'PaymentTransaction'),
        ('Production', 'ProductMaster'), ('Production', 'BOMHeader'), ('Production', 'BOMLine'),
        ('Production', 'WorkCenter'), ('Production', 'RoutingHeader'), ('Production', 'RoutingOperation'),
        ('Production', 'ProductionShift'), ('Production', 'ProductionOrderHdr'), ('Production', 'ProductionOrderLine'),
        ('Production', 'ProductionMaterialRequirement'), ('Production', 'MaterialIssueHeader'), ('Production', 'MaterialIssueLine'),
        ('Production', 'ProductionBatch'), ('Production', 'OperationExecution'), ('Production', 'ProductionQualityInspection'),
        ('Production', 'ProductionQualityResult'), ('Production', 'ScrapReworkEvent'), ('Production', 'FinishedGoodsReceipt'),
        ('Production', 'FinishedGoodsInventory'), ('Production', 'ProductionGenealogy'), ('Production', 'ProductionCostSummary'),
        ('Sales', 'CustomerMaster'), ('Sales', 'CustomerLocation'), ('Sales', 'SalesChannel'),
        ('Sales', 'SalesPriceListHeader'), ('Sales', 'SalesPriceListLine'), ('Sales', 'SalesOrderHdr'),
        ('Sales', 'SalesOrderLine'), ('Sales', 'SalesInventoryReservation'), ('Sales', 'SalesPickListHeader'),
        ('Sales', 'SalesPickListLine'), ('Sales', 'SalesShipmentHeader'), ('Sales', 'SalesShipmentLine'),
        ('Sales', 'SalesInvoiceHeader'), ('Sales', 'SalesInvoiceLine'), ('Sales', 'CustomerPaymentReceipt'),
        ('Sales', 'SalesReturnHeader'), ('Sales', 'SalesReturnLine'), ('Sales', 'SalesShipmentTraceability')
    ) v(ModuleName, TableName)
)
SELECT e.ModuleName,
       COUNT(*) AS ExpectedTableCount,
       SUM(CASE WHEN t.TABLE_NAME IS NOT NULL THEN 1 ELSE 0 END) AS PresentTableCount
FROM ExpectedTables e
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
GROUP BY e.ModuleName
ORDER BY e.ModuleName;

-- 1C. Row-count readiness summary. Expected: required operational tables > 0.
SELECT 'SupplierMaster' AS TableName, COUNT(*) AS [RowCount] FROM dbo.SupplierMaster
UNION ALL SELECT 'PurchaseOrderLine', COUNT(*) FROM dbo.PurchaseOrderLine
UNION ALL SELECT 'InventoryReceiptDetail', COUNT(*) FROM dbo.InventoryReceiptDetail
UNION ALL SELECT 'InventoryTransaction', COUNT(*) FROM dbo.InventoryTransaction
UNION ALL SELECT 'Inventory', COUNT(*) FROM dbo.Inventory
UNION ALL SELECT 'ProductMaster', COUNT(*) FROM dbo.ProductMaster
UNION ALL SELECT 'MaterialIssueLine', COUNT(*) FROM dbo.MaterialIssueLine
UNION ALL SELECT 'FinishedGoodsReceipt', COUNT(*) FROM dbo.FinishedGoodsReceipt
UNION ALL SELECT 'ProductionGenealogy', COUNT(*) FROM dbo.ProductionGenealogy
UNION ALL SELECT 'FinishedGoodsInventory', COUNT(*) FROM dbo.FinishedGoodsInventory
UNION ALL SELECT 'CustomerMaster', COUNT(*) FROM dbo.CustomerMaster
UNION ALL SELECT 'SalesOrderLine', COUNT(*) FROM dbo.SalesOrderLine
UNION ALL SELECT 'SalesShipmentLine', COUNT(*) FROM dbo.SalesShipmentLine
UNION ALL SELECT 'SalesInvoiceHeader', COUNT(*) FROM dbo.SalesInvoiceHeader
UNION ALL SELECT 'CustomerPaymentReceipt', COUNT(*) FROM dbo.CustomerPaymentReceipt
UNION ALL SELECT 'SalesReturnHeader', COUNT(*) FROM dbo.SalesReturnHeader
UNION ALL SELECT 'SalesReturnLine', COUNT(*) FROM dbo.SalesReturnLine
UNION ALL SELECT 'SalesShipmentTraceability', COUNT(*) FROM dbo.SalesShipmentTraceability;

-- 1D. SalesCreditMemo is excluded from Sales v1. Expected: SalesCreditMemoObjectCount = 0.
SELECT COUNT(*) AS SalesCreditMemoObjectCount
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'SalesCreditMemo';

/* ============================================================
SECTION 2 - PROCUREMENT LIFECYCLE VALIDATION
============================================================ */

-- 2A. Procurement quantity chain. Expected: failed_rows = 0.
SELECT COUNT(*) AS failed_rows
FROM dbo.PurchaseOrderLine pol
JOIN dbo.SupplierQuotationLn ql ON ql.QuotationLineID = pol.QuotationLineID
JOIN dbo.RFQLine rl ON rl.RFQLineID = ql.RFQLineID
JOIN dbo.PurchaseReqLine prl ON prl.RequisitionLineID = rl.RequisitionLineID
JOIN dbo.POSchedule ps ON ps.PurchaseOrderLineID = pol.PurchaseOrderLineID
JOIN dbo.ShipmentLine sl ON sl.POScheduleID = ps.POScheduleID
JOIN dbo.GoodsReceiptLine grl ON grl.ShipmentLineID = sl.ShipmentLineID
JOIN dbo.IncomingInspection ii ON ii.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN dbo.InspectionResult ir ON ir.InspectionID = ii.InspectionID
WHERE prl.RequestedQuantity < rl.RFQQuantity
   OR rl.RFQQuantity < ql.QuotedQuantity
   OR ql.QuotedQuantity < pol.OrderedQuantity
   OR pol.OrderedQuantity < ps.ScheduledQuantity
   OR ps.ScheduledQuantity < sl.ShippedQuantity
   OR sl.ShippedQuantity < grl.ReceivedQuantity
   OR grl.ReceivedQuantity < ir.InspectedQuantity
   OR ir.InspectedQuantity < ir.AcceptedQuantity;

-- 2B. Accepted quantity posted to InventoryTransaction. Expected: no rows.
SELECT ir.InspectionResultID,
       ir.AcceptedQuantity,
       it.TransactionQuantity
FROM dbo.InspectionResult ir
JOIN dbo.InventoryTransaction it ON it.InspectionResultID = ir.InspectionResultID
WHERE ABS(COALESCE(it.TransactionQuantity, 0) - COALESCE(ir.AcceptedQuantity, 0)) > 0.01;

/* ============================================================
SECTION 3 - PROCUREMENT RECONCILIATION VALIDATION
============================================================ */

-- 3A. PO line amount formula. Expected: no rows.
SELECT PurchaseOrderLineID, OrderedQuantity, UnitPrice, LineAmount
FROM dbo.PurchaseOrderLine
WHERE ABS(COALESCE(LineAmount, 0) - COALESCE(OrderedQuantity, 0) * COALESCE(UnitPrice, 0)) > 0.01;

-- 3B. Goods receipt quantities do not exceed shipped quantity. Expected: no rows.
SELECT GoodsReceiptLineID, ShippedQuantity, ReceivedQuantity
FROM dbo.GoodsReceiptLine
WHERE COALESCE(ReceivedQuantity, 0) > COALESCE(ShippedQuantity, 0) + 0.01;

-- 3C. Inspection accepted + rejected = inspected. Expected: no rows.
SELECT InspectionResultID, InspectedQuantity, AcceptedQuantity, RejectedQuantity
FROM dbo.InspectionResult
WHERE ABS(COALESCE(InspectedQuantity, 0) - COALESCE(AcceptedQuantity, 0) - COALESCE(RejectedQuantity, 0)) > 0.01;

-- 3D. InventoryTransaction value formula. Expected: no rows.
SELECT InventoryTransactionID, TransactionQuantity, UnitPrice, InventoryValue
FROM dbo.InventoryTransaction
WHERE ABS(COALESCE(InventoryValue, 0) - COALESCE(TransactionQuantity, 0) * COALESCE(UnitPrice, 0)) > 0.01;

-- 3E. Inventory rollup from InventoryTransaction. Expected: no rows.
WITH TxnRollup AS (
    SELECT ComponentID,
           PlantID,
           WarehouseID,
           SUM(TransactionQuantity) AS TransactionQuantity,
           SUM(InventoryValue) AS InventoryValue
    FROM dbo.InventoryTransaction
    GROUP BY ComponentID, PlantID, WarehouseID
)
SELECT i.InventoryID,
       i.ComponentID,
       i.PlantID,
       i.WarehouseID,
       i.OnHandQuantity,
       r.TransactionQuantity,
       i.OnHandValue,
       r.InventoryValue
FROM dbo.Inventory i
JOIN TxnRollup r
  ON r.ComponentID = i.ComponentID
 AND r.PlantID = i.PlantID
 AND r.WarehouseID = i.WarehouseID
WHERE ABS(COALESCE(i.OnHandQuantity, 0) - COALESCE(r.TransactionQuantity, 0)) > 0.01
   OR ABS(COALESCE(i.OnHandValue, 0) - COALESCE(r.InventoryValue, 0)) > 0.01
   OR ABS(COALESCE(i.AvailableQuantity, 0) - (COALESCE(i.OnHandQuantity, 0) - COALESCE(i.ReservedQuantity, 0))) > 0.01;

-- 3F. SupplierInvoice total formula. Expected: no rows.
SELECT SupplierInvoiceID, InvoiceAmount, TaxAmount, FreightAmount, TotalInvoiceAmount
FROM dbo.SupplierInvoice
WHERE ABS(COALESCE(TotalInvoiceAmount, 0)
        - (COALESCE(InvoiceAmount, 0) + COALESCE(TaxAmount, 0) + COALESCE(FreightAmount, 0))) > 0.01;

-- 3G. Supplier payment total does not exceed invoice total. Expected: no rows.
WITH PaymentRollup AS (
    SELECT SupplierInvoiceID, SUM(PaymentAmount) AS PaidAmount
    FROM dbo.PaymentTransaction
    GROUP BY SupplierInvoiceID
)
SELECT si.SupplierInvoiceID, si.TotalInvoiceAmount, p.PaidAmount
FROM dbo.SupplierInvoice si
JOIN PaymentRollup p ON p.SupplierInvoiceID = si.SupplierInvoiceID
WHERE COALESCE(p.PaidAmount, 0) > COALESCE(si.TotalInvoiceAmount, 0) + 0.01;

-- 3H. InventoryReceiptDetail price variance formula. Expected: no rows.
-- Negative PriceDifference / PriceDifferencePct is a valid favorable variance, not an error.
SELECT InventoryReceiptDetailID,
       OrderedUnitPrice,
       DeliveredUnitPrice,
       PriceDifference,
       PriceDifferencePct
FROM dbo.InventoryReceiptDetail
WHERE ABS(COALESCE(PriceDifference, 0) - ROUND(COALESCE(DeliveredUnitPrice, 0) - COALESCE(OrderedUnitPrice, 0), 2)) > 0.01
   OR ABS(
        COALESCE(PriceDifferencePct, 0)
        - CASE
              WHEN COALESCE(OrderedUnitPrice, 0) = 0 THEN 0
              ELSE ROUND((COALESCE(PriceDifference, 0) / NULLIF(OrderedUnitPrice, 0)) * 100.0, 2)
          END
      ) > 0.01;

/* ============================================================
SECTION 4 - PRODUCTION MATERIAL CONSUMPTION VALIDATION
============================================================ */

-- 4A. Requirement issued quantity does not exceed scrap-adjusted requirement. Expected: no rows.
SELECT MaterialRequirementID, ScrapAdjustedQuantity, IssuedQuantity
FROM dbo.ProductionMaterialRequirement
WHERE COALESCE(IssuedQuantity, 0) > COALESCE(ScrapAdjustedQuantity, 0) + 0.01;

-- 4B. MaterialIssueLine sum equals requirement issued quantity. Expected: no rows.
WITH IssueRollup AS (
    SELECT MaterialRequirementID, SUM(IssuedQuantity) AS IssuedQuantity
    FROM dbo.MaterialIssueLine
    GROUP BY MaterialRequirementID
)
SELECT pmr.MaterialRequirementID,
       pmr.IssuedQuantity AS RequirementIssuedQuantity,
       r.IssuedQuantity AS LineIssuedQuantity
FROM dbo.ProductionMaterialRequirement pmr
LEFT JOIN IssueRollup r ON r.MaterialRequirementID = pmr.MaterialRequirementID
WHERE ABS(COALESCE(pmr.IssuedQuantity, 0) - COALESCE(r.IssuedQuantity, 0)) > 0.01;

-- 4C. Material issue value formula. Expected: no rows.
SELECT MaterialIssueLineID, IssuedQuantity, UnitCost, IssueValue
FROM dbo.MaterialIssueLine
WHERE ABS(COALESCE(IssueValue, 0) - COALESCE(IssuedQuantity, 0) * COALESCE(UnitCost, 0)) > 0.01;

-- 4D. Material consumption does not exceed source Procurement StockIn. Expected: no rows.
WITH IssueByTransaction AS (
    SELECT SourceInventoryTransactionID, SUM(IssuedQuantity) AS IssuedQuantity
    FROM dbo.MaterialIssueLine
    GROUP BY SourceInventoryTransactionID
)
SELECT i.SourceInventoryTransactionID,
       i.IssuedQuantity,
       it.TransactionQuantity
FROM IssueByTransaction i
JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = i.SourceInventoryTransactionID
WHERE COALESCE(i.IssuedQuantity, 0) > COALESCE(it.TransactionQuantity, 0) + 0.01;

-- 4E. Every material issue line has source InventoryTransaction and InventoryReceiptDetail. Expected: no rows.
SELECT mil.MaterialIssueLineID,
       mil.SourceInventoryTransactionID,
       mil.InventoryReceiptDetailID
FROM dbo.MaterialIssueLine mil
LEFT JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = mil.SourceInventoryTransactionID
LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = mil.InventoryReceiptDetailID
WHERE it.InventoryTransactionID IS NULL
   OR ird.InventoryReceiptDetailID IS NULL;

/* ============================================================
SECTION 5 - PRODUCTION FINISHED GOODS, GENEALOGY, AND COST VALIDATION
============================================================ */

-- 5A. OperationExecution flow and quantity semantics. Expected: no rows.
-- ReworkQuantity is non-additive: it is a subset of OutputQuantity routed through rework,
-- so the valid loss formula is OutputQuantity = InputQuantity - ScrapQuantity.
WITH OrderedOperations AS (
    SELECT oe.OperationExecutionID,
           oe.ProductionBatchID,
           oe.OperationSequence,
           oe.InputQuantity,
           oe.OutputQuantity,
           oe.ScrapQuantity,
           oe.ReworkQuantity,
           pb.PlannedBatchQuantity,
           LAG(oe.OutputQuantity) OVER (
               PARTITION BY oe.ProductionBatchID
               ORDER BY oe.OperationSequence
           ) AS PreviousOutputQuantity,
           ROW_NUMBER() OVER (
               PARTITION BY oe.ProductionBatchID
               ORDER BY oe.OperationSequence
           ) AS OperationRank
    FROM dbo.OperationExecution oe
    JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = oe.ProductionBatchID
)
SELECT OperationExecutionID,
       ProductionBatchID,
       InputQuantity,
       OutputQuantity,
       ScrapQuantity,
       ReworkQuantity,
       PreviousOutputQuantity
FROM OrderedOperations
WHERE InputQuantity < 0
   OR OutputQuantity < 0
   OR ScrapQuantity < 0
   OR ReworkQuantity < 0
   OR (OperationRank = 1 AND ABS(COALESCE(InputQuantity, 0) - COALESCE(PlannedBatchQuantity, 0)) > 0.01)
   OR (OperationRank > 1 AND ABS(COALESCE(InputQuantity, 0) - COALESCE(PreviousOutputQuantity, 0)) > 0.01)
   OR ABS(COALESCE(OutputQuantity, 0) - (COALESCE(InputQuantity, 0) - COALESCE(ScrapQuantity, 0))) > 0.01
   OR COALESCE(ReworkQuantity, 0) > COALESCE(OutputQuantity, 0) + 0.01;

-- 5B. FinishedGoodsReceipt value formula. Expected: no rows.
SELECT FinishedGoodsReceiptID, GoodQuantity, UnitCost, ReceiptValue
FROM dbo.FinishedGoodsReceipt
WHERE ABS(COALESCE(ReceiptValue, 0) - COALESCE(GoodQuantity, 0) * COALESCE(UnitCost, 0)) > 0.01;

-- 5C. Production genealogy links to FinishedGoodsReceipt and MaterialIssueLine. Expected: no rows.
SELECT pg.ProductionGenealogyID,
       pg.FinishedGoodsReceiptID,
       pg.MaterialIssueLineID
FROM dbo.ProductionGenealogy pg
LEFT JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = pg.FinishedGoodsReceiptID
LEFT JOIN dbo.MaterialIssueLine mil ON mil.MaterialIssueLineID = pg.MaterialIssueLineID
WHERE fgr.FinishedGoodsReceiptID IS NULL
   OR mil.MaterialIssueLineID IS NULL;

-- 5D. Genealogy consumed quantity does not exceed material issued quantity. Expected: no rows.
WITH GenealogyByIssue AS (
    SELECT MaterialIssueLineID, SUM(ConsumedQuantity) AS ConsumedQuantity
    FROM dbo.ProductionGenealogy
    GROUP BY MaterialIssueLineID
)
SELECT mil.MaterialIssueLineID,
       mil.IssuedQuantity,
       g.ConsumedQuantity
FROM dbo.MaterialIssueLine mil
JOIN GenealogyByIssue g ON g.MaterialIssueLineID = mil.MaterialIssueLineID
WHERE COALESCE(g.ConsumedQuantity, 0) > COALESCE(mil.IssuedQuantity, 0) + 0.01;

-- 5E. ProductionCostSummary total formula. Expected: no rows.
SELECT ProductionCostSummaryID,
       MaterialCost,
       LaborCost,
       OverheadCost,
       ScrapCost,
       TotalProductionCost
FROM dbo.ProductionCostSummary
WHERE ABS(COALESCE(TotalProductionCost, 0)
        - (COALESCE(MaterialCost, 0) + COALESCE(LaborCost, 0) + COALESCE(OverheadCost, 0) + COALESCE(ScrapCost, 0))) > 0.01;

-- 5F. ProductionCostSummary unit production cost. Expected: no rows.
WITH BatchGoodQty AS (
    SELECT ProductionBatchID, SUM(GoodQuantity) AS GoodQuantity
    FROM dbo.FinishedGoodsReceipt
    GROUP BY ProductionBatchID
)
SELECT pcs.ProductionCostSummaryID,
       pcs.ProductionBatchID,
       pcs.TotalProductionCost,
       pcs.UnitProductionCost,
       b.GoodQuantity
FROM dbo.ProductionCostSummary pcs
JOIN BatchGoodQty b ON b.ProductionBatchID = pcs.ProductionBatchID
WHERE b.GoodQuantity <= 0
   OR ABS(COALESCE(pcs.UnitProductionCost, 0) - COALESCE(pcs.TotalProductionCost, 0) / NULLIF(b.GoodQuantity, 0)) > 0.01;

/* ============================================================
SECTION 6 - SALES MASTER/REFERENCE VALIDATION
============================================================ */

-- 6A. CustomerLocation.CustomerID references CustomerMaster. Expected: no rows.
SELECT cl.CustomerLocationID, cl.CustomerID
FROM dbo.CustomerLocation cl
LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = cl.CustomerID
WHERE cm.CustomerID IS NULL;

-- 6B. At least one location per customer. Expected: no rows.
SELECT cm.CustomerID
FROM dbo.CustomerMaster cm
LEFT JOIN dbo.CustomerLocation cl ON cl.CustomerID = cm.CustomerID
GROUP BY cm.CustomerID
HAVING COUNT(cl.CustomerLocationID) = 0;

-- 6C. SalesPriceListLine references header and ProductMaster. Expected: no rows.
SELECT spl.PriceListLineID, spl.PriceListID, spl.ProductID
FROM dbo.SalesPriceListLine spl
LEFT JOIN dbo.SalesPriceListHeader sph ON sph.PriceListID = spl.PriceListID
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = spl.ProductID
WHERE sph.PriceListID IS NULL
   OR pm.ProductID IS NULL;

-- 6D. SalesChannel IDs referenced by SalesOrderHdr exist. Expected: no rows.
SELECT soh.SalesOrderID, soh.SalesChannelID
FROM dbo.SalesOrderHdr soh
LEFT JOIN dbo.SalesChannel sc ON sc.SalesChannelID = soh.SalesChannelID
WHERE sc.SalesChannelID IS NULL;

/* ============================================================
SECTION 7 - SALES ORDER/RESERVATION/PICK/SHIPMENT VALIDATION
============================================================ */

-- 7A. SalesOrderHdr references customer, locations, and channel. Expected: no rows.
SELECT soh.SalesOrderID
FROM dbo.SalesOrderHdr soh
LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = soh.CustomerID
LEFT JOIN dbo.CustomerLocation bill ON bill.CustomerLocationID = soh.BillToLocationID
LEFT JOIN dbo.CustomerLocation ship ON ship.CustomerLocationID = soh.ShipToLocationID
LEFT JOIN dbo.SalesChannel sc ON sc.SalesChannelID = soh.SalesChannelID
WHERE cm.CustomerID IS NULL
   OR bill.CustomerLocationID IS NULL
   OR ship.CustomerLocationID IS NULL
   OR bill.CustomerID <> soh.CustomerID
   OR ship.CustomerID <> soh.CustomerID
   OR sc.SalesChannelID IS NULL;

-- 7B. SalesOrderLine quantity lifecycle and financial formulas. Expected: no rows.
SELECT SalesOrderLineID,
       OrderedQuantity,
       ReservedQuantity,
       ShippedQuantity,
       BackorderQuantity,
       UnitPrice,
       DiscountPct,
       LineAmount,
       DiscountAmount,
       NetLineAmount
FROM dbo.SalesOrderLine
WHERE OrderedQuantity < 0
   OR ReservedQuantity < 0
   OR ShippedQuantity < 0
   OR BackorderQuantity < 0
   OR OrderedQuantity + 0.01 < ReservedQuantity
   OR ReservedQuantity + 0.01 < ShippedQuantity
   OR ABS(COALESCE(BackorderQuantity, 0) - (COALESCE(OrderedQuantity, 0) - COALESCE(ShippedQuantity, 0))) > 0.01
   OR ABS(COALESCE(LineAmount, 0) - COALESCE(OrderedQuantity, 0) * COALESCE(UnitPrice, 0)) > 0.01
   OR ABS(COALESCE(DiscountAmount, 0) - COALESCE(LineAmount, 0) * COALESCE(DiscountPct, 0) / 100.0) > 0.01
   OR ABS(COALESCE(NetLineAmount, 0) - (COALESCE(LineAmount, 0) - COALESCE(DiscountAmount, 0))) > 0.01;

-- 7C. Reservation FKs and product/plant/warehouse alignment. Expected: no rows.
SELECT sir.ReservationID
FROM dbo.SalesInventoryReservation sir
LEFT JOIN dbo.SalesOrderLine sol ON sol.SalesOrderLineID = sir.SalesOrderLineID
LEFT JOIN dbo.FinishedGoodsInventory fgi ON fgi.FinishedGoodsInventoryID = sir.FinishedGoodsInventoryID
WHERE sol.SalesOrderLineID IS NULL
   OR fgi.FinishedGoodsInventoryID IS NULL
   OR sol.ProductID <> sir.ProductID
   OR sol.PlantID <> sir.PlantID
   OR sol.WarehouseID <> sir.WarehouseID
   OR fgi.ProductID <> sir.ProductID
   OR fgi.PlantID <> sir.PlantID
   OR fgi.WarehouseID <> sir.WarehouseID
   OR sir.ReservedQuantity < 0
   OR sir.ReleasedQuantity < 0
   OR sir.ReservedQuantity > sol.OrderedQuantity + 0.01;

-- 7D. Pick quantity does not exceed reserved quantity. Expected: no rows.
SELECT pll.PickListLineID,
       pll.PickedQuantity,
       sir.ReservedQuantity
FROM dbo.SalesPickListLine pll
JOIN dbo.SalesInventoryReservation sir ON sir.ReservationID = pll.ReservationID
WHERE COALESCE(pll.PickedQuantity, 0) > COALESCE(sir.ReservedQuantity, 0) + 0.01;

-- 7E. Shipment quantity does not exceed picked quantity and COGS formula holds. Expected: no rows.
SELECT ssl.ShipmentLineID,
       ssl.ShippedQuantity,
       pll.PickedQuantity,
       ssl.UnitCost,
       ssl.COGSValue
FROM dbo.SalesShipmentLine ssl
JOIN dbo.SalesPickListLine pll ON pll.PickListLineID = ssl.PickListLineID
WHERE COALESCE(ssl.ShippedQuantity, 0) > COALESCE(pll.PickedQuantity, 0) + 0.01
   OR ABS(COALESCE(ssl.COGSValue, 0) - COALESCE(ssl.ShippedQuantity, 0) * COALESCE(ssl.UnitCost, 0)) > 0.01;

-- 7F. SalesShipmentLine references upstream finished goods receipt and production batch. Expected: no rows.
SELECT ssl.ShipmentLineID
FROM dbo.SalesShipmentLine ssl
LEFT JOIN dbo.SalesShipmentHeader ssh ON ssh.ShipmentID = ssl.ShipmentID
LEFT JOIN dbo.SalesOrderLine sol ON sol.SalesOrderLineID = ssl.SalesOrderLineID
LEFT JOIN dbo.SalesPickListLine pll ON pll.PickListLineID = ssl.PickListLineID
LEFT JOIN dbo.FinishedGoodsInventory fgi ON fgi.FinishedGoodsInventoryID = ssl.FinishedGoodsInventoryID
LEFT JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = ssl.FinishedGoodsReceiptID
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = ssl.ProductionBatchID
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = ssl.ProductID
WHERE ssh.ShipmentID IS NULL
   OR sol.SalesOrderLineID IS NULL
   OR pll.PickListLineID IS NULL
   OR fgi.FinishedGoodsInventoryID IS NULL
   OR fgr.FinishedGoodsReceiptID IS NULL
   OR pb.ProductionBatchID IS NULL
   OR pm.ProductID IS NULL;

-- 7G. Total shipped does not exceed FinishedGoodsReceipt good quantity. Expected: no rows.
WITH ShippedByReceipt AS (
    SELECT FinishedGoodsReceiptID, SUM(ShippedQuantity) AS ShippedQuantity
    FROM dbo.SalesShipmentLine
    GROUP BY FinishedGoodsReceiptID
)
SELECT fgr.FinishedGoodsReceiptID,
       fgr.GoodQuantity,
       s.ShippedQuantity
FROM dbo.FinishedGoodsReceipt fgr
JOIN ShippedByReceipt s ON s.FinishedGoodsReceiptID = fgr.FinishedGoodsReceiptID
WHERE COALESCE(s.ShippedQuantity, 0) > COALESCE(fgr.GoodQuantity, 0) + 0.01;

/* ============================================================
SECTION 8 - SALES INVOICE/PAYMENT VALIDATION
============================================================ */

-- 8A. SalesInvoiceLine quantity, COGS, and margin formulas. Expected: no rows.
SELECT sil.InvoiceLineID,
       sil.InvoiceQuantity,
       ssl.ShippedQuantity,
       sil.UnitPrice,
       sil.DiscountAmount,
       sil.TaxAmount,
       sil.COGSValue,
       ssl.UnitCost,
       sil.NetLineAmount,
       sil.GrossMarginAmount,
       sil.GrossMarginPct
FROM dbo.SalesInvoiceLine sil
JOIN dbo.SalesShipmentLine ssl ON ssl.ShipmentLineID = sil.ShipmentLineID
WHERE ABS(COALESCE(sil.InvoiceQuantity, 0) - COALESCE(ssl.ShippedQuantity, 0)) > 0.01
   OR ABS(COALESCE(sil.NetLineAmount, 0)
        - (ROUND(COALESCE(sil.InvoiceQuantity, 0) * COALESCE(sil.UnitPrice, 0), 2) - COALESCE(sil.DiscountAmount, 0))) > 0.05
   OR ABS(COALESCE(sil.COGSValue, 0) - COALESCE(sil.InvoiceQuantity, 0) * COALESCE(ssl.UnitCost, 0)) > 0.01
   OR ABS(COALESCE(sil.GrossMarginAmount, 0) - (COALESCE(sil.NetLineAmount, 0) - COALESCE(sil.COGSValue, 0))) > 0.01
   OR (
        COALESCE(sil.NetLineAmount, 0) > 0
        AND ABS(COALESCE(sil.GrossMarginPct, 0) - COALESCE(sil.GrossMarginAmount, 0) / NULLIF(sil.NetLineAmount, 0)) > 0.01
      );

-- 8B. Invoice header totals reconcile to invoice lines. Expected: no rows.
WITH InvoiceLineRollup AS (
    SELECT InvoiceID,
           SUM(NetLineAmount) AS SubtotalAmount,
           SUM(DiscountAmount) AS DiscountAmount,
           SUM(TaxAmount) AS TaxAmount
    FROM dbo.SalesInvoiceLine
    GROUP BY InvoiceID
)
SELECT h.InvoiceID,
       h.SubtotalAmount,
       r.SubtotalAmount AS LineSubtotalAmount,
       h.DiscountAmount,
       r.DiscountAmount AS LineDiscountAmount,
       h.TaxAmount,
       r.TaxAmount AS LineTaxAmount,
       h.TotalInvoiceAmount
FROM dbo.SalesInvoiceHeader h
JOIN InvoiceLineRollup r ON r.InvoiceID = h.InvoiceID
WHERE ABS(COALESCE(h.SubtotalAmount, 0) - COALESCE(r.SubtotalAmount, 0)) > 0.01
   OR ABS(COALESCE(h.DiscountAmount, 0) - COALESCE(r.DiscountAmount, 0)) > 0.01
   OR ABS(COALESCE(h.TaxAmount, 0) - COALESCE(r.TaxAmount, 0)) > 0.01
   OR ABS(COALESCE(h.TotalInvoiceAmount, 0)
        - (COALESCE(h.SubtotalAmount, 0) + COALESCE(h.TaxAmount, 0) + COALESCE(h.FreightAmount, 0))) > 0.05;

-- 8C. Negative gross margin rows are business-realistic warnings, not validation errors.
-- Expected: optional warning rows when a sale is intentionally below cost.
SELECT InvoiceLineID,
       NetLineAmount,
       COGSValue,
       GrossMarginAmount,
       GrossMarginPct,
       'WARNING_NEGATIVE_GROSS_MARGIN' AS Severity
FROM dbo.SalesInvoiceLine
WHERE GrossMarginAmount < 0
   OR GrossMarginPct < 0;

-- 8D. Extreme gross margin percentages remain errors. Expected: no rows.
SELECT InvoiceLineID,
       NetLineAmount,
       COGSValue,
       GrossMarginAmount,
       GrossMarginPct
FROM dbo.SalesInvoiceLine
WHERE GrossMarginPct < -1.0
   OR GrossMarginPct > 1.0;

-- 8E. Payments do not exceed invoice total and payment dates are valid. Expected: no rows.
WITH PaymentRollup AS (
    SELECT InvoiceID, SUM(PaidAmount) AS PaidAmount
    FROM dbo.CustomerPaymentReceipt
    GROUP BY InvoiceID
)
SELECT h.InvoiceID, h.TotalInvoiceAmount, p.PaidAmount
FROM dbo.SalesInvoiceHeader h
JOIN PaymentRollup p ON p.InvoiceID = h.InvoiceID
WHERE COALESCE(p.PaidAmount, 0) > COALESCE(h.TotalInvoiceAmount, 0) + 0.01
UNION ALL
SELECT h.InvoiceID, h.TotalInvoiceAmount, p.PaidAmount
FROM dbo.SalesInvoiceHeader h
JOIN dbo.CustomerPaymentReceipt p ON p.InvoiceID = h.InvoiceID
WHERE p.PaymentDate < h.InvoiceDate;

-- 8F. InvoiceStatus is fact-derived from payment amounts. Expected: no rows.
WITH PaymentRollup AS (
    SELECT InvoiceID, SUM(PaidAmount) AS PaidAmount
    FROM dbo.CustomerPaymentReceipt
    GROUP BY InvoiceID
)
SELECT h.InvoiceID, h.TotalInvoiceAmount, COALESCE(p.PaidAmount, 0) AS PaidAmount, h.InvoiceStatus
FROM dbo.SalesInvoiceHeader h
LEFT JOIN PaymentRollup p ON p.InvoiceID = h.InvoiceID
WHERE (COALESCE(p.PaidAmount, 0) >= COALESCE(h.TotalInvoiceAmount, 0) - 0.01 AND h.InvoiceStatus <> 'Paid')
   OR (COALESCE(p.PaidAmount, 0) > 0.01 AND COALESCE(p.PaidAmount, 0) < COALESCE(h.TotalInvoiceAmount, 0) - 0.01 AND h.InvoiceStatus <> 'PartiallyPaid')
   OR (COALESCE(p.PaidAmount, 0) <= 0.01 AND h.InvoiceStatus <> 'Open');

-- 8G. PaymentStatus values are valid and distinct from invoice statuses. Expected: no rows.
SELECT PaymentReceiptID, PaymentStatus
FROM dbo.CustomerPaymentReceipt
WHERE PaymentStatus NOT IN ('Received', 'Partial', 'Failed');

/* ============================================================
SECTION 9 - SALES RETURNS VALIDATION
============================================================ */

-- 9A. Return headers link to customer, order, and shipment. Expected: no rows.
SELECT srh.SalesReturnID
FROM dbo.SalesReturnHeader srh
LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = srh.CustomerID
LEFT JOIN dbo.SalesOrderHdr soh ON soh.SalesOrderID = srh.SalesOrderID
LEFT JOIN dbo.SalesShipmentHeader ssh ON ssh.ShipmentID = srh.ShipmentID
WHERE cm.CustomerID IS NULL
   OR soh.SalesOrderID IS NULL
   OR ssh.ShipmentID IS NULL;

-- 9B. Return lines link to shipment lines and split returned quantity. Expected: no rows.
SELECT srl.SalesReturnLineID,
       srl.ReturnedQuantity,
       srl.RestockedQuantity,
       srl.ScrappedQuantity,
       ssl.ShippedQuantity,
       srl.ReturnUnitValue
FROM dbo.SalesReturnLine srl
JOIN dbo.SalesShipmentLine ssl ON ssl.ShipmentLineID = srl.ShipmentLineID
WHERE srl.ReturnedQuantity <= 0
   OR srl.ReturnedQuantity > ssl.ShippedQuantity + 0.01
   OR srl.RestockedQuantity < 0
   OR srl.ScrappedQuantity < 0
   OR ABS(COALESCE(srl.ReturnedQuantity, 0) - COALESCE(srl.RestockedQuantity, 0) - COALESCE(srl.ScrappedQuantity, 0)) > 0.01
   OR srl.ProductID <> ssl.ProductID
   OR srl.ReturnUnitValue <= 0;

-- 9C. ReturnDate is on or after ShipmentDate. Expected: no rows.
SELECT srh.SalesReturnID, srh.ReturnDate, ssh.ShipmentDate
FROM dbo.SalesReturnHeader srh
JOIN dbo.SalesShipmentHeader ssh ON ssh.ShipmentID = srh.ShipmentID
WHERE srh.ReturnDate < ssh.ShipmentDate;

/* ============================================================
SECTION 10 - SALES SHIPMENT TRACEABILITY VALIDATION
============================================================ */

-- 10A. Every SalesShipmentLine has at least one traceability row. Expected: no rows.
SELECT ssl.ShipmentLineID
FROM dbo.SalesShipmentLine ssl
LEFT JOIN dbo.SalesShipmentTraceability sst ON sst.ShipmentLineID = ssl.ShipmentLineID
GROUP BY ssl.ShipmentLineID
HAVING COUNT(sst.SalesTraceabilityID) = 0;

-- 10B. Traceability links to all required upstream lineage tables. Expected: no rows.
SELECT sst.SalesTraceabilityID
FROM dbo.SalesShipmentTraceability sst
LEFT JOIN dbo.SalesShipmentLine ssl ON ssl.ShipmentLineID = sst.ShipmentLineID
LEFT JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = sst.FinishedGoodsReceiptID
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = sst.ProductionBatchID
LEFT JOIN dbo.ProductionGenealogy pg ON pg.ProductionGenealogyID = sst.ProductionGenealogyID
LEFT JOIN dbo.MaterialIssueLine mil ON mil.MaterialIssueLineID = sst.MaterialIssueLineID
LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = sst.InventoryReceiptDetailID
LEFT JOIN dbo.SupplierMaster sm ON sm.SupplierID = sst.SupplierID
LEFT JOIN dbo.ComponentMaster cm ON cm.ComponentID = sst.ComponentID
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = sst.ProductID
WHERE ssl.ShipmentLineID IS NULL
   OR fgr.FinishedGoodsReceiptID IS NULL
   OR pb.ProductionBatchID IS NULL
   OR pg.ProductionGenealogyID IS NULL
   OR mil.MaterialIssueLineID IS NULL
   OR ird.InventoryReceiptDetailID IS NULL
   OR sm.SupplierID IS NULL
   OR cm.ComponentID IS NULL
   OR pm.ProductID IS NULL;

-- 10C. AllocatedConsumedQuantity formula. Expected: no rows.
SELECT sst.SalesTraceabilityID,
       sst.AllocatedConsumedQuantity,
       pg.ConsumedQuantity,
       ssl.ShippedQuantity,
       fgr.GoodQuantity
FROM dbo.SalesShipmentTraceability sst
JOIN dbo.ProductionGenealogy pg ON pg.ProductionGenealogyID = sst.ProductionGenealogyID
JOIN dbo.SalesShipmentLine ssl ON ssl.ShipmentLineID = sst.ShipmentLineID
JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = sst.FinishedGoodsReceiptID
WHERE fgr.GoodQuantity <= 0
   OR sst.AllocatedConsumedQuantity < 0
   OR ABS(COALESCE(sst.AllocatedConsumedQuantity, 0)
        - COALESCE(pg.ConsumedQuantity, 0) * COALESCE(ssl.ShippedQuantity, 0) / NULLIF(fgr.GoodQuantity, 0)) > 0.01
   OR sst.TraceabilityStatus <> 'Traced';

/* ============================================================
SECTION 11 - FINISHED GOODS INVENTORY AFTER SALES VALIDATION
============================================================ */

-- 11A. FinishedGoodsInventory after Sales rollup. Expected: no rows.
WITH ReceiptRollup AS (
    SELECT ProductID, PlantID, WarehouseID, SUM(GoodQuantity) AS ReceiptQuantity
    FROM dbo.FinishedGoodsReceipt
    GROUP BY ProductID, PlantID, WarehouseID
),
ShipmentRollup AS (
    SELECT FinishedGoodsInventoryID, SUM(ShippedQuantity) AS ShippedQuantity
    FROM dbo.SalesShipmentLine
    GROUP BY FinishedGoodsInventoryID
),
ReturnRollup AS (
    SELECT ssl.FinishedGoodsInventoryID, SUM(srl.RestockedQuantity) AS RestockedQuantity
    FROM dbo.SalesReturnLine srl
    JOIN dbo.SalesShipmentLine ssl ON ssl.ShipmentLineID = srl.ShipmentLineID
    GROUP BY ssl.FinishedGoodsInventoryID
),
ReservationRollup AS (
    SELECT FinishedGoodsInventoryID, SUM(ReservedQuantity) AS ReservedQuantity
    FROM dbo.SalesInventoryReservation
    WHERE ReservationStatus = 'Reserved'
    GROUP BY FinishedGoodsInventoryID
)
SELECT fgi.FinishedGoodsInventoryID,
       fgi.OnHandQuantity,
       COALESCE(rr.ReceiptQuantity, 0) - COALESCE(sr.ShippedQuantity, 0) + COALESCE(ret.RestockedQuantity, 0) AS ExpectedOnHandQuantity,
       fgi.ReservedQuantity,
       COALESCE(res.ReservedQuantity, 0) AS ExpectedReservedQuantity,
       fgi.AvailableQuantity
FROM dbo.FinishedGoodsInventory fgi
LEFT JOIN ReceiptRollup rr
  ON rr.ProductID = fgi.ProductID
 AND rr.PlantID = fgi.PlantID
 AND rr.WarehouseID = fgi.WarehouseID
LEFT JOIN ShipmentRollup sr ON sr.FinishedGoodsInventoryID = fgi.FinishedGoodsInventoryID
LEFT JOIN ReturnRollup ret ON ret.FinishedGoodsInventoryID = fgi.FinishedGoodsInventoryID
LEFT JOIN ReservationRollup res ON res.FinishedGoodsInventoryID = fgi.FinishedGoodsInventoryID
WHERE ABS(COALESCE(fgi.OnHandQuantity, 0)
        - (COALESCE(rr.ReceiptQuantity, 0) - COALESCE(sr.ShippedQuantity, 0) + COALESCE(ret.RestockedQuantity, 0))) > 0.01
   OR ABS(COALESCE(fgi.ReservedQuantity, 0) - COALESCE(res.ReservedQuantity, 0)) > 0.01
   OR ABS(COALESCE(fgi.AvailableQuantity, 0) - (COALESCE(fgi.OnHandQuantity, 0) - COALESCE(fgi.ReservedQuantity, 0))) > 0.01
   OR fgi.OnHandQuantity < 0
   OR fgi.ReservedQuantity < 0
   OR fgi.AvailableQuantity < 0
   OR fgi.ReservedQuantity > fgi.OnHandQuantity + 0.01;

-- 11B. Consumed and released reservations do not count as current FinishedGoodsInventory.ReservedQuantity. Expected: no rows.
WITH ActiveReservationRollup AS (
    SELECT FinishedGoodsInventoryID, SUM(ReservedQuantity) AS ReservedQuantity
    FROM dbo.SalesInventoryReservation
    WHERE ReservationStatus = 'Reserved'
    GROUP BY FinishedGoodsInventoryID
)
SELECT fgi.FinishedGoodsInventoryID,
       fgi.ReservedQuantity,
       COALESCE(ar.ReservedQuantity, 0) AS ActiveReservedQuantity
FROM dbo.FinishedGoodsInventory fgi
LEFT JOIN ActiveReservationRollup ar ON ar.FinishedGoodsInventoryID = fgi.FinishedGoodsInventoryID
WHERE ABS(COALESCE(fgi.ReservedQuantity, 0) - COALESCE(ar.ReservedQuantity, 0)) > 0.01;

/* ============================================================
SECTION 12 - END-TO-END SUPPLIER-TO-CUSTOMER TRACEABILITY
============================================================ */

-- 12A. Supplier-to-customer traceability chain summary. Expected: status = PASS.
WITH Chain AS (
    SELECT cm.CustomerID,
           soh.SalesOrderID,
           ssl.ShipmentLineID,
           sst.SalesTraceabilityID,
           fgr.FinishedGoodsReceiptID,
           pb.ProductionBatchID,
           pg.ProductionGenealogyID,
           mil.MaterialIssueLineID,
           ird.InventoryReceiptDetailID,
           sm.SupplierID,
           comp.ComponentID
    FROM dbo.CustomerMaster cm
    JOIN dbo.SalesOrderHdr soh ON soh.CustomerID = cm.CustomerID
    JOIN dbo.SalesShipmentHeader ssh ON ssh.SalesOrderID = soh.SalesOrderID
    JOIN dbo.SalesShipmentLine ssl ON ssl.ShipmentID = ssh.ShipmentID
    LEFT JOIN dbo.SalesShipmentTraceability sst ON sst.ShipmentLineID = ssl.ShipmentLineID
    LEFT JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = sst.FinishedGoodsReceiptID
    LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = sst.ProductionBatchID
    LEFT JOIN dbo.ProductionGenealogy pg ON pg.ProductionGenealogyID = sst.ProductionGenealogyID
    LEFT JOIN dbo.MaterialIssueLine mil ON mil.MaterialIssueLineID = sst.MaterialIssueLineID
    LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = sst.InventoryReceiptDetailID
    LEFT JOIN dbo.SupplierMaster sm ON sm.SupplierID = sst.SupplierID
    LEFT JOIN dbo.ComponentMaster comp ON comp.ComponentID = sst.ComponentID
)
SELECT COUNT(*) AS traceability_rows,
       SUM(CASE WHEN CustomerID IS NULL OR SalesOrderID IS NULL OR ShipmentLineID IS NULL THEN 1 ELSE 0 END) AS missing_customer_links,
       SUM(CASE WHEN SupplierID IS NULL THEN 1 ELSE 0 END) AS missing_supplier_links,
       SUM(CASE WHEN ComponentID IS NULL THEN 1 ELSE 0 END) AS missing_component_links,
       CASE
           WHEN COUNT(*) > 0
            AND SUM(CASE WHEN CustomerID IS NULL OR SalesOrderID IS NULL OR ShipmentLineID IS NULL THEN 1 ELSE 0 END) = 0
            AND SUM(CASE WHEN SupplierID IS NULL THEN 1 ELSE 0 END) = 0
            AND SUM(CASE WHEN ComponentID IS NULL THEN 1 ELSE 0 END) = 0
           THEN 'PASS'
           ELSE 'FAIL'
       END AS status
FROM Chain;

/* ============================================================
SECTION 13 - FOOD MANUFACTURING VOCABULARY / EV LEAKAGE CHECK
============================================================ */

-- 13A. Food context should be present and EV/automotive leakage should be absent for profile_id = food_manufacturing.
-- Expected: food_context_rows > 0, ev_context_rows = 0, status = PASS.
WITH TextValues AS (
    SELECT CONCAT(SupplierName, ' ', SupplierCategory) AS TextValue FROM dbo.SupplierMaster
    UNION ALL SELECT CONCAT(ComponentName, ' ', ComponentCategory) FROM dbo.ComponentMaster
    UNION ALL SELECT CONCAT(ProductName, ' ', ProductCategory, ' ', ProductType) FROM dbo.ProductMaster
    UNION ALL SELECT CONCAT(CustomerName, ' ', CustomerType, ' ', Industry) FROM dbo.CustomerMaster
    UNION ALL SELECT CONCAT(ChannelCode, ' ', ChannelName, ' ', ChannelType) FROM dbo.SalesChannel
    UNION ALL SELECT CONCAT(CarrierName, ' ', TrackingNumber, ' ', ShipmentStatus) FROM dbo.SalesShipmentHeader
    UNION ALL SELECT CONCAT(ReturnReason, ' ', ReturnStatus) FROM dbo.SalesReturnHeader
    UNION ALL SELECT CONCAT(DefectCode, ' ', DefectSeverity) FROM dbo.ProductionQualityResult
    UNION ALL SELECT CONCAT(EventType, ' ', ReasonCode) FROM dbo.ScrapReworkEvent
),
Normalized AS (
    SELECT UPPER(CONCAT(' ', REPLACE(REPLACE(REPLACE(REPLACE(TextValue, '-', ' '), '/', ' '), '_', ' '), '.', ' '), ' ')) AS TextValue
    FROM TextValues
),
Counts AS (
    SELECT
        SUM(CASE
                WHEN TextValue LIKE '% FOOD %'
                  OR TextValue LIKE '% GROCERY %'
                  OR TextValue LIKE '% SNACK %'
                  OR TextValue LIKE '% SPICE %'
                  OR TextValue LIKE '% PANTRY %'
                  OR TextValue LIKE '% FRESH %'
                THEN 1 ELSE 0
            END) AS food_context_rows,
        SUM(CASE
                WHEN TextValue LIKE '% EV %'
                  OR TextValue LIKE '% ELECTRIC VEHICLE %'
                  OR TextValue LIKE '% BATTERY %'
                  OR TextValue LIKE '% AUTOMOTIVE %'
                  OR TextValue LIKE '% THERMAL RUNAWAY %'
                  OR TextValue LIKE '% CHASSIS %'
                  OR TextValue LIKE '% DRIVE UNIT %'
                  OR TextValue LIKE '% POWER ELECTRONICS %'
                THEN 1 ELSE 0
            END) AS ev_context_rows
    FROM Normalized
)
SELECT food_context_rows,
       ev_context_rows,
       CASE WHEN food_context_rows > 0 AND ev_context_rows = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM Counts;

/* ============================================================
SECTION 14 - FINAL READINESS STATUS
============================================================ */

-- 14A. Final readiness. Expected: SALES_E2E_VALIDATED.
WITH CoreCounts AS (
    SELECT
        (SELECT COUNT(*) FROM dbo.SupplierMaster)
      + (SELECT COUNT(*) FROM dbo.PurchaseOrderLine)
      + (SELECT COUNT(*) FROM dbo.InventoryReceiptDetail)
      + (SELECT COUNT(*) FROM dbo.InventoryTransaction) AS procurement_core_rows,
        (SELECT COUNT(*) FROM dbo.ProductMaster)
      + (SELECT COUNT(*) FROM dbo.FinishedGoodsReceipt)
      + (SELECT COUNT(*) FROM dbo.ProductionGenealogy)
      + (SELECT COUNT(*) FROM dbo.ProductionCostSummary) AS production_core_rows,
        (SELECT COUNT(*) FROM dbo.CustomerMaster)
      + (SELECT COUNT(*) FROM dbo.SalesOrderLine)
      + (SELECT COUNT(*) FROM dbo.SalesShipmentLine)
      + (SELECT COUNT(*) FROM dbo.SalesInvoiceHeader)
      + (SELECT COUNT(*) FROM dbo.CustomerPaymentReceipt) AS sales_core_rows,
        (SELECT COUNT(*) FROM dbo.FinishedGoodsInventory) AS finished_goods_inventory_rows,
        (SELECT COUNT(*) FROM dbo.SalesShipmentTraceability) AS sales_traceability_rows,
        (SELECT COUNT(*) FROM dbo.SalesInvoiceLine) + (SELECT COUNT(*) FROM dbo.CustomerPaymentReceipt) AS invoice_payment_rows,
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'SalesCreditMemo') AS sales_credit_memo_tables,
        (SELECT COUNT(*)
         FROM dbo.SalesShipmentLine ssl
         LEFT JOIN dbo.SalesShipmentTraceability sst ON sst.ShipmentLineID = ssl.ShipmentLineID
         WHERE sst.SalesTraceabilityID IS NULL) AS missing_traceability_rows
)
SELECT procurement_core_rows,
       production_core_rows,
       sales_core_rows,
       finished_goods_inventory_rows,
       sales_traceability_rows,
       invoice_payment_rows,
       sales_credit_memo_tables,
       missing_traceability_rows,
       CASE
           WHEN procurement_core_rows > 0
            AND production_core_rows > 0
            AND sales_core_rows > 0
            AND finished_goods_inventory_rows > 0
            AND sales_traceability_rows > 0
            AND invoice_payment_rows > 0
            AND sales_credit_memo_tables = 0
            AND missing_traceability_rows = 0
           THEN 'SALES_E2E_VALIDATED'
           ELSE 'SALES_E2E_NOT_READY'
       END AS FinalReadinessStatus
FROM CoreCounts;
