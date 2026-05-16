/*
Procurement v2 lifecycle quantity and status SQL validation checks.

Purpose:
Validate the current 25-table Procurement v2 full-received lifecycle in SQL Server.

Expected:
- Detail checks return no rows.
- Final scorecards return IssueName / IssueCount with all IssueCount = 0.
- InventoryBalance is absent.

Lifecycle:
PurchaseReqLine.RequestedQuantity
-> RFQLine.RFQQuantity
-> SupplierQuotationLn.QuotedQuantity
-> PurchaseOrderLine.OrderedQuantity
-> POSchedule.ScheduledQuantity
-> ShipmentLine.ShippedQuantity
-> GoodsReceiptLine.ReceivedQuantity
-> InspectionResult.AcceptedQuantity
-> InventoryReceiptDetail.AcceptedQuantity
-> InventoryTransaction.TransactionQuantity
-> Inventory.OnHandQuantity
*/

-- 1. Procurement v2 25 expected tables. Expected: no rows.
WITH ExpectedTables AS (
    SELECT TableName
    FROM (VALUES
        ('SupplierMaster'),
        ('SupplierComponent'),
        ('ComponentMaster'),
        ('Plant'),
        ('Warehouse'),
        ('PurchaseRequisition'),
        ('PurchaseReqLine'),
        ('RFQHeader'),
        ('RFQLine'),
        ('SupplierQuotation'),
        ('SupplierQuotationLn'),
        ('PurchaseOrderHdr'),
        ('PurchaseOrderLine'),
        ('POSchedule'),
        ('ShipmentHdr'),
        ('ShipmentLine'),
        ('GoodsReceiptHeader'),
        ('GoodsReceiptLine'),
        ('IncomingInspection'),
        ('InspectionResult'),
        ('InventoryReceiptDetail'),
        ('InventoryTransaction'),
        ('Inventory'),
        ('SupplierInvoice'),
        ('PaymentTransaction')
    ) v(TableName)
)
SELECT e.TableName AS MissingExpectedTable
FROM ExpectedTables e
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
WHERE t.TABLE_NAME IS NULL;

-- 2. InventoryBalance absence. Expected: InventoryBalanceObjectCount = 0.
SELECT COUNT(*) AS InventoryBalanceObjectCount
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'InventoryBalance';

-- 2A. Simplified operating scope summary. Expected: one Plant and one Warehouse.
SELECT 'Plant' AS TableName, COUNT(*) AS RowCount
FROM dbo.Plant
UNION ALL
SELECT 'Warehouse', COUNT(*)
FROM dbo.Warehouse;

-- 2B. Demo-friendly location summary. Expected: DistinctPlantCount and DistinctWarehouseCount are 1 where applicable.
SELECT 'Warehouse' AS TableName,
       COUNT(DISTINCT PlantID) AS DistinctPlantCount,
       COUNT(DISTINCT WarehouseID) AS DistinctWarehouseCount
FROM dbo.Warehouse
UNION ALL
SELECT 'PurchaseRequisition', COUNT(DISTINCT PlantID), NULL
FROM dbo.PurchaseRequisition
UNION ALL
SELECT 'PurchaseOrderHdr', COUNT(DISTINCT PlantID), NULL
FROM dbo.PurchaseOrderHdr
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
FROM dbo.Inventory;

-- 2C. One Plant / one Warehouse scope checks. Expected: no rows.
WITH SinglePlant AS (
    SELECT MIN(PlantID) AS PlantID
    FROM dbo.Plant
),
SingleWarehouse AS (
    SELECT MIN(WarehouseID) AS WarehouseID
    FROM dbo.Warehouse
)
SELECT 'Invalid Procurement PlantID reference' AS IssueName, 'Warehouse' AS TableName, WarehouseID AS RecordID, PlantID AS BadValue
FROM dbo.Warehouse
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement PlantID reference', 'PurchaseRequisition', RequisitionID, PlantID
FROM dbo.PurchaseRequisition
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement PlantID reference', 'PurchaseOrderHdr', PurchaseOrderID, PlantID
FROM dbo.PurchaseOrderHdr
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement PlantID reference', 'GoodsReceiptHeader', GoodsReceiptID, PlantID
FROM dbo.GoodsReceiptHeader
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement PlantID reference', 'InventoryReceiptDetail', InventoryReceiptDetailID, PlantID
FROM dbo.InventoryReceiptDetail
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement PlantID reference', 'InventoryTransaction', InventoryTransactionID, PlantID
FROM dbo.InventoryTransaction
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement PlantID reference', 'Inventory', InventoryID, PlantID
FROM dbo.Inventory
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL
SELECT 'Invalid Procurement WarehouseID reference', 'GoodsReceiptHeader', GoodsReceiptID, WarehouseID
FROM dbo.GoodsReceiptHeader
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL
SELECT 'Invalid Procurement WarehouseID reference', 'InventoryReceiptDetail', InventoryReceiptDetailID, WarehouseID
FROM dbo.InventoryReceiptDetail
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL
SELECT 'Invalid Procurement WarehouseID reference', 'InventoryTransaction', InventoryTransactionID, WarehouseID
FROM dbo.InventoryTransaction
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL
SELECT 'Invalid Procurement WarehouseID reference', 'Inventory', InventoryID, WarehouseID
FROM dbo.Inventory
WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse);

-- 3. Required inventory tables. Expected: no rows.
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

-- 4. POStatus = Received only. Expected: no rows.
SELECT POStatus, COUNT(*) AS RowCount
FROM dbo.PurchaseOrderHdr
WHERE POStatus <> 'Received'
GROUP BY POStatus;

-- 5. LineStatus = Received only. Expected: no rows.
SELECT LineStatus, COUNT(*) AS RowCount
FROM dbo.PurchaseOrderLine
WHERE LineStatus <> 'Received'
GROUP BY LineStatus;

-- 6. Invalid lifecycle statuses. Expected: no rows.
SELECT 'PurchaseOrderHdr.POStatus' AS StatusColumn, POStatus AS InvalidStatus, COUNT(*) AS RowCount
FROM dbo.PurchaseOrderHdr
WHERE POStatus IN ('Sent', 'PartiallyReceived', 'Closed', 'PartiallyShipped', 'PartiallyDelivered', 'ShortReceived', 'Damaged', 'PartiallyRejected', 'Failed')
GROUP BY POStatus

UNION ALL
SELECT 'PurchaseOrderLine.LineStatus', LineStatus, COUNT(*)
FROM dbo.PurchaseOrderLine
WHERE LineStatus IN ('Sent', 'PartiallyReceived', 'Closed', 'PartiallyShipped', 'PartiallyDelivered', 'ShortReceived', 'Damaged', 'PartiallyRejected', 'Failed')
GROUP BY LineStatus

UNION ALL
SELECT 'POSchedule.ScheduleStatus', ScheduleStatus, COUNT(*)
FROM dbo.POSchedule
WHERE ScheduleStatus IN ('Sent', 'PartiallyReceived', 'Closed', 'PartiallyShipped', 'PartiallyDelivered', 'ShortReceived', 'Damaged', 'PartiallyRejected', 'Failed')
GROUP BY ScheduleStatus

UNION ALL
SELECT 'ShipmentHdr.ShipmentStatus', ShipmentStatus, COUNT(*)
FROM dbo.ShipmentHdr
WHERE ShipmentStatus IN ('Sent', 'PartiallyReceived', 'Closed', 'PartiallyShipped', 'PartiallyDelivered', 'ShortReceived', 'Damaged', 'PartiallyRejected', 'Failed')
GROUP BY ShipmentStatus

UNION ALL
SELECT 'GoodsReceiptHeader.ReceiptStatus', ReceiptStatus, COUNT(*)
FROM dbo.GoodsReceiptHeader
WHERE ReceiptStatus IN ('Sent', 'PartiallyReceived', 'Closed', 'PartiallyShipped', 'PartiallyDelivered', 'ShortReceived', 'Damaged', 'PartiallyRejected', 'Failed')
GROUP BY ReceiptStatus

UNION ALL
SELECT 'InspectionResult.ResultStatus', ResultStatus, COUNT(*)
FROM dbo.InspectionResult
WHERE ResultStatus IN ('Sent', 'PartiallyReceived', 'Closed', 'PartiallyShipped', 'PartiallyDelivered', 'ShortReceived', 'Damaged', 'PartiallyRejected', 'Failed')
GROUP BY ResultStatus;

-- 7. RFQQuantity <= RequestedQuantity. Expected: no rows.
SELECT
    rfl.RFQLineID,
    rfl.RequisitionLineID,
    prl.RequestedQuantity,
    rfl.RFQQuantity,
    rfl.RFQQuantity - prl.RequestedQuantity AS Difference
FROM dbo.RFQLine rfl
JOIN dbo.PurchaseReqLine prl
    ON rfl.RequisitionLineID = prl.RequisitionLineID
WHERE rfl.RFQQuantity > prl.RequestedQuantity + 0.0001;

-- 8. QuotedQuantity <= RFQQuantity. Expected: no rows.
SELECT
    sqln.QuotationLineID,
    sqln.RFQLineID,
    rfl.RFQQuantity,
    sqln.QuotedQuantity,
    sqln.QuotedQuantity - rfl.RFQQuantity AS Difference
FROM dbo.SupplierQuotationLn sqln
JOIN dbo.RFQLine rfl
    ON sqln.RFQLineID = rfl.RFQLineID
WHERE sqln.QuotedQuantity > rfl.RFQQuantity + 0.0001;

-- 9. OrderedQuantity <= awarded QuotedQuantity. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.QuotationLineID,
    sqln.QuotedQuantity,
    pol.OrderedQuantity,
    pol.OrderedQuantity - sqln.QuotedQuantity AS Difference
FROM dbo.PurchaseOrderLine pol
JOIN dbo.SupplierQuotationLn sqln
    ON pol.QuotationLineID = sqln.QuotationLineID
WHERE pol.OrderedQuantity > sqln.QuotedQuantity + 0.0001;

-- 10. OrderedQuantity total > Awarded QuotedQuantity. Expected: no rows.
SELECT
    sqln.QuotationLineID,
    sqln.QuotedQuantity,
    SUM(pol.OrderedQuantity) AS TotalOrderedQuantity,
    SUM(pol.OrderedQuantity) - sqln.QuotedQuantity AS Difference
FROM dbo.SupplierQuotationLn sqln
JOIN dbo.PurchaseOrderLine pol
    ON sqln.QuotationLineID = pol.QuotationLineID
GROUP BY
    sqln.QuotationLineID,
    sqln.QuotedQuantity
HAVING SUM(pol.OrderedQuantity) > sqln.QuotedQuantity + 0.0001;

-- 11. ScheduledQuantity total > OrderedQuantity. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    SUM(ps.ScheduledQuantity) AS TotalScheduledQuantity,
    SUM(ps.ScheduledQuantity) - pol.OrderedQuantity AS Difference
FROM dbo.PurchaseOrderLine pol
JOIN dbo.POSchedule ps
    ON pol.PurchaseOrderLineID = ps.PurchaseOrderLineID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity
HAVING SUM(ps.ScheduledQuantity) > pol.OrderedQuantity + 0.0001;

-- 12. Full-received quantity equality by PurchaseOrderLineID. Expected: no rows.
WITH ScheduleQty AS (
    SELECT PurchaseOrderLineID, SUM(ScheduledQuantity) AS TotalScheduledQuantity
    FROM dbo.POSchedule
    GROUP BY PurchaseOrderLineID
),
ShipmentQty AS (
    SELECT PurchaseOrderLineID, SUM(ShippedQuantity) AS TotalShippedQuantity
    FROM dbo.ShipmentLine
    GROUP BY PurchaseOrderLineID
),
ReceiptQty AS (
    SELECT PurchaseOrderLineID, SUM(ReceivedQuantity) AS TotalReceivedQuantity
    FROM dbo.GoodsReceiptLine
    GROUP BY PurchaseOrderLineID
),
InspectionQty AS (
    SELECT
        grl.PurchaseOrderLineID,
        SUM(ir.InspectedQuantity) AS TotalInspectedQuantity,
        SUM(ir.AcceptedQuantity) AS TotalAcceptedQuantity,
        SUM(ir.RejectedQuantity) AS TotalRejectedQuantity
    FROM dbo.GoodsReceiptLine grl
    JOIN dbo.IncomingInspection ii
        ON grl.GoodsReceiptLineID = ii.GoodsReceiptLineID
    JOIN dbo.InspectionResult ir
        ON ii.InspectionID = ir.InspectionID
    GROUP BY grl.PurchaseOrderLineID
),
ReceiptDetailQty AS (
    SELECT PurchaseOrderLineID, SUM(AcceptedQuantity) AS TotalReceiptDetailAcceptedQuantity
    FROM dbo.InventoryReceiptDetail
    GROUP BY PurchaseOrderLineID
),
StockInQty AS (
    SELECT PurchaseOrderLineID, SUM(TransactionQuantity) AS TotalStockInQuantity
    FROM dbo.InventoryTransaction
    GROUP BY PurchaseOrderLineID
)
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    sq.TotalScheduledQuantity,
    sh.TotalShippedQuantity,
    rq.TotalReceivedQuantity,
    iq.TotalInspectedQuantity,
    iq.TotalAcceptedQuantity,
    rdq.TotalReceiptDetailAcceptedQuantity,
    siq.TotalStockInQuantity
FROM dbo.PurchaseOrderLine pol
LEFT JOIN ScheduleQty sq ON pol.PurchaseOrderLineID = sq.PurchaseOrderLineID
LEFT JOIN ShipmentQty sh ON pol.PurchaseOrderLineID = sh.PurchaseOrderLineID
LEFT JOIN ReceiptQty rq ON pol.PurchaseOrderLineID = rq.PurchaseOrderLineID
LEFT JOIN InspectionQty iq ON pol.PurchaseOrderLineID = iq.PurchaseOrderLineID
LEFT JOIN ReceiptDetailQty rdq ON pol.PurchaseOrderLineID = rdq.PurchaseOrderLineID
LEFT JOIN StockInQty siq ON pol.PurchaseOrderLineID = siq.PurchaseOrderLineID
WHERE ABS(pol.OrderedQuantity - COALESCE(sq.TotalScheduledQuantity, 0)) > 0.0001
   OR ABS(pol.OrderedQuantity - COALESCE(sh.TotalShippedQuantity, 0)) > 0.0001
   OR ABS(pol.OrderedQuantity - COALESCE(rq.TotalReceivedQuantity, 0)) > 0.0001
   OR ABS(pol.OrderedQuantity - COALESCE(iq.TotalInspectedQuantity, 0)) > 0.0001
   OR ABS(pol.OrderedQuantity - COALESCE(iq.TotalAcceptedQuantity, 0)) > 0.0001
   OR ABS(pol.OrderedQuantity - COALESCE(rdq.TotalReceiptDetailAcceptedQuantity, 0)) > 0.0001
   OR ABS(pol.OrderedQuantity - COALESCE(siq.TotalStockInQuantity, 0)) > 0.0001;

-- 13. Rejected/short/damaged quantities are zero. Expected: no rows.
SELECT 'InspectionResult.RejectedQuantity' AS QuantityColumn, InspectionResultID AS RowID, RejectedQuantity AS BadQuantity
FROM dbo.InspectionResult
WHERE ABS(RejectedQuantity) > 0.0001

UNION ALL
SELECT 'GoodsReceiptLine.ShortQuantity', GoodsReceiptLineID, ShortQuantity
FROM dbo.GoodsReceiptLine
WHERE ABS(ShortQuantity) > 0.0001

UNION ALL
SELECT 'GoodsReceiptLine.DamagedQuantity', GoodsReceiptLineID, DamagedQuantity
FROM dbo.GoodsReceiptLine
WHERE ABS(DamagedQuantity) > 0.0001;

-- 14. InventoryTransaction quantity = InventoryReceiptDetail accepted quantity. Expected: no rows.
SELECT
    it.InventoryTransactionID,
    ird.InventoryReceiptDetailID,
    ird.AcceptedQuantity,
    it.TransactionQuantity,
    it.TransactionQuantity - ird.AcceptedQuantity AS Difference
FROM dbo.InventoryTransaction it
JOIN dbo.InventoryReceiptDetail ird
    ON it.InspectionResultID = ird.InspectionResultID
WHERE ABS(it.TransactionQuantity - ird.AcceptedQuantity) > 0.0001;

-- 15. StockIn total > OrderedQuantity. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.PurchaseOrderID,
    pol.ComponentID,
    pol.OrderedQuantity,
    SUM(it.TransactionQuantity) AS TotalStockInQuantity,
    SUM(it.TransactionQuantity) - pol.OrderedQuantity AS Difference
FROM dbo.PurchaseOrderLine pol
JOIN dbo.InventoryTransaction it
    ON pol.PurchaseOrderLineID = it.PurchaseOrderLineID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.PurchaseOrderID,
    pol.ComponentID,
    pol.OrderedQuantity
HAVING SUM(it.TransactionQuantity) > pol.OrderedQuantity + 0.0001;

-- 16. Countable component lifecycle quantity precision checks. Expected: no rows.
WITH CountableComponents AS (
    SELECT ComponentID
    FROM dbo.ComponentMaster
    WHERE UPPER(REPLACE(CAST(UOM AS varchar(80)), ' ', '')) IN (
        'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
        'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
    )
)
SELECT 'PurchaseOrderLine.OrderedQuantity decimal for countable UOM' AS IssueName,
    pol.PurchaseOrderLineID AS RowID,
    pol.ComponentID,
    pol.OrderedQuantity AS BadQuantity
FROM dbo.PurchaseOrderLine pol
JOIN CountableComponents cc ON pol.ComponentID = cc.ComponentID
WHERE ABS(pol.OrderedQuantity - FLOOR(pol.OrderedQuantity)) > 0.0001

UNION ALL
SELECT 'InspectionResult.AcceptedQuantity decimal for countable UOM',
    ir.InspectionResultID,
    grl.ComponentID,
    ir.AcceptedQuantity
FROM dbo.InspectionResult ir
JOIN dbo.IncomingInspection ii ON ir.InspectionID = ii.InspectionID
JOIN dbo.GoodsReceiptLine grl ON ii.GoodsReceiptLineID = grl.GoodsReceiptLineID
JOIN CountableComponents cc ON grl.ComponentID = cc.ComponentID
WHERE ABS(ir.AcceptedQuantity - FLOOR(ir.AcceptedQuantity)) > 0.0001

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
WHERE ABS(inv.OnHandQuantity - FLOOR(inv.OnHandQuantity)) > 0.0001;

-- 17. Inventory OnHandQuantity mismatch. Expected: no rows.
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
    inv.InventoryID,
    inv.ComponentID,
    inv.PlantID,
    inv.WarehouseID,
    inv.OnHandQuantity,
    tb.ExpectedOnHandQuantity,
    inv.OnHandQuantity - tb.ExpectedOnHandQuantity AS Difference
FROM dbo.Inventory inv
JOIN TxnBalance tb
    ON inv.ComponentID = tb.ComponentID
   AND inv.PlantID = tb.PlantID
   AND inv.WarehouseID = tb.WarehouseID
WHERE ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity) > 0.0001;

-- 18. Final lifecycle quantity and status scorecard. Expected: all IssueCount = 0.
WITH ExpectedTables AS (
    SELECT TableName
    FROM (VALUES
        ('SupplierMaster'), ('SupplierComponent'), ('ComponentMaster'), ('Plant'), ('Warehouse'),
        ('PurchaseRequisition'), ('PurchaseReqLine'), ('RFQHeader'), ('RFQLine'),
        ('SupplierQuotation'), ('SupplierQuotationLn'), ('PurchaseOrderHdr'), ('PurchaseOrderLine'),
        ('POSchedule'), ('ShipmentHdr'), ('ShipmentLine'), ('GoodsReceiptHeader'), ('GoodsReceiptLine'),
        ('IncomingInspection'), ('InspectionResult'), ('InventoryReceiptDetail'), ('InventoryTransaction'),
        ('Inventory'), ('SupplierInvoice'), ('PaymentTransaction')
    ) v(TableName)
),
ScheduleQty AS (
    SELECT PurchaseOrderLineID, SUM(ScheduledQuantity) AS TotalScheduledQuantity
    FROM dbo.POSchedule
    GROUP BY PurchaseOrderLineID
),
ShipmentQty AS (
    SELECT PurchaseOrderLineID, SUM(ShippedQuantity) AS TotalShippedQuantity
    FROM dbo.ShipmentLine
    GROUP BY PurchaseOrderLineID
),
ReceiptQty AS (
    SELECT PurchaseOrderLineID, SUM(ReceivedQuantity) AS TotalReceivedQuantity
    FROM dbo.GoodsReceiptLine
    GROUP BY PurchaseOrderLineID
),
InspectionQty AS (
    SELECT
        grl.PurchaseOrderLineID,
        SUM(ir.InspectedQuantity) AS TotalInspectedQuantity,
        SUM(ir.AcceptedQuantity) AS TotalAcceptedQuantity
    FROM dbo.GoodsReceiptLine grl
    JOIN dbo.IncomingInspection ii ON grl.GoodsReceiptLineID = ii.GoodsReceiptLineID
    JOIN dbo.InspectionResult ir ON ii.InspectionID = ir.InspectionID
    GROUP BY grl.PurchaseOrderLineID
),
ReceiptDetailQty AS (
    SELECT PurchaseOrderLineID, SUM(AcceptedQuantity) AS TotalReceiptDetailAcceptedQuantity
    FROM dbo.InventoryReceiptDetail
    GROUP BY PurchaseOrderLineID
),
StockInQty AS (
    SELECT PurchaseOrderLineID, SUM(TransactionQuantity) AS TotalStockInQuantity
    FROM dbo.InventoryTransaction
    GROUP BY PurchaseOrderLineID
)
SELECT IssueName, IssueCount
FROM (
    SELECT 'Missing expected v2 tables (25 expected tables)' AS IssueName, COUNT(*) AS IssueCount
    FROM ExpectedTables e
    LEFT JOIN INFORMATION_SCHEMA.TABLES t
        ON t.TABLE_SCHEMA = 'dbo' AND t.TABLE_NAME = e.TableName
    WHERE t.TABLE_NAME IS NULL

    UNION ALL
    SELECT 'InventoryBalance present', COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'InventoryBalance'

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
        UNION ALL SELECT COUNT(*) FROM dbo.PurchaseRequisition WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.PurchaseOrderHdr WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.GoodsReceiptHeader WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.InventoryReceiptDetail WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.InventoryTransaction WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
        UNION ALL SELECT COUNT(*) FROM dbo.Inventory WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
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
    SELECT 'POStatus not Received', COUNT(*)
    FROM dbo.PurchaseOrderHdr
    WHERE POStatus <> 'Received'

    UNION ALL
    SELECT 'LineStatus not Received', COUNT(*)
    FROM dbo.PurchaseOrderLine
    WHERE LineStatus <> 'Received'

    UNION ALL
    SELECT 'RFQQuantity > RequestedQuantity', COUNT(*)
    FROM dbo.RFQLine rfl
    JOIN dbo.PurchaseReqLine prl ON rfl.RequisitionLineID = prl.RequisitionLineID
    WHERE rfl.RFQQuantity > prl.RequestedQuantity + 0.0001

    UNION ALL
    SELECT 'QuotedQuantity > RFQQuantity', COUNT(*)
    FROM dbo.SupplierQuotationLn sqln
    JOIN dbo.RFQLine rfl ON sqln.RFQLineID = rfl.RFQLineID
    WHERE sqln.QuotedQuantity > rfl.RFQQuantity + 0.0001

    UNION ALL
    SELECT 'OrderedQuantity total > Awarded QuotedQuantity', COUNT(*)
    FROM (
        SELECT sqln.QuotationLineID, sqln.QuotedQuantity, SUM(pol.OrderedQuantity) AS TotalOrderedQuantity
        FROM dbo.SupplierQuotationLn sqln
        JOIN dbo.PurchaseOrderLine pol ON sqln.QuotationLineID = pol.QuotationLineID
        GROUP BY sqln.QuotationLineID, sqln.QuotedQuantity
    ) x
    WHERE TotalOrderedQuantity > QuotedQuantity + 0.0001

    UNION ALL
    SELECT 'ScheduledQuantity total > OrderedQuantity', COUNT(*)
    FROM (
        SELECT pol.PurchaseOrderLineID, pol.OrderedQuantity, SUM(ps.ScheduledQuantity) AS TotalScheduledQuantity
        FROM dbo.PurchaseOrderLine pol
        JOIN dbo.POSchedule ps ON pol.PurchaseOrderLineID = ps.PurchaseOrderLineID
        GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
    ) x
    WHERE TotalScheduledQuantity > OrderedQuantity + 0.0001

    UNION ALL
    SELECT 'Full-received quantity equality mismatch', COUNT(*)
    FROM dbo.PurchaseOrderLine pol
    LEFT JOIN ScheduleQty sq ON pol.PurchaseOrderLineID = sq.PurchaseOrderLineID
    LEFT JOIN ShipmentQty sh ON pol.PurchaseOrderLineID = sh.PurchaseOrderLineID
    LEFT JOIN ReceiptQty rq ON pol.PurchaseOrderLineID = rq.PurchaseOrderLineID
    LEFT JOIN InspectionQty iq ON pol.PurchaseOrderLineID = iq.PurchaseOrderLineID
    LEFT JOIN ReceiptDetailQty rdq ON pol.PurchaseOrderLineID = rdq.PurchaseOrderLineID
    LEFT JOIN StockInQty siq ON pol.PurchaseOrderLineID = siq.PurchaseOrderLineID
    WHERE ABS(pol.OrderedQuantity - COALESCE(sq.TotalScheduledQuantity, 0)) > 0.0001
       OR ABS(pol.OrderedQuantity - COALESCE(sh.TotalShippedQuantity, 0)) > 0.0001
       OR ABS(pol.OrderedQuantity - COALESCE(rq.TotalReceivedQuantity, 0)) > 0.0001
       OR ABS(pol.OrderedQuantity - COALESCE(iq.TotalInspectedQuantity, 0)) > 0.0001
       OR ABS(pol.OrderedQuantity - COALESCE(iq.TotalAcceptedQuantity, 0)) > 0.0001
       OR ABS(pol.OrderedQuantity - COALESCE(rdq.TotalReceiptDetailAcceptedQuantity, 0)) > 0.0001
       OR ABS(pol.OrderedQuantity - COALESCE(siq.TotalStockInQuantity, 0)) > 0.0001

    UNION ALL
    SELECT 'RejectedQuantity nonzero', COUNT(*)
    FROM dbo.InspectionResult
    WHERE ABS(RejectedQuantity) > 0.0001

    UNION ALL
    SELECT 'ShortQuantity or DamagedQuantity nonzero', COUNT(*)
    FROM dbo.GoodsReceiptLine
    WHERE ABS(ShortQuantity) > 0.0001 OR ABS(DamagedQuantity) > 0.0001

    UNION ALL
    SELECT 'InventoryTransaction quantity != InventoryReceiptDetail accepted quantity', COUNT(*)
    FROM dbo.InventoryTransaction it
    JOIN dbo.InventoryReceiptDetail ird ON it.InspectionResultID = ird.InspectionResultID
    WHERE ABS(it.TransactionQuantity - ird.AcceptedQuantity) > 0.0001

    UNION ALL
    SELECT 'StockIn total > OrderedQuantity', COUNT(*)
    FROM (
        SELECT pol.PurchaseOrderLineID, pol.OrderedQuantity, SUM(it.TransactionQuantity) AS TotalStockInQuantity
        FROM dbo.PurchaseOrderLine pol
        JOIN dbo.InventoryTransaction it ON pol.PurchaseOrderLineID = it.PurchaseOrderLineID
        GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
    ) x
    WHERE TotalStockInQuantity > OrderedQuantity + 0.0001

    UNION ALL
    SELECT 'Inventory OnHandQuantity mismatch', COUNT(*)
    FROM dbo.Inventory inv
    JOIN (
        SELECT ComponentID, PlantID, WarehouseID, SUM(TransactionQuantity) AS ExpectedOnHandQuantity
        FROM dbo.InventoryTransaction
        GROUP BY ComponentID, PlantID, WarehouseID
    ) tb
        ON inv.ComponentID = tb.ComponentID
       AND inv.PlantID = tb.PlantID
       AND inv.WarehouseID = tb.WarehouseID
    WHERE ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity) > 0.0001

    UNION ALL
    SELECT 'Countable component quantity precision mismatch', COUNT(*)
    FROM (
        SELECT pol.PurchaseOrderLineID AS RowID
        FROM dbo.PurchaseOrderLine pol
        JOIN dbo.ComponentMaster cm ON pol.ComponentID = cm.ComponentID
        WHERE UPPER(REPLACE(CAST(cm.UOM AS varchar(80)), ' ', '')) IN (
            'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
            'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
        )
          AND ABS(pol.OrderedQuantity - FLOOR(pol.OrderedQuantity)) > 0.0001
        UNION ALL
        SELECT ir.InspectionResultID
        FROM dbo.InspectionResult ir
        JOIN dbo.IncomingInspection ii ON ir.InspectionID = ii.InspectionID
        JOIN dbo.GoodsReceiptLine grl ON ii.GoodsReceiptLineID = grl.GoodsReceiptLineID
        JOIN dbo.ComponentMaster cm ON grl.ComponentID = cm.ComponentID
        WHERE UPPER(REPLACE(CAST(cm.UOM AS varchar(80)), ' ', '')) IN (
            'EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE',
            'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK', 'BOX'
        )
          AND ABS(ir.AcceptedQuantity - FLOOR(ir.AcceptedQuantity)) > 0.0001
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
          AND ABS(inv.OnHandQuantity - FLOOR(inv.OnHandQuantity)) > 0.0001
    ) precision_issues
) scorecard
ORDER BY IssueName;
