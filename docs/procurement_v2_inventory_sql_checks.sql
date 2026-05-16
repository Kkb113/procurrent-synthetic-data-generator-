/*
Procurement v2 InventoryReceiptDetail, InventoryTransaction, and Inventory SQL validation checks.

Purpose:
Validate the current 25-table Procurement v2 inventory flow:
InspectionResult -> InventoryReceiptDetail -> InventoryTransaction -> Inventory.

Expected:
- Detail checks return no rows.
- Final scorecards return IssueName / IssueCount with all IssueCount = 0.
- InventoryBalance is absent.
*/

-- 1. Procurement v2 required inventory tables. Expected: no rows.
SELECT RequiredTable
FROM (VALUES
    ('InventoryReceiptDetail'),
    ('InventoryTransaction'),
    ('Inventory')
) v(RequiredTable)
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = v.RequiredTable
WHERE t.TABLE_NAME IS NULL;

-- 2. InventoryBalance absence. Expected: InventoryBalanceObjectCount = 0.
SELECT COUNT(*) AS InventoryBalanceObjectCount
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'InventoryBalance';

-- 2A. Simplified operating scope summary. Expected: Plant and Warehouse each have 1 row.
SELECT 'Plant' AS TableName, COUNT(*) AS RowCount
FROM dbo.Plant
UNION ALL
SELECT 'Warehouse', COUNT(*)
FROM dbo.Warehouse;

-- 2B. Demo-friendly location summary. Expected: every DistinctPlantCount / DistinctWarehouseCount is 1 where applicable.
SELECT 'Warehouse' AS TableName,
       COUNT(DISTINCT PlantID) AS DistinctPlantCount,
       COUNT(DISTINCT WarehouseID) AS DistinctWarehouseCount
FROM dbo.Warehouse
UNION ALL
SELECT 'GoodsReceiptHeader', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID)
FROM dbo.GoodsReceiptHeader
UNION ALL
SELECT 'InventoryReceiptDetail', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID)
FROM dbo.InventoryReceiptDetail
UNION ALL
SELECT 'InventoryTransaction', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID)
FROM dbo.InventoryTransaction
UNION ALL
SELECT 'Inventory', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID)
FROM dbo.Inventory
UNION ALL
SELECT 'PurchaseRequisition', COUNT(DISTINCT PlantID), NULL
FROM dbo.PurchaseRequisition
UNION ALL
SELECT 'PurchaseOrderHdr', COUNT(DISTINCT PlantID), NULL
FROM dbo.PurchaseOrderHdr;

-- 2C. One Plant / one Warehouse scope checks. Expected: no rows.
WITH SinglePlant AS (
    SELECT MIN(PlantID) AS PlantID
    FROM dbo.Plant
),
SingleWarehouse AS (
    SELECT MIN(WarehouseID) AS WarehouseID
    FROM dbo.Warehouse
)
SELECT 'Warehouse.PlantID outside single Plant' AS IssueName, WarehouseID AS RecordID, PlantID AS BadValue
FROM dbo.Warehouse
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'GoodsReceiptHeader.PlantID outside single Plant', GoodsReceiptID, PlantID
FROM dbo.GoodsReceiptHeader
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'InventoryReceiptDetail.PlantID outside single Plant', InventoryReceiptDetailID, PlantID
FROM dbo.InventoryReceiptDetail
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'InventoryTransaction.PlantID outside single Plant', InventoryTransactionID, PlantID
FROM dbo.InventoryTransaction
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Inventory.PlantID outside single Plant', InventoryID, PlantID
FROM dbo.Inventory
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'GoodsReceiptHeader.WarehouseID outside single Warehouse', GoodsReceiptID, WarehouseID
FROM dbo.GoodsReceiptHeader
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL
SELECT 'InventoryReceiptDetail.WarehouseID outside single Warehouse', InventoryReceiptDetailID, WarehouseID
FROM dbo.InventoryReceiptDetail
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL
SELECT 'InventoryTransaction.WarehouseID outside single Warehouse', InventoryTransactionID, WarehouseID
FROM dbo.InventoryTransaction
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL
SELECT 'Inventory.WarehouseID outside single Warehouse', InventoryID, WarehouseID
FROM dbo.Inventory
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse);

-- 3. InventoryReceiptDetail primary key uniqueness. Expected: no rows.
SELECT
    InventoryReceiptDetailID,
    COUNT(*) AS DuplicateCount
FROM dbo.InventoryReceiptDetail
GROUP BY InventoryReceiptDetailID
HAVING InventoryReceiptDetailID IS NULL
    OR COUNT(*) > 1;

-- 4. InventoryReceiptDetail FK orphan checks. Expected: all IssueCount = 0.
SELECT 'InventoryReceiptDetail.InspectionResultID orphan' AS IssueName, COUNT(*) AS IssueCount
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.InspectionResult ir ON ird.InspectionResultID = ir.InspectionResultID
WHERE ir.InspectionResultID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.GoodsReceiptLineID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.GoodsReceiptLine grl ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
WHERE grl.GoodsReceiptLineID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.PurchaseOrderLineID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.PurchaseOrderLine pol ON ird.PurchaseOrderLineID = pol.PurchaseOrderLineID
WHERE pol.PurchaseOrderLineID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.PurchaseOrderID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.PurchaseOrderHdr poh ON ird.PurchaseOrderID = poh.PurchaseOrderID
WHERE poh.PurchaseOrderID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.SupplierID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.SupplierMaster sm ON ird.SupplierID = sm.SupplierID
WHERE sm.SupplierID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.ComponentID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.ComponentMaster cm ON ird.ComponentID = cm.ComponentID
WHERE cm.ComponentID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.PlantID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.Plant p ON ird.PlantID = p.PlantID
WHERE p.PlantID IS NULL

UNION ALL
SELECT 'InventoryReceiptDetail.WarehouseID orphan', COUNT(*)
FROM dbo.InventoryReceiptDetail ird
LEFT JOIN dbo.Warehouse w ON ird.WarehouseID = w.WarehouseID
WHERE w.WarehouseID IS NULL;

-- 5. InventoryReceiptDetail supplier/component/location lineage. Expected: no rows.
SELECT
    ird.InventoryReceiptDetailID,
    ird.SupplierID AS ActualSupplierID,
    poh.SupplierID AS ExpectedSupplierID,
    ird.ComponentID AS ActualComponentID,
    pol.ComponentID AS ExpectedPOComponentID,
    grl.ComponentID AS ExpectedReceiptComponentID,
    ird.PlantID AS ActualPlantID,
    grh.PlantID AS ExpectedPlantID,
    ird.WarehouseID AS ActualWarehouseID,
    grh.WarehouseID AS ExpectedWarehouseID
FROM dbo.InventoryReceiptDetail ird
JOIN dbo.PurchaseOrderHdr poh
    ON ird.PurchaseOrderID = poh.PurchaseOrderID
JOIN dbo.PurchaseOrderLine pol
    ON ird.PurchaseOrderLineID = pol.PurchaseOrderLineID
JOIN dbo.GoodsReceiptLine grl
    ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN dbo.GoodsReceiptHeader grh
    ON grl.GoodsReceiptID = grh.GoodsReceiptID
WHERE ird.SupplierID <> poh.SupplierID
   OR ird.ComponentID <> pol.ComponentID
   OR ird.ComponentID <> grl.ComponentID
   OR ird.PlantID <> grh.PlantID
   OR ird.WarehouseID <> grh.WarehouseID;

-- 6. InventoryReceiptDetail date lineage. Expected: no rows.
SELECT
    ird.InventoryReceiptDetailID,
    ird.POOrderDate,
    poh.OrderDate AS ExpectedPOOrderDate,
    ird.ExpectedDeliveryDate,
    ps.ScheduledDeliveryDate AS ExpectedScheduledDeliveryDate,
    ird.ActualDeliveryDate,
    grh.ReceiptDate AS ExpectedReceiptDate,
    ird.StockPostedDate
FROM dbo.InventoryReceiptDetail ird
JOIN dbo.PurchaseOrderHdr poh
    ON ird.PurchaseOrderID = poh.PurchaseOrderID
JOIN dbo.GoodsReceiptLine grl
    ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN dbo.GoodsReceiptHeader grh
    ON grl.GoodsReceiptID = grh.GoodsReceiptID
JOIN dbo.ShipmentLine sl
    ON grl.ShipmentLineID = sl.ShipmentLineID
JOIN dbo.POSchedule ps
    ON sl.POScheduleID = ps.POScheduleID
WHERE ird.POOrderDate <> poh.OrderDate
   OR ird.ExpectedDeliveryDate <> ps.ScheduledDeliveryDate
   OR ird.ActualDeliveryDate <> grh.ReceiptDate
   OR ird.StockPostedDate < ird.ActualDeliveryDate;

-- 7. InventoryReceiptDetail 2025-only date scope and cross-year flags. Expected: no rows.
SELECT
    InventoryReceiptDetailID,
    POOrderDate,
    ExpectedDeliveryDate,
    ActualDeliveryDate,
    StockPostedDate,
    OrderYear,
    DeliveryYear,
    CrossYearDeliveryFlag
FROM dbo.InventoryReceiptDetail
WHERE YEAR(POOrderDate) <> 2025
   OR YEAR(ExpectedDeliveryDate) <> 2025
   OR YEAR(ActualDeliveryDate) <> 2025
   OR YEAR(StockPostedDate) <> 2025
   OR OrderYear <> 2025
   OR DeliveryYear <> 2025
   OR CrossYearDeliveryFlag <> 0;

-- 8. InventoryReceiptDetail full-received quantity lineage. Expected: no rows.
SELECT
    ird.InventoryReceiptDetailID,
    pol.OrderedQuantity AS ExpectedOrderedQuantity,
    sl.ShippedQuantity AS ExpectedShippedQuantity,
    grl.ReceivedQuantity AS ExpectedReceivedQuantity,
    ir.InspectedQuantity AS ExpectedInspectedQuantity,
    ir.AcceptedQuantity AS ExpectedAcceptedQuantity,
    ir.RejectedQuantity AS ExpectedRejectedQuantity,
    ird.OrderedQuantity,
    ird.ShippedQuantity,
    ird.ReceivedQuantity,
    ird.InspectedQuantity,
    ird.AcceptedQuantity,
    ird.RejectedQuantity
FROM dbo.InventoryReceiptDetail ird
JOIN dbo.PurchaseOrderLine pol
    ON ird.PurchaseOrderLineID = pol.PurchaseOrderLineID
JOIN dbo.GoodsReceiptLine grl
    ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN dbo.ShipmentLine sl
    ON grl.ShipmentLineID = sl.ShipmentLineID
JOIN dbo.InspectionResult ir
    ON ird.InspectionResultID = ir.InspectionResultID
WHERE ABS(ird.OrderedQuantity - pol.OrderedQuantity) > 0.0001
   OR ABS(ird.ShippedQuantity - sl.ShippedQuantity) > 0.0001
   OR ABS(ird.ReceivedQuantity - grl.ReceivedQuantity) > 0.0001
   OR ABS(ird.InspectedQuantity - ir.InspectedQuantity) > 0.0001
   OR ABS(ird.AcceptedQuantity - ir.AcceptedQuantity) > 0.0001
   OR ABS(ird.RejectedQuantity - ir.RejectedQuantity) > 0.0001
   OR ABS(ird.OrderedQuantity - ird.ShippedQuantity) > 0.0001
   OR ABS(ird.OrderedQuantity - ird.ReceivedQuantity) > 0.0001
   OR ABS(ird.OrderedQuantity - ird.InspectedQuantity) > 0.0001
   OR ABS(ird.OrderedQuantity - ird.AcceptedQuantity) > 0.0001
   OR ABS(ird.RejectedQuantity) > 0.0001;

-- 9. InventoryReceiptDetail price and value formulas. Expected: no rows.
SELECT
    InventoryReceiptDetailID,
    OrderedUnitPrice,
    DeliveredUnitPrice,
    PriceDifference,
    PriceDifferencePct,
    OrderedValue,
    DeliveredValue,
    AcceptedStockValue
FROM dbo.InventoryReceiptDetail
WHERE ABS(PriceDifference - ROUND(DeliveredUnitPrice - OrderedUnitPrice, 2)) > 0.01
   OR ABS(
        PriceDifferencePct -
        CASE
            WHEN OrderedUnitPrice = 0 THEN 0
            ELSE ROUND(((DeliveredUnitPrice - OrderedUnitPrice) / OrderedUnitPrice) * 100, 2)
        END
   ) > 0.01
   OR ABS(OrderedValue - ROUND(OrderedQuantity * OrderedUnitPrice, 2)) > 0.01
   OR ABS(DeliveredValue - ROUND(ReceivedQuantity * DeliveredUnitPrice, 2)) > 0.01
   OR ABS(AcceptedStockValue - ROUND(AcceptedQuantity * DeliveredUnitPrice, 2)) > 0.01;

-- 10. InventoryReceiptDetail status logic. Expected: no rows.
SELECT
    InventoryReceiptDetailID,
    ExpectedDeliveryDate,
    ActualDeliveryDate,
    DeliveryStatus,
    PriceDifference,
    PriceVarianceStatus,
    InventoryReceiptStatus
FROM dbo.InventoryReceiptDetail
WHERE InventoryReceiptStatus <> 'Received'
   OR DeliveryStatus <>
        CASE
            WHEN ActualDeliveryDate < ExpectedDeliveryDate THEN 'Early'
            WHEN ActualDeliveryDate = ExpectedDeliveryDate THEN 'OnTime'
            ELSE 'Delayed'
        END
   OR PriceVarianceStatus <>
        CASE
            WHEN ABS(PriceDifference) <= 0.01 THEN 'NoChange'
            WHEN PriceDifference > 0 THEN 'PriceIncrease'
            ELSE 'PriceDecrease'
        END;

-- 11. InventoryTransaction vs InventoryReceiptDetail checks. Expected: no rows.
SELECT
    it.InventoryTransactionID,
    ird.InventoryReceiptDetailID,
    it.ReferenceDocument,
    CONCAT('IRD-', RIGHT('000000' + CAST(ird.InventoryReceiptDetailID AS varchar(20)), 6)) AS ExpectedReferenceDocument
FROM dbo.InventoryTransaction it
JOIN dbo.InventoryReceiptDetail ird
    ON it.InspectionResultID = ird.InspectionResultID
WHERE it.GoodsReceiptLineID <> ird.GoodsReceiptLineID
   OR it.PurchaseOrderLineID <> ird.PurchaseOrderLineID
   OR it.SupplierID <> ird.SupplierID
   OR it.ComponentID <> ird.ComponentID
   OR it.PlantID <> ird.PlantID
   OR it.WarehouseID <> ird.WarehouseID
   OR it.TransactionDate <> ird.StockPostedDate
   OR ABS(it.TransactionQuantity - ird.AcceptedQuantity) > 0.0001
   OR ABS(it.UnitPrice - ird.DeliveredUnitPrice) > 0.01
   OR ABS(it.InventoryValue - ROUND(it.TransactionQuantity * it.UnitPrice, 2)) > 0.01
   OR it.TransactionType <> 'StockIn'
   OR it.ReferenceDocument <> CONCAT('IRD-', RIGHT('000000' + CAST(ird.InventoryReceiptDetailID AS varchar(20)), 6));

-- 12. InventoryTransaction rows without InventoryReceiptDetail. Expected: MissingReceiptDetailRows = 0.
SELECT COUNT(*) AS MissingReceiptDetailRows
FROM dbo.InventoryTransaction it
LEFT JOIN dbo.InventoryReceiptDetail ird
    ON it.InspectionResultID = ird.InspectionResultID
WHERE ird.InventoryReceiptDetailID IS NULL;

-- 13. Inventory OnHandQuantity and OnHandValue rollup. Expected: no rows.
WITH TxnBalance AS (
    SELECT
        ComponentID,
        PlantID,
        WarehouseID,
        SUM(TransactionQuantity) AS ExpectedOnHandQuantity,
        SUM(InventoryValue) AS ExpectedOnHandValue
    FROM dbo.InventoryTransaction
    GROUP BY ComponentID, PlantID, WarehouseID
)
SELECT
    inv.InventoryID,
    inv.ComponentID,
    inv.PlantID,
    inv.WarehouseID,
    inv.OnHandQuantity,
    tb.ExpectedOnHandQuantity,
    inv.OnHandValue,
    tb.ExpectedOnHandValue
FROM dbo.Inventory inv
JOIN TxnBalance tb
    ON inv.ComponentID = tb.ComponentID
   AND inv.PlantID = tb.PlantID
   AND inv.WarehouseID = tb.WarehouseID
WHERE ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity) > 0.0001
   OR ABS(inv.OnHandValue - tb.ExpectedOnHandValue) > 0.01;

-- 14. Inventory AvailableQuantity and AvailableValue formulas. Expected: no rows.
SELECT
    InventoryID,
    OnHandQuantity,
    ReservedQuantity,
    AvailableQuantity,
    OnHandValue,
    AvailableValue
FROM dbo.Inventory
WHERE ABS(AvailableQuantity - (OnHandQuantity - ReservedQuantity)) > 0.0001
   OR ABS(
        AvailableValue -
        CASE
            WHEN OnHandQuantity = 0 THEN 0
            ELSE ROUND(AvailableQuantity * (OnHandValue / OnHandQuantity), 2)
        END
   ) > 0.01;

-- 15. Countable component quantity precision checks. Expected: no rows.
WITH CountableComponents AS (
    SELECT ComponentID
    FROM dbo.ComponentMaster
    WHERE UPPER(REPLACE(CAST(UOM AS varchar(80)), ' ', '')) IN (
        'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
        'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
    )
)
SELECT 'InventoryReceiptDetail.AcceptedQuantity decimal for countable UOM' AS IssueName,
    ird.InventoryReceiptDetailID AS RowID,
    ird.ComponentID,
    ird.AcceptedQuantity AS BadQuantity
FROM dbo.InventoryReceiptDetail ird
JOIN CountableComponents cc ON ird.ComponentID = cc.ComponentID
WHERE ABS(ird.AcceptedQuantity - FLOOR(ird.AcceptedQuantity)) > 0.0001

UNION ALL
SELECT 'InventoryTransaction.TransactionQuantity decimal for countable UOM',
    it.InventoryTransactionID,
    it.ComponentID,
    it.TransactionQuantity
FROM dbo.InventoryTransaction it
JOIN CountableComponents cc ON it.ComponentID = cc.ComponentID
WHERE ABS(it.TransactionQuantity - FLOOR(it.TransactionQuantity)) > 0.0001

UNION ALL
SELECT 'Inventory.OnHandQuantity decimal for countable UOM',
    inv.InventoryID,
    inv.ComponentID,
    inv.OnHandQuantity
FROM dbo.Inventory inv
JOIN CountableComponents cc ON inv.ComponentID = cc.ComponentID
WHERE ABS(inv.OnHandQuantity - FLOOR(inv.OnHandQuantity)) > 0.0001

UNION ALL
SELECT 'Inventory.AvailableQuantity decimal for countable UOM',
    inv.InventoryID,
    inv.ComponentID,
    inv.AvailableQuantity
FROM dbo.Inventory inv
JOIN CountableComponents cc ON inv.ComponentID = cc.ComponentID
WHERE ABS(inv.AvailableQuantity - FLOOR(inv.AvailableQuantity)) > 0.0001;

-- 16. Final InventoryReceiptDetail / InventoryTransaction / Inventory scorecard. Expected: all IssueCount = 0.
SELECT IssueName, IssueCount
FROM (
    SELECT 'InventoryReceiptDetail missing' AS IssueName, COUNT(*) AS IssueCount
    FROM (SELECT 1 AS ExpectedRow) x
    WHERE NOT EXISTS (
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = 'InventoryReceiptDetail'
    )

    UNION ALL
    SELECT 'InventoryBalance present', COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo'
      AND TABLE_NAME = 'InventoryBalance'

    UNION ALL
    SELECT 'Plant count should be 1', ABS(COUNT(*) - 1)
    FROM dbo.Plant

    UNION ALL
    SELECT 'Warehouse count should be 1', ABS(COUNT(*) - 1)
    FROM dbo.Warehouse

    UNION ALL
    SELECT 'Warehouse.PlantID not single PlantID', COUNT(*)
    FROM dbo.Warehouse
    WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)

    UNION ALL
    SELECT 'Invalid Procurement PlantID references', SUM(IssueCount)
    FROM (
        SELECT COUNT(*) AS IssueCount FROM dbo.Warehouse WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.GoodsReceiptHeader WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.InventoryReceiptDetail WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.InventoryTransaction WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.Inventory WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.PurchaseRequisition WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.PurchaseOrderHdr WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    ) plant_scope

    UNION ALL
    SELECT 'Invalid Procurement WarehouseID references', SUM(IssueCount)
    FROM (
        SELECT COUNT(*) AS IssueCount FROM dbo.GoodsReceiptHeader WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
        UNION ALL SELECT COUNT(*) FROM dbo.InventoryReceiptDetail WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
        UNION ALL SELECT COUNT(*) FROM dbo.InventoryTransaction WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
        UNION ALL SELECT COUNT(*) FROM dbo.Inventory WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
    ) warehouse_scope

    UNION ALL
    SELECT 'InventoryReceiptDetail duplicate PK', COUNT(*)
    FROM (
        SELECT InventoryReceiptDetailID
        FROM dbo.InventoryReceiptDetail
        GROUP BY InventoryReceiptDetailID
        HAVING InventoryReceiptDetailID IS NULL OR COUNT(*) > 1
    ) x

    UNION ALL
    SELECT 'InventoryReceiptDetail FK orphan', SUM(IssueCount)
    FROM (
        SELECT COUNT(*) AS IssueCount
        FROM dbo.InventoryReceiptDetail ird
        LEFT JOIN dbo.InspectionResult ir ON ird.InspectionResultID = ir.InspectionResultID
        WHERE ir.InspectionResultID IS NULL
        UNION ALL
        SELECT COUNT(*)
        FROM dbo.InventoryReceiptDetail ird
        LEFT JOIN dbo.GoodsReceiptLine grl ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
        WHERE grl.GoodsReceiptLineID IS NULL
        UNION ALL
        SELECT COUNT(*)
        FROM dbo.InventoryReceiptDetail ird
        LEFT JOIN dbo.PurchaseOrderLine pol ON ird.PurchaseOrderLineID = pol.PurchaseOrderLineID
        WHERE pol.PurchaseOrderLineID IS NULL
    ) orphan_counts

    UNION ALL
    SELECT 'InventoryReceiptDetail lineage mismatch', COUNT(*)
    FROM dbo.InventoryReceiptDetail ird
    JOIN dbo.PurchaseOrderHdr poh ON ird.PurchaseOrderID = poh.PurchaseOrderID
    JOIN dbo.PurchaseOrderLine pol ON ird.PurchaseOrderLineID = pol.PurchaseOrderLineID
    JOIN dbo.GoodsReceiptLine grl ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
    JOIN dbo.GoodsReceiptHeader grh ON grl.GoodsReceiptID = grh.GoodsReceiptID
    WHERE ird.SupplierID <> poh.SupplierID
       OR ird.ComponentID <> pol.ComponentID
       OR ird.ComponentID <> grl.ComponentID
       OR ird.PlantID <> grh.PlantID
       OR ird.WarehouseID <> grh.WarehouseID

    UNION ALL
    SELECT 'InventoryReceiptDetail date mismatch or non-2025 date', COUNT(*)
    FROM dbo.InventoryReceiptDetail ird
    JOIN dbo.PurchaseOrderHdr poh ON ird.PurchaseOrderID = poh.PurchaseOrderID
    JOIN dbo.GoodsReceiptLine grl ON ird.GoodsReceiptLineID = grl.GoodsReceiptLineID
    JOIN dbo.GoodsReceiptHeader grh ON grl.GoodsReceiptID = grh.GoodsReceiptID
    JOIN dbo.ShipmentLine sl ON grl.ShipmentLineID = sl.ShipmentLineID
    JOIN dbo.POSchedule ps ON sl.POScheduleID = ps.POScheduleID
    WHERE ird.POOrderDate <> poh.OrderDate
       OR ird.ExpectedDeliveryDate <> ps.ScheduledDeliveryDate
       OR ird.ActualDeliveryDate <> grh.ReceiptDate
       OR ird.StockPostedDate < ird.ActualDeliveryDate
       OR YEAR(ird.POOrderDate) <> 2025
       OR YEAR(ird.ExpectedDeliveryDate) <> 2025
       OR YEAR(ird.ActualDeliveryDate) <> 2025
       OR YEAR(ird.StockPostedDate) <> 2025
       OR ird.CrossYearDeliveryFlag <> 0
       OR ird.OrderYear <> 2025
       OR ird.DeliveryYear <> 2025

    UNION ALL
    SELECT 'InventoryReceiptDetail price/value formula mismatch', COUNT(*)
    FROM dbo.InventoryReceiptDetail
    WHERE ABS(PriceDifference - ROUND(DeliveredUnitPrice - OrderedUnitPrice, 2)) > 0.01
       OR ABS(
            PriceDifferencePct -
            CASE
                WHEN OrderedUnitPrice = 0 THEN 0
                ELSE ROUND(((DeliveredUnitPrice - OrderedUnitPrice) / OrderedUnitPrice) * 100, 2)
            END
       ) > 0.01
       OR ABS(OrderedValue - ROUND(OrderedQuantity * OrderedUnitPrice, 2)) > 0.01
       OR ABS(DeliveredValue - ROUND(ReceivedQuantity * DeliveredUnitPrice, 2)) > 0.01
       OR ABS(AcceptedStockValue - ROUND(AcceptedQuantity * DeliveredUnitPrice, 2)) > 0.01

    UNION ALL
    SELECT 'InventoryReceiptDetail status mismatch', COUNT(*)
    FROM dbo.InventoryReceiptDetail
    WHERE InventoryReceiptStatus <> 'Received'
       OR DeliveryStatus <>
            CASE
                WHEN ActualDeliveryDate < ExpectedDeliveryDate THEN 'Early'
                WHEN ActualDeliveryDate = ExpectedDeliveryDate THEN 'OnTime'
                ELSE 'Delayed'
            END
       OR PriceVarianceStatus <>
            CASE
                WHEN ABS(PriceDifference) <= 0.01 THEN 'NoChange'
                WHEN PriceDifference > 0 THEN 'PriceIncrease'
                ELSE 'PriceDecrease'
            END

    UNION ALL
    SELECT 'InventoryTransaction vs InventoryReceiptDetail mismatch', COUNT(*)
    FROM dbo.InventoryTransaction it
    JOIN dbo.InventoryReceiptDetail ird ON it.InspectionResultID = ird.InspectionResultID
    WHERE it.GoodsReceiptLineID <> ird.GoodsReceiptLineID
       OR it.PurchaseOrderLineID <> ird.PurchaseOrderLineID
       OR it.SupplierID <> ird.SupplierID
       OR it.ComponentID <> ird.ComponentID
       OR it.PlantID <> ird.PlantID
       OR it.WarehouseID <> ird.WarehouseID
       OR it.TransactionDate <> ird.StockPostedDate
       OR ABS(it.TransactionQuantity - ird.AcceptedQuantity) > 0.0001
       OR ABS(it.UnitPrice - ird.DeliveredUnitPrice) > 0.01
       OR ABS(it.InventoryValue - ROUND(it.TransactionQuantity * it.UnitPrice, 2)) > 0.01
       OR it.TransactionType <> 'StockIn'
       OR it.ReferenceDocument <> CONCAT('IRD-', RIGHT('000000' + CAST(ird.InventoryReceiptDetailID AS varchar(20)), 6))

    UNION ALL
    SELECT 'Inventory OnHandQuantity / OnHandValue rollup mismatch', COUNT(*)
    FROM dbo.Inventory inv
    JOIN (
        SELECT
            ComponentID,
            PlantID,
            WarehouseID,
            SUM(TransactionQuantity) AS ExpectedOnHandQuantity,
            SUM(InventoryValue) AS ExpectedOnHandValue
        FROM dbo.InventoryTransaction
        GROUP BY ComponentID, PlantID, WarehouseID
    ) tb
        ON inv.ComponentID = tb.ComponentID
       AND inv.PlantID = tb.PlantID
       AND inv.WarehouseID = tb.WarehouseID
    WHERE ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity) > 0.0001
       OR ABS(inv.OnHandValue - tb.ExpectedOnHandValue) > 0.01

    UNION ALL
    SELECT 'Inventory AvailableQuantity / AvailableValue formula mismatch', COUNT(*)
    FROM dbo.Inventory
    WHERE ABS(AvailableQuantity - (OnHandQuantity - ReservedQuantity)) > 0.0001
       OR ABS(
            AvailableValue -
            CASE
                WHEN OnHandQuantity = 0 THEN 0
                ELSE ROUND(AvailableQuantity * (OnHandValue / OnHandQuantity), 2)
            END
       ) > 0.01

    UNION ALL
    SELECT 'Countable component quantity precision mismatch', COUNT(*)
    FROM (
        SELECT ird.InventoryReceiptDetailID AS RowID
        FROM dbo.InventoryReceiptDetail ird
        JOIN dbo.ComponentMaster cm ON ird.ComponentID = cm.ComponentID
        WHERE UPPER(REPLACE(CAST(cm.UOM AS varchar(80)), ' ', '')) IN (
            'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
            'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
        )
          AND ABS(ird.AcceptedQuantity - FLOOR(ird.AcceptedQuantity)) > 0.0001
        UNION ALL
        SELECT it.InventoryTransactionID
        FROM dbo.InventoryTransaction it
        JOIN dbo.ComponentMaster cm ON it.ComponentID = cm.ComponentID
        WHERE UPPER(REPLACE(CAST(cm.UOM AS varchar(80)), ' ', '')) IN (
            'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
            'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
        )
          AND ABS(it.TransactionQuantity - FLOOR(it.TransactionQuantity)) > 0.0001
        UNION ALL
        SELECT inv.InventoryID
        FROM dbo.Inventory inv
        JOIN dbo.ComponentMaster cm ON inv.ComponentID = cm.ComponentID
        WHERE UPPER(REPLACE(CAST(cm.UOM AS varchar(80)), ' ', '')) IN (
            'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
            'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
        )
          AND (
              ABS(inv.OnHandQuantity - FLOOR(inv.OnHandQuantity)) > 0.0001
              OR ABS(inv.AvailableQuantity - FLOOR(inv.AvailableQuantity)) > 0.0001
          )
    ) precision_issues
) scorecard
ORDER BY IssueName;
