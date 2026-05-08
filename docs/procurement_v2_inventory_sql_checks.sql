/*
Procurement v2 Inventory SQL validation checks.

InventoryTransaction is the detailed stock movement ledger.
Inventory is the calculated current stock balance by ComponentID, PlantID, and WarehouseID.
InventoryBalance is intentionally not part of Procurement v2.

Refined inventory design:
- InventoryTransaction contains accepted inbound StockIn postings only.
- InventoryTransaction carries supplier, goods receipt line, PO line, unit price, and inventory value traceability.
- Inventory summarizes both quantity and value from InventoryTransaction groups.
*/

-- 1. Inventory row count. Expected: InventoryRows > 0.
SELECT COUNT(*) AS InventoryRows
FROM dbo.Inventory;

-- 2. InventoryBalance absence. Expected: InventoryBalanceObjectCount = 0.
SELECT COUNT(*) AS InventoryBalanceObjectCount
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'InventoryBalance';

-- 3. InventoryTransaction.TransactionType. Expected: NonStockInRows = 0.
SELECT COUNT(*) AS NonStockInRows
FROM dbo.InventoryTransaction
WHERE TransactionType <> 'StockIn';

-- 4. InventoryTransaction FK orphan checks. Expected: all IssueCount = 0.
SELECT 'InventoryTransaction.InspectionResultID orphan' AS CheckName, COUNT(*) AS IssueCount
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.InspectionResult ir ON it.InspectionResultID = ir.InspectionResultID
WHERE ir.InspectionResultID IS NULL

UNION ALL
SELECT 'InventoryTransaction.GoodsReceiptLineID orphan', COUNT(*)
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.GoodsReceiptLine grl ON it.GoodsReceiptLineID = grl.GoodsReceiptLineID
WHERE grl.GoodsReceiptLineID IS NULL

UNION ALL
SELECT 'InventoryTransaction.PurchaseOrderLineID orphan', COUNT(*)
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.PurchaseOrderLine pol ON it.PurchaseOrderLineID = pol.PurchaseOrderLineID
WHERE pol.PurchaseOrderLineID IS NULL

UNION ALL
SELECT 'InventoryTransaction.SupplierID orphan', COUNT(*)
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.SupplierMaster sm ON it.SupplierID = sm.SupplierID
WHERE sm.SupplierID IS NULL

UNION ALL
SELECT 'InventoryTransaction.ComponentID orphan', COUNT(*)
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.ComponentMaster cm ON it.ComponentID = cm.ComponentID
WHERE cm.ComponentID IS NULL

UNION ALL
SELECT 'InventoryTransaction.PlantID orphan', COUNT(*)
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.Plant p ON it.PlantID = p.PlantID
WHERE p.PlantID IS NULL

UNION ALL
SELECT 'InventoryTransaction.WarehouseID orphan', COUNT(*)
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.Warehouse w ON it.WarehouseID = w.WarehouseID
WHERE w.WarehouseID IS NULL;

-- 5. InventoryTransaction supplier lineage. Expected: SupplierMismatchRows = 0.
SELECT COUNT(*) AS SupplierMismatchRows
FROM dbo.InventoryTransaction it
JOIN dbo.PurchaseOrderLine pol ON it.PurchaseOrderLineID = pol.PurchaseOrderLineID
JOIN dbo.PurchaseOrderHdr poh ON pol.PurchaseOrderID = poh.PurchaseOrderID
WHERE it.SupplierID <> poh.SupplierID;

-- 6. InventoryTransaction goods receipt line lineage. Expected: GoodsReceiptLineMismatchRows = 0.
SELECT COUNT(*) AS GoodsReceiptLineMismatchRows
FROM dbo.InventoryTransaction it
JOIN dbo.InspectionResult ir ON it.InspectionResultID = ir.InspectionResultID
JOIN dbo.IncomingInspection ii ON ir.InspectionID = ii.InspectionID
WHERE it.GoodsReceiptLineID <> ii.GoodsReceiptLineID;

-- 7. InventoryTransaction PO line lineage. Expected: PurchaseOrderLineMismatchRows = 0.
SELECT COUNT(*) AS PurchaseOrderLineMismatchRows
FROM dbo.InventoryTransaction it
JOIN dbo.GoodsReceiptLine grl ON it.GoodsReceiptLineID = grl.GoodsReceiptLineID
WHERE it.PurchaseOrderLineID <> grl.PurchaseOrderLineID;

-- 8. InventoryTransaction component lineage. Expected: ComponentMismatchRows = 0.
SELECT COUNT(*) AS ComponentMismatchRows
FROM dbo.InventoryTransaction it
JOIN dbo.GoodsReceiptLine grl ON it.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN dbo.PurchaseOrderLine pol ON it.PurchaseOrderLineID = pol.PurchaseOrderLineID
WHERE it.ComponentID <> grl.ComponentID
   OR it.ComponentID <> pol.ComponentID;

-- 9. InventoryTransaction plant/warehouse lineage. Expected: PlantWarehouseMismatchRows = 0.
SELECT COUNT(*) AS PlantWarehouseMismatchRows
FROM dbo.InventoryTransaction it
JOIN dbo.GoodsReceiptLine grl ON it.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN dbo.GoodsReceiptHeader grh ON grl.GoodsReceiptID = grh.GoodsReceiptID
WHERE it.PlantID <> grh.PlantID
   OR it.WarehouseID <> grh.WarehouseID;

-- 10. InventoryTransaction quantity and price checks. Expected: all issue counts = 0.
SELECT 'TransactionQuantity != AcceptedQuantity' AS CheckName, COUNT(*) AS IssueCount
FROM dbo.InventoryTransaction it
JOIN dbo.InspectionResult ir ON it.InspectionResultID = ir.InspectionResultID
WHERE ABS(it.TransactionQuantity - ir.AcceptedQuantity) > 0.0001

UNION ALL
SELECT 'UnitPrice != PurchaseOrderLine.UnitPrice', COUNT(*)
FROM dbo.InventoryTransaction it
JOIN dbo.PurchaseOrderLine pol ON it.PurchaseOrderLineID = pol.PurchaseOrderLineID
WHERE ABS(it.UnitPrice - pol.UnitPrice) > 0.01

UNION ALL
SELECT 'InventoryValue != TransactionQuantity * UnitPrice', COUNT(*)
FROM dbo.InventoryTransaction it
WHERE ABS(it.InventoryValue - ROUND(it.TransactionQuantity * it.UnitPrice, 2)) > 0.01;

-- 11. InventoryTransaction negative value checks. Expected: all IssueCount = 0.
SELECT 'TransactionQuantity negative' AS CheckName, COUNT(*) AS IssueCount
FROM dbo.InventoryTransaction
WHERE TransactionQuantity < 0

UNION ALL
SELECT 'InventoryValue negative', COUNT(*)
FROM dbo.InventoryTransaction
WHERE InventoryValue < 0;

-- 12. Inventory FK orphan checks. Expected: all IssueCount = 0.
SELECT 'Inventory.ComponentID orphan' AS CheckName, COUNT(*) AS IssueCount
FROM dbo.Inventory inv
LEFT JOIN dbo.ComponentMaster cm ON inv.ComponentID = cm.ComponentID
WHERE cm.ComponentID IS NULL

UNION ALL
SELECT 'Inventory.PlantID orphan', COUNT(*)
FROM dbo.Inventory inv
LEFT JOIN dbo.Plant p ON inv.PlantID = p.PlantID
WHERE p.PlantID IS NULL

UNION ALL
SELECT 'Inventory.WarehouseID orphan', COUNT(*)
FROM dbo.Inventory inv
LEFT JOIN dbo.Warehouse w ON inv.WarehouseID = w.WarehouseID
WHERE w.WarehouseID IS NULL;

-- 13. Warehouse/Plant consistency. Expected: WarehousePlantMismatchRows = 0.
SELECT COUNT(*) AS WarehousePlantMismatchRows
FROM dbo.Inventory inv
JOIN dbo.Warehouse w ON inv.WarehouseID = w.WarehouseID
WHERE inv.PlantID <> w.PlantID;

-- 14. OnHand quantity reconciliation. Expected: BadInventoryOnHandRows = 0.
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

-- 15. OnHand value reconciliation. Expected: BadOnHandValueRows = 0.
WITH TxnValue AS (
    SELECT
        ComponentID,
        PlantID,
        WarehouseID,
        SUM(InventoryValue) AS ExpectedOnHandValue
    FROM dbo.InventoryTransaction
    GROUP BY ComponentID, PlantID, WarehouseID
)
SELECT
    COUNT(*) AS BadOnHandValueRows,
    MAX(ABS(inv.OnHandValue - tv.ExpectedOnHandValue)) AS MaxDifference
FROM dbo.Inventory inv
JOIN TxnValue tv
    ON inv.ComponentID = tv.ComponentID
   AND inv.PlantID = tv.PlantID
   AND inv.WarehouseID = tv.WarehouseID
WHERE ABS(inv.OnHandValue - tv.ExpectedOnHandValue) > 0.01;

-- 16. Available quantity reconciliation. Expected: BadAvailableQuantityRows = 0.
SELECT COUNT(*) AS BadAvailableQuantityRows
FROM dbo.Inventory
WHERE ABS(AvailableQuantity - (OnHandQuantity - ReservedQuantity)) > 0.0001;

-- 17. Available value reconciliation. Expected: BadAvailableValueRows = 0.
SELECT COUNT(*) AS BadAvailableValueRows
FROM dbo.Inventory
WHERE ABS(
    AvailableValue -
    CASE
        WHEN OnHandQuantity = 0 THEN 0
        ELSE ROUND(AvailableQuantity * (OnHandValue / OnHandQuantity), 2)
    END
) > 0.01;

-- 18. Last transaction date reconciliation. Expected: BadLastTransactionDateRows = 0.
WITH TxnDates AS (
    SELECT
        ComponentID,
        PlantID,
        WarehouseID,
        MAX(TransactionDate) AS ExpectedLastTransactionDate
    FROM dbo.InventoryTransaction
    GROUP BY ComponentID, PlantID, WarehouseID
)
SELECT COUNT(*) AS BadLastTransactionDateRows
FROM dbo.Inventory inv
JOIN TxnDates td
    ON inv.ComponentID = td.ComponentID
   AND inv.PlantID = td.PlantID
   AND inv.WarehouseID = td.WarehouseID
WHERE inv.LastTransactionDate <> td.ExpectedLastTransactionDate;

-- 19. Negative inventory quantity/value checks. Expected: all IssueCount = 0.
SELECT 'OnHandQuantity negative' AS CheckName, COUNT(*) AS IssueCount
FROM dbo.Inventory
WHERE OnHandQuantity < 0

UNION ALL
SELECT 'ReservedQuantity negative', COUNT(*)
FROM dbo.Inventory
WHERE ReservedQuantity < 0

UNION ALL
SELECT 'AvailableQuantity negative', COUNT(*)
FROM dbo.Inventory
WHERE AvailableQuantity < 0

UNION ALL
SELECT 'ReservedQuantity > OnHandQuantity', COUNT(*)
FROM dbo.Inventory
WHERE ReservedQuantity > OnHandQuantity

UNION ALL
SELECT 'OnHandValue negative', COUNT(*)
FROM dbo.Inventory
WHERE OnHandValue < 0

UNION ALL
SELECT 'AvailableValue negative', COUNT(*)
FROM dbo.Inventory
WHERE AvailableValue < 0

UNION ALL
SELECT 'AvailableValue > OnHandValue', COUNT(*)
FROM dbo.Inventory
WHERE AvailableValue > OnHandValue + 0.01;

-- 20. Inventory status logic check. Expected: BadInventoryStatusRows = 0.
SELECT COUNT(*) AS BadInventoryStatusRows
FROM dbo.Inventory
WHERE
    (OnHandQuantity = 0 AND InventoryStatus <> 'OutOfStock')
    OR
    (OnHandQuantity > 0 AND AvailableQuantity = 0 AND InventoryStatus <> 'Hold')
    OR
    (OnHandQuantity > 0 AND AvailableQuantity > 0 AND AvailableQuantity <= OnHandQuantity * 0.10 AND InventoryStatus <> 'LowStock')
    OR
    (OnHandQuantity > 0 AND AvailableQuantity > OnHandQuantity * 0.10 AND InventoryStatus <> 'Available');

-- 21. Final inventory value scorecard. Expected: all IssueCount = 0.
WITH Scorecard AS (
    SELECT 'NonStockInRows' AS CheckName, COUNT(*) AS IssueCount
    FROM dbo.InventoryTransaction
    WHERE TransactionType <> 'StockIn'

    UNION ALL
    SELECT 'SupplierMismatchRows', COUNT(*)
    FROM dbo.InventoryTransaction it
    JOIN dbo.PurchaseOrderLine pol ON it.PurchaseOrderLineID = pol.PurchaseOrderLineID
    JOIN dbo.PurchaseOrderHdr poh ON pol.PurchaseOrderID = poh.PurchaseOrderID
    WHERE it.SupplierID <> poh.SupplierID

    UNION ALL
    SELECT 'InventoryValueMismatchRows', COUNT(*)
    FROM dbo.InventoryTransaction it
    WHERE ABS(it.InventoryValue - ROUND(it.TransactionQuantity * it.UnitPrice, 2)) > 0.01

    UNION ALL
    SELECT 'OnHandValueMismatchRows', COUNT(*)
    FROM dbo.Inventory inv
    JOIN (
        SELECT ComponentID, PlantID, WarehouseID, SUM(InventoryValue) AS ExpectedOnHandValue
        FROM dbo.InventoryTransaction
        GROUP BY ComponentID, PlantID, WarehouseID
    ) tv
        ON inv.ComponentID = tv.ComponentID
       AND inv.PlantID = tv.PlantID
       AND inv.WarehouseID = tv.WarehouseID
    WHERE ABS(inv.OnHandValue - tv.ExpectedOnHandValue) > 0.01

    UNION ALL
    SELECT 'AvailableValueMismatchRows', COUNT(*)
    FROM dbo.Inventory
    WHERE ABS(
        AvailableValue -
        CASE
            WHEN OnHandQuantity = 0 THEN 0
            ELSE ROUND(AvailableQuantity * (OnHandValue / OnHandQuantity), 2)
        END
    ) > 0.01

    UNION ALL
    SELECT 'InventoryBalanceObjectCount', COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo'
      AND TABLE_NAME = 'InventoryBalance'
)
SELECT CheckName, IssueCount
FROM Scorecard
ORDER BY CheckName;

-- 22. Inventory status distribution. Expected: Available majority; LowStock/Hold may appear; OutOfStock may be absent.
SELECT
    InventoryStatus,
    COUNT(*) AS RowCount,
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS DECIMAL(6,2)) AS Percentage
FROM dbo.Inventory
GROUP BY InventoryStatus
ORDER BY RowCount DESC;
