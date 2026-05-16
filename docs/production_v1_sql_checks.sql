/*
Production v1 SQL validation checks.

Purpose:
Validate the 21-table Production Execution flow after generated CSVs are loaded
to SQL Server under dbo, including Procurement-to-Production lineage.

Expected:
- Detail checks return no rows unless explicitly labelled as demo summaries.
- Final scorecard returns IssueName / IssueCount with all IssueCount = 0.
- Out-of-scope MES tables are not required by this pack.

Lifecycle:
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
*/

/* SECTION 1 - TABLE EXISTENCE CHECKS */

-- 1A. Production v1 21 expected tables. Expected: no rows.
WITH ExpectedProductionTables AS (
    SELECT TableName
    FROM (VALUES
        ('ProductMaster'),
        ('BOMHeader'),
        ('BOMLine'),
        ('WorkCenter'),
        ('RoutingHeader'),
        ('RoutingOperation'),
        ('ProductionShift'),
        ('ProductionOrderHdr'),
        ('ProductionOrderLine'),
        ('ProductionMaterialRequirement'),
        ('MaterialIssueHeader'),
        ('MaterialIssueLine'),
        ('ProductionBatch'),
        ('OperationExecution'),
        ('ProductionQualityInspection'),
        ('ProductionQualityResult'),
        ('ScrapReworkEvent'),
        ('FinishedGoodsReceipt'),
        ('FinishedGoodsInventory'),
        ('ProductionGenealogy'),
        ('ProductionCostSummary')
    ) v(TableName)
)
SELECT e.TableName AS MissingProductionTable
FROM ExpectedProductionTables e
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
WHERE t.TABLE_NAME IS NULL;

-- 1B. Required upstream Procurement tables. Expected: no rows.
WITH RequiredProcurementTables AS (
    SELECT TableName
    FROM (VALUES
        ('ComponentMaster'),
        ('Plant'),
        ('Warehouse'),
        ('Inventory'),
        ('InventoryTransaction'),
        ('InventoryReceiptDetail'),
        ('SupplierMaster')
    ) v(TableName)
)
SELECT e.TableName AS MissingUpstreamProcurementTable
FROM RequiredProcurementTables e
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
WHERE t.TABLE_NAME IS NULL;

-- 1C. Out-of-scope MES tables are not required by Production v1. Expected: no rows if absent.
WITH OutOfScopeMESTables AS (
    SELECT TableName
    FROM (VALUES
        ('OEE'),
        ('Downtime'),
        ('Maintenance'),
        ('LaborTracking'),
        ('Warranty'),
        ('Sales'),
        ('Customer'),
        ('CustomerShipment')
    ) v(TableName)
)
SELECT o.TableName AS OutOfScopeTablePresentButNotRequired
FROM OutOfScopeMESTables o
JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = o.TableName;

/* SECTION 2 - ROW COUNT SUMMARY */

-- Demo visibility: row-count summary for all Production tables.
SELECT 'ProductMaster' AS TableName, COUNT(*) AS RowCount FROM dbo.ProductMaster
UNION ALL SELECT 'BOMHeader', COUNT(*) FROM dbo.BOMHeader
UNION ALL SELECT 'BOMLine', COUNT(*) FROM dbo.BOMLine
UNION ALL SELECT 'WorkCenter', COUNT(*) FROM dbo.WorkCenter
UNION ALL SELECT 'RoutingHeader', COUNT(*) FROM dbo.RoutingHeader
UNION ALL SELECT 'RoutingOperation', COUNT(*) FROM dbo.RoutingOperation
UNION ALL SELECT 'ProductionShift', COUNT(*) FROM dbo.ProductionShift
UNION ALL SELECT 'ProductionOrderHdr', COUNT(*) FROM dbo.ProductionOrderHdr
UNION ALL SELECT 'ProductionOrderLine', COUNT(*) FROM dbo.ProductionOrderLine
UNION ALL SELECT 'ProductionMaterialRequirement', COUNT(*) FROM dbo.ProductionMaterialRequirement
UNION ALL SELECT 'MaterialIssueHeader', COUNT(*) FROM dbo.MaterialIssueHeader
UNION ALL SELECT 'MaterialIssueLine', COUNT(*) FROM dbo.MaterialIssueLine
UNION ALL SELECT 'ProductionBatch', COUNT(*) FROM dbo.ProductionBatch
UNION ALL SELECT 'OperationExecution', COUNT(*) FROM dbo.OperationExecution
UNION ALL SELECT 'ProductionQualityInspection', COUNT(*) FROM dbo.ProductionQualityInspection
UNION ALL SELECT 'ProductionQualityResult', COUNT(*) FROM dbo.ProductionQualityResult
UNION ALL SELECT 'ScrapReworkEvent', COUNT(*) FROM dbo.ScrapReworkEvent
UNION ALL SELECT 'FinishedGoodsReceipt', COUNT(*) FROM dbo.FinishedGoodsReceipt
UNION ALL SELECT 'FinishedGoodsInventory', COUNT(*) FROM dbo.FinishedGoodsInventory
UNION ALL SELECT 'ProductionGenealogy', COUNT(*) FROM dbo.ProductionGenealogy
UNION ALL SELECT 'ProductionCostSummary', COUNT(*) FROM dbo.ProductionCostSummary;

/* SECTION 2A - SIMPLIFIED OPERATING SCOPE */

-- Upstream location cardinality. Expected: both RowCount values are 1.
SELECT 'Plant' AS TableName, COUNT(*) AS RowCount
FROM dbo.Plant
UNION ALL
SELECT 'Warehouse', COUNT(*)
FROM dbo.Warehouse;

-- Production location summary. Expected: every DistinctPlantCount / DistinctWarehouseCount is 1 where applicable.
SELECT 'BOMHeader' AS TableName, COUNT(DISTINCT PlantID) AS DistinctPlantCount, NULL AS DistinctWarehouseCount
FROM dbo.BOMHeader
UNION ALL SELECT 'WorkCenter', COUNT(DISTINCT PlantID), NULL FROM dbo.WorkCenter
UNION ALL SELECT 'RoutingHeader', COUNT(DISTINCT PlantID), NULL FROM dbo.RoutingHeader
UNION ALL SELECT 'ProductionShift', COUNT(DISTINCT PlantID), NULL FROM dbo.ProductionShift
UNION ALL SELECT 'ProductionOrderHdr', COUNT(DISTINCT PlantID), NULL FROM dbo.ProductionOrderHdr
UNION ALL SELECT 'ProductionMaterialRequirement', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID) FROM dbo.ProductionMaterialRequirement
UNION ALL SELECT 'MaterialIssueHeader', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID) FROM dbo.MaterialIssueHeader
UNION ALL SELECT 'ProductionBatch', COUNT(DISTINCT PlantID), NULL FROM dbo.ProductionBatch
UNION ALL SELECT 'FinishedGoodsReceipt', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID) FROM dbo.FinishedGoodsReceipt
UNION ALL SELECT 'FinishedGoodsInventory', COUNT(DISTINCT PlantID), COUNT(DISTINCT WarehouseID) FROM dbo.FinishedGoodsInventory;

-- WorkCenter count is informational only. Multiple WorkCenters are allowed.
SELECT COUNT(*) AS WorkCenterCount
FROM dbo.WorkCenter;

-- ShiftCode counts. Expected: only ShiftCode = A appears.
SELECT ShiftCode, COUNT(*) AS RowCount
FROM dbo.ProductionShift
GROUP BY ShiftCode;

-- One Plant / one Warehouse / Shift A checks. Expected: no rows.
WITH SinglePlant AS (
    SELECT MIN(PlantID) AS PlantID
    FROM dbo.Plant
),
SingleWarehouse AS (
    SELECT MIN(WarehouseID) AS WarehouseID
    FROM dbo.Warehouse
)
SELECT 'Invalid Production PlantID reference' AS IssueName, 'BOMHeader' AS TableName, BOMID AS RecordID, PlantID AS BadValue
FROM dbo.BOMHeader
WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'WorkCenter', WorkCenterID, PlantID FROM dbo.WorkCenter WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'RoutingHeader', RoutingID, PlantID FROM dbo.RoutingHeader WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'ProductionShift', ShiftID, PlantID FROM dbo.ProductionShift WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'ProductionOrderHdr', ProductionOrderID, PlantID FROM dbo.ProductionOrderHdr WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'ProductionMaterialRequirement', MaterialRequirementID, PlantID FROM dbo.ProductionMaterialRequirement WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'MaterialIssueHeader', MaterialIssueID, PlantID FROM dbo.MaterialIssueHeader WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'ProductionBatch', ProductionBatchID, PlantID FROM dbo.ProductionBatch WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'FinishedGoodsReceipt', FinishedGoodsReceiptID, PlantID FROM dbo.FinishedGoodsReceipt WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production PlantID reference', 'FinishedGoodsInventory', FinishedGoodsInventoryID, PlantID FROM dbo.FinishedGoodsInventory WHERE PlantID <> (SELECT PlantID FROM SinglePlant)
UNION ALL SELECT 'Invalid Production WarehouseID reference', 'ProductionMaterialRequirement', MaterialRequirementID, WarehouseID FROM dbo.ProductionMaterialRequirement WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL SELECT 'Invalid Production WarehouseID reference', 'MaterialIssueHeader', MaterialIssueID, WarehouseID FROM dbo.MaterialIssueHeader WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL SELECT 'Invalid Production WarehouseID reference', 'FinishedGoodsReceipt', FinishedGoodsReceiptID, WarehouseID FROM dbo.FinishedGoodsReceipt WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse)
UNION ALL SELECT 'Invalid Production WarehouseID reference', 'FinishedGoodsInventory', FinishedGoodsInventoryID, WarehouseID FROM dbo.FinishedGoodsInventory WHERE WarehouseID <> (SELECT WarehouseID FROM SingleWarehouse);

-- Shift A only. Expected: no rows.
SELECT 'Invalid ProductionShift ShiftCode' AS IssueName, ShiftID, ShiftCode
FROM dbo.ProductionShift
WHERE ShiftCode <> 'A';

-- Explicit no Shift B/C check. Expected: IssueCount = 0.
SELECT 'Shift B/C should not exist' AS IssueName, COUNT(*) AS IssueCount
FROM dbo.ProductionShift
WHERE ShiftCode IN ('B', 'C');

-- OperationExecution shift lineage. Expected: no rows.
SELECT oe.OperationExecutionID,
       oe.ShiftID,
       ps.ShiftCode,
       oe.WorkCenterID AS OperationWorkCenterID,
       ps.WorkCenterID AS ShiftWorkCenterID
FROM dbo.OperationExecution oe
LEFT JOIN dbo.ProductionShift ps ON ps.ShiftID = oe.ShiftID
WHERE ps.ShiftID IS NULL
   OR ps.ShiftCode <> 'A'
   OR oe.WorkCenterID <> ps.WorkCenterID;

/* SECTION 3 - PRODUCTION MASTER DATA CHECKS */

-- ProductMaster uniqueness and allowed values. Expected: no rows.
SELECT 'Duplicate ProductID' AS IssueName, ProductID, COUNT(*) AS IssueCount
FROM dbo.ProductMaster
GROUP BY ProductID
HAVING COUNT(*) > 1
UNION ALL
SELECT 'Duplicate ProductCode', ProductCode, COUNT(*)
FROM dbo.ProductMaster
GROUP BY ProductCode
HAVING COUNT(*) > 1
UNION ALL
SELECT 'Invalid ProductType', ProductType, COUNT(*)
FROM dbo.ProductMaster
WHERE ProductType NOT IN ('FinishedGood', 'SemiFinished')
GROUP BY ProductType
UNION ALL
SELECT 'Invalid ProductStatus', ProductStatus, COUNT(*)
FROM dbo.ProductMaster
WHERE ProductStatus NOT IN ('Active', 'Inactive')
GROUP BY ProductStatus;

-- BOMHeader lineage, dates, and status. Expected: no rows.
SELECT bh.BOMID, bh.ProductID, bh.PlantID, bh.EffectiveFromDate, bh.EffectiveToDate, bh.BOMStatus
FROM dbo.BOMHeader bh
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = bh.ProductID
LEFT JOIN dbo.Plant p ON p.PlantID = bh.PlantID
WHERE pm.ProductID IS NULL
   OR p.PlantID IS NULL
   OR bh.EffectiveFromDate > bh.EffectiveToDate
   OR bh.EffectiveFromDate < '2025-01-01'
   OR bh.EffectiveToDate > '2025-12-31'
   OR bh.BOMStatus NOT IN ('Active', 'Inactive');

-- BOMLine component lineage, UOM, and controlled scrap. Expected: no rows.
SELECT bl.BOMLineID, bl.BOMID, bl.ComponentID, bl.UOM, cm.UOM AS ComponentUOM,
       bl.ComponentQuantity, bl.ScrapFactorPct, bl.IsCriticalComponent, bl.BOMLineStatus
FROM dbo.BOMLine bl
LEFT JOIN dbo.BOMHeader bh ON bh.BOMID = bl.BOMID
LEFT JOIN dbo.ComponentMaster cm ON cm.ComponentID = bl.ComponentID
WHERE bh.BOMID IS NULL
   OR cm.ComponentID IS NULL
   OR bl.UOM <> cm.UOM
   OR bl.ComponentQuantity <= 0
   OR bl.ScrapFactorPct < 0
   OR bl.ScrapFactorPct > 3
   OR bl.IsCriticalComponent NOT IN (0, 1)
   OR bl.BOMLineStatus NOT IN ('Active', 'Inactive');

-- WorkCenter, RoutingHeader, RoutingOperation, and ProductionShift checks. Expected: no rows.
SELECT 'WorkCenter' AS SourceTable, CAST(wc.WorkCenterID AS varchar(50)) AS SourceID
FROM dbo.WorkCenter wc
LEFT JOIN dbo.Plant p ON p.PlantID = wc.PlantID
WHERE p.PlantID IS NULL
   OR wc.CapacityPerShift <= 0
   OR wc.WorkCenterStatus NOT IN ('Active', 'Inactive', 'Maintenance')
UNION ALL
SELECT 'WorkCenter duplicate code', WorkCenterCode
FROM dbo.WorkCenter
GROUP BY WorkCenterCode
HAVING COUNT(*) > 1
UNION ALL
SELECT 'RoutingHeader', CAST(rh.RoutingID AS varchar(50))
FROM dbo.RoutingHeader rh
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = rh.ProductID
LEFT JOIN dbo.Plant p ON p.PlantID = rh.PlantID
WHERE pm.ProductID IS NULL
   OR p.PlantID IS NULL
   OR rh.RoutingStatus NOT IN ('Active', 'Inactive')
UNION ALL
SELECT 'RoutingOperation', CAST(ro.RoutingOperationID AS varchar(50))
FROM dbo.RoutingOperation ro
LEFT JOIN dbo.RoutingHeader rh ON rh.RoutingID = ro.RoutingID
LEFT JOIN dbo.WorkCenter wc ON wc.WorkCenterID = ro.WorkCenterID
WHERE rh.RoutingID IS NULL
   OR wc.WorkCenterID IS NULL
   OR ro.SetupTimeMinutes < 0
   OR ro.RunTimeMinutesPerUnit <= 0
   OR ro.StandardYieldPct < 0
   OR ro.StandardYieldPct > 100
   OR ro.OperationStatus NOT IN ('Active', 'Inactive')
UNION ALL
SELECT 'ProductionShift', CAST(ps.ShiftID AS varchar(50))
FROM dbo.ProductionShift ps
LEFT JOIN dbo.Plant p ON p.PlantID = ps.PlantID
LEFT JOIN dbo.WorkCenter wc ON wc.WorkCenterID = ps.WorkCenterID
WHERE p.PlantID IS NULL
   OR wc.WorkCenterID IS NULL
   OR ps.PlantID <> wc.PlantID
   OR ps.ShiftDate < '2025-01-01'
   OR ps.ShiftDate > '2025-12-31'
   OR ps.ShiftCode NOT IN ('A', 'B', 'C')
   OR ps.PlannedHours <= 0;

-- RoutingOperation sequence uniqueness per RoutingID. Expected: no rows.
SELECT RoutingID, OperationSequence, COUNT(*) AS DuplicateSequenceCount
FROM dbo.RoutingOperation
GROUP BY RoutingID, OperationSequence
HAVING COUNT(*) > 1;

/* SECTION 4 - PRODUCTION ORDER FLOW CHECKS */

-- ProductionOrderHdr and ProductionOrderLine lineage, dates, statuses, and quantities. Expected: no rows.
SELECT 'ProductionOrderHdr' AS SourceTable, CAST(poh.ProductionOrderID AS varchar(50)) AS SourceID
FROM dbo.ProductionOrderHdr poh
LEFT JOIN dbo.Plant p ON p.PlantID = poh.PlantID
WHERE p.PlantID IS NULL
   OR poh.OrderDate < '2025-01-01'
   OR poh.PlannedStartDate < '2025-01-01'
   OR poh.PlannedEndDate > '2025-12-31'
   OR poh.ActualStartDate < '2025-01-01'
   OR poh.ActualEndDate > '2025-12-31'
   OR poh.OrderDate > poh.PlannedStartDate
   OR poh.PlannedStartDate > poh.PlannedEndDate
   OR poh.ActualStartDate > poh.ActualEndDate
   OR poh.ProductionOrderStatus NOT IN ('Planned', 'Released', 'InProduction', 'Completed', 'Cancelled')
UNION ALL
SELECT 'ProductionOrderLine', CAST(pol.ProductionOrderLineID AS varchar(50))
FROM dbo.ProductionOrderLine pol
LEFT JOIN dbo.ProductionOrderHdr poh ON poh.ProductionOrderID = pol.ProductionOrderID
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = pol.ProductID
LEFT JOIN dbo.BOMHeader bh ON bh.BOMID = pol.BOMID
LEFT JOIN dbo.RoutingHeader rh ON rh.RoutingID = pol.RoutingID
WHERE poh.ProductionOrderID IS NULL
   OR pm.ProductID IS NULL
   OR bh.BOMID IS NULL
   OR rh.RoutingID IS NULL
   OR bh.ProductID <> pol.ProductID
   OR rh.ProductID <> pol.ProductID
   OR ABS(pol.ReleasedQuantity - pol.PlannedQuantity) > 0.0001
   OR ABS(pol.CompletedQuantity - (pol.GoodQuantity + pol.ScrapQuantity)) > 0.0001
   OR pol.GoodQuantity <= 0
   OR pol.ScrapQuantity < 0
   OR pol.UOM <> pm.UOM
   OR pol.LineStatus NOT IN ('Planned', 'Released', 'InProduction', 'Completed', 'Cancelled');

-- Demo summary: production order execution quantities.
SELECT poh.ProductionOrderID,
       pm.ProductName,
       pol.PlannedQuantity,
       pol.ReleasedQuantity,
       pol.CompletedQuantity,
       pol.GoodQuantity,
       pol.ScrapQuantity,
       poh.ProductionOrderStatus,
       pol.LineStatus
FROM dbo.ProductionOrderHdr poh
JOIN dbo.ProductionOrderLine pol ON pol.ProductionOrderID = poh.ProductionOrderID
JOIN dbo.ProductMaster pm ON pm.ProductID = pol.ProductID;

/* SECTION 5 - MATERIAL REQUIREMENT AND ISSUE CHECKS */

-- ProductionMaterialRequirement formula and lineage. Expected: no rows.
SELECT pmr.MaterialRequirementID,
       pmr.ProductionOrderLineID,
       pmr.BOMLineID,
       pmr.ComponentID,
       pmr.InventoryID,
       pmr.RequiredQuantity,
       pol.PlannedQuantity * bl.ComponentQuantity AS ExpectedRequiredQuantity,
       pmr.ScrapAdjustedQuantity,
       pmr.RequiredQuantity * (1 + bl.ScrapFactorPct / 100.0) AS ExpectedScrapAdjustedQuantity
FROM dbo.ProductionMaterialRequirement pmr
LEFT JOIN dbo.ProductionOrderLine pol ON pol.ProductionOrderLineID = pmr.ProductionOrderLineID
LEFT JOIN dbo.BOMLine bl ON bl.BOMLineID = pmr.BOMLineID
LEFT JOIN dbo.ComponentMaster cm ON cm.ComponentID = pmr.ComponentID
LEFT JOIN dbo.Plant p ON p.PlantID = pmr.PlantID
LEFT JOIN dbo.Warehouse w ON w.WarehouseID = pmr.WarehouseID
LEFT JOIN dbo.Inventory i ON i.InventoryID = pmr.InventoryID
WHERE pol.ProductionOrderLineID IS NULL
   OR bl.BOMLineID IS NULL
   OR pmr.ComponentID <> bl.ComponentID
   OR cm.ComponentID IS NULL
   OR p.PlantID IS NULL
   OR w.WarehouseID IS NULL
   OR i.InventoryID IS NULL
   OR i.ComponentID <> pmr.ComponentID
   OR i.PlantID <> pmr.PlantID
   OR i.WarehouseID <> pmr.WarehouseID
   OR ABS(pmr.RequiredQuantity - (pol.PlannedQuantity * bl.ComponentQuantity)) > 0.0001
   OR ABS(pmr.ScrapAdjustedQuantity - (pmr.RequiredQuantity * (1 + bl.ScrapFactorPct / 100.0))) > 0.0001
   OR pmr.IssuedQuantity > pmr.ScrapAdjustedQuantity + 0.0001
   OR pmr.RequirementStatus NOT IN ('Required', 'Issued', 'Consumed', 'Short');

-- MaterialIssueHeader and MaterialIssueLine lineage and formulas. Expected: no rows.
SELECT 'MaterialIssueHeader' AS SourceTable, CAST(mih.MaterialIssueID AS varchar(50)) AS SourceID
FROM dbo.MaterialIssueHeader mih
LEFT JOIN dbo.ProductionOrderHdr poh ON poh.ProductionOrderID = mih.ProductionOrderID
LEFT JOIN dbo.Plant p ON p.PlantID = mih.PlantID
LEFT JOIN dbo.Warehouse w ON w.WarehouseID = mih.WarehouseID
WHERE poh.ProductionOrderID IS NULL
   OR p.PlantID IS NULL
   OR w.WarehouseID IS NULL
   OR mih.IssueDate < '2025-01-01'
   OR mih.IssueDate > '2025-12-31'
   OR mih.IssueStatus NOT IN ('Planned', 'Issued', 'Cancelled')
UNION ALL
SELECT 'MaterialIssueLine', CAST(mil.MaterialIssueLineID AS varchar(50))
FROM dbo.MaterialIssueLine mil
LEFT JOIN dbo.MaterialIssueHeader mih ON mih.MaterialIssueID = mil.MaterialIssueID
LEFT JOIN dbo.ProductionMaterialRequirement pmr ON pmr.MaterialRequirementID = mil.MaterialRequirementID
LEFT JOIN dbo.ComponentMaster cm ON cm.ComponentID = mil.ComponentID
LEFT JOIN dbo.Inventory i ON i.InventoryID = mil.InventoryID
LEFT JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = mil.SourceInventoryTransactionID
LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = mil.InventoryReceiptDetailID
WHERE mih.MaterialIssueID IS NULL
   OR pmr.MaterialRequirementID IS NULL
   OR mil.ComponentID <> pmr.ComponentID
   OR mil.InventoryID <> pmr.InventoryID
   OR i.InventoryID IS NULL
   OR it.InventoryTransactionID IS NULL
   OR ird.InventoryReceiptDetailID IS NULL
   OR it.ComponentID <> mil.ComponentID
   OR it.InventoryReceiptDetailID <> mil.InventoryReceiptDetailID
   OR ABS(mil.IssuedQuantity - pmr.IssuedQuantity) > 0.0001
   OR mil.IssuedQuantity <= 0
   OR mil.UOM <> cm.UOM
   OR ABS(mil.UnitCost - it.UnitPrice) > 0.0001
   OR ABS(mil.IssueValue - (mil.IssuedQuantity * mil.UnitCost)) > 0.01
   OR mil.IssueStatus NOT IN ('Issued', 'Cancelled');

-- Inventory consumption cap by InventoryID. Expected: no rows.
SELECT mil.InventoryID,
       i.AvailableQuantity,
       SUM(mil.IssuedQuantity) AS TotalIssuedQuantity
FROM dbo.MaterialIssueLine mil
JOIN dbo.Inventory i ON i.InventoryID = mil.InventoryID
GROUP BY mil.InventoryID, i.AvailableQuantity
HAVING SUM(mil.IssuedQuantity) > i.AvailableQuantity + 0.0001;

-- Source-level consumption cap by SourceInventoryTransactionID. Expected: no rows when strict source tracking is used.
SELECT mil.SourceInventoryTransactionID,
       it.TransactionQuantity,
       SUM(mil.IssuedQuantity) AS TotalIssuedQuantity
FROM dbo.MaterialIssueLine mil
JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = mil.SourceInventoryTransactionID
GROUP BY mil.SourceInventoryTransactionID, it.TransactionQuantity
HAVING SUM(mil.IssuedQuantity) > it.TransactionQuantity + 0.0001;

-- Demo summary: component issue against Procurement inventory.
SELECT i.ComponentID,
       cm.ComponentName,
       cm.UOM,
       i.AvailableQuantity,
       SUM(mil.IssuedQuantity) AS TotalIssuedQuantity,
       i.AvailableQuantity - SUM(mil.IssuedQuantity) AS RemainingAvailableQuantity
FROM dbo.Inventory i
JOIN dbo.ComponentMaster cm ON cm.ComponentID = i.ComponentID
LEFT JOIN dbo.MaterialIssueLine mil ON mil.InventoryID = i.InventoryID
GROUP BY i.ComponentID, cm.ComponentName, cm.UOM, i.AvailableQuantity;

/* SECTION 6 - PRODUCTION BATCH AND OPERATION CHECKS */

-- ProductionBatch checks. Expected: no rows.
SELECT pb.ProductionBatchID, pb.ProductionOrderLineID, pb.ProductID, pb.PlantID
FROM dbo.ProductionBatch pb
LEFT JOIN dbo.ProductionOrderLine pol ON pol.ProductionOrderLineID = pb.ProductionOrderLineID
LEFT JOIN dbo.ProductionOrderHdr poh ON poh.ProductionOrderID = pol.ProductionOrderID
WHERE pol.ProductionOrderLineID IS NULL
   OR pb.ProductID <> pol.ProductID
   OR pb.PlantID <> poh.PlantID
   OR ABS(pb.PlannedBatchQuantity - pol.PlannedQuantity) > 0.0001
   OR pb.ActualStartDate < '2025-01-01'
   OR pb.ActualEndDate > '2025-12-31'
   OR pb.ActualStartDate > pb.ActualEndDate
   OR pb.BatchStatus NOT IN ('Planned', 'InProgress', 'Completed', 'Cancelled');

-- OperationExecution flow and formula checks. Expected: no rows.
WITH OperationFlow AS (
    SELECT oe.*,
           pb.PlannedBatchQuantity,
           ro.WorkCenterID AS ExpectedWorkCenterID,
           ro.OperationSequence AS ExpectedOperationSequence,
           ps.WorkCenterID AS ShiftWorkCenterID,
           LAG(oe.OutputQuantity) OVER (
               PARTITION BY oe.ProductionBatchID
               ORDER BY oe.OperationSequence
           ) AS PreviousOutputQuantity,
           ROW_NUMBER() OVER (
               PARTITION BY oe.ProductionBatchID
               ORDER BY oe.OperationSequence
           ) AS OperationRank
    FROM dbo.OperationExecution oe
    LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = oe.ProductionBatchID
    LEFT JOIN dbo.RoutingOperation ro ON ro.RoutingOperationID = oe.RoutingOperationID
    LEFT JOIN dbo.ProductionShift ps ON ps.ShiftID = oe.ShiftID
)
SELECT ProductionBatchID,
       OperationSequence,
       InputQuantity,
       OutputQuantity,
       ScrapQuantity,
       ReworkQuantity,
       PreviousOutputQuantity
FROM OperationFlow
WHERE ExpectedWorkCenterID IS NULL
   OR WorkCenterID <> ExpectedWorkCenterID
   OR ShiftWorkCenterID <> WorkCenterID
   OR OperationSequence <> ExpectedOperationSequence
   OR (OperationRank = 1 AND ABS(InputQuantity - PlannedBatchQuantity) > 0.0001)
   OR (OperationRank > 1 AND ABS(InputQuantity - PreviousOutputQuantity) > 0.0001)
   OR ABS(OutputQuantity - (InputQuantity - ScrapQuantity)) > 0.0001
   OR ScrapQuantity < 0
   OR ReworkQuantity < 0
   OR OperationStatus NOT IN ('Planned', 'InProgress', 'Completed', 'Skipped')
   OR TRY_CONVERT(date, ActualStartDateTime) < '2025-01-01'
   OR TRY_CONVERT(date, ActualEndDateTime) > '2025-12-31';

-- Demo summary: operation flow.
SELECT oe.ProductionBatchID,
       oe.OperationSequence,
       wc.WorkCenterName,
       oe.InputQuantity,
       oe.OutputQuantity,
       oe.ScrapQuantity,
       oe.ReworkQuantity,
       oe.OperationStatus
FROM dbo.OperationExecution oe
JOIN dbo.WorkCenter wc ON wc.WorkCenterID = oe.WorkCenterID;

/* SECTION 7 - QUALITY AND SCRAP/REWORK CHECKS */

-- ProductionQualityInspection and ProductionQualityResult checks. Expected: no rows.
SELECT 'ProductionQualityInspection' AS SourceTable, CAST(pqi.ProductionInspectionID AS varchar(50)) AS SourceID
FROM dbo.ProductionQualityInspection pqi
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = pqi.ProductionBatchID
LEFT JOIN dbo.OperationExecution oe ON oe.OperationExecutionID = pqi.OperationExecutionID
WHERE pb.ProductionBatchID IS NULL
   OR oe.OperationExecutionID IS NULL
   OR pqi.ProductID <> pb.ProductID
   OR pqi.InspectionDate < '2025-01-01'
   OR pqi.InspectionDate > '2025-12-31'
   OR pqi.InspectionType NOT IN ('InProcess', 'Final')
   OR pqi.SampleQuantity > oe.OutputQuantity + 0.0001
   OR pqi.InspectionStatus NOT IN ('Passed', 'PartiallyPassed', 'Failed')
UNION ALL
SELECT 'ProductionQualityResult', CAST(pqr.ProductionQualityResultID AS varchar(50))
FROM dbo.ProductionQualityResult pqr
LEFT JOIN dbo.ProductionQualityInspection pqi ON pqi.ProductionInspectionID = pqr.ProductionInspectionID
WHERE pqi.ProductionInspectionID IS NULL
   OR ABS(pqr.TestedQuantity - pqi.SampleQuantity) > 0.0001
   OR ABS((pqr.PassedQuantity + pqr.FailedQuantity) - pqr.TestedQuantity) > 0.0001
   OR pqr.FailedQuantity < 0
   OR (pqr.FailedQuantity = 0 AND (pqr.ResultStatus <> 'Passed' OR pqr.DefectCode <> 'NoDefect' OR pqr.DefectSeverity <> 'None'))
   OR (pqr.FailedQuantity > 0 AND (NULLIF(LTRIM(RTRIM(pqr.DefectCode)), '') IS NULL OR pqr.DefectCode IN ('NoDefect', 'None') OR pqr.DefectSeverity = 'None' OR pqr.ResultStatus NOT IN ('PartiallyFailed', 'Failed')))
   OR pqr.ResultStatus NOT IN ('Passed', 'PartiallyFailed', 'Failed')
   OR pqr.DefectSeverity NOT IN ('None', 'Low', 'Medium', 'High', 'Critical')
   OR pqr.DefectCode NOT IN ('NoDefect', 'TorqueDeviation', 'ElectricalContinuityFailure', 'ThermalLeak', 'CalibrationFailure', 'CosmeticDamage', 'ConnectorFitmentIssue');

-- ScrapReworkEvent checks. Expected: no rows.
SELECT sre.ScrapReworkID,
       sre.EventType,
       sre.Quantity,
       oe.ScrapQuantity,
       oe.ReworkQuantity
FROM dbo.ScrapReworkEvent sre
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = sre.ProductionBatchID
LEFT JOIN dbo.OperationExecution oe ON oe.OperationExecutionID = sre.OperationExecutionID
WHERE pb.ProductionBatchID IS NULL
   OR oe.OperationExecutionID IS NULL
   OR sre.ProductID <> pb.ProductID
   OR sre.EventType NOT IN ('Scrap', 'Rework')
   OR sre.Quantity <= 0
   OR sre.EventDate < '2025-01-01'
   OR sre.EventDate > '2025-12-31'
   OR (sre.EventType = 'Scrap' AND ABS(sre.Quantity - oe.ScrapQuantity) > 0.0001)
   OR (sre.EventType = 'Rework' AND ABS(sre.Quantity - oe.ReworkQuantity) > 0.0001)
   OR sre.CostImpact < 0;

/* SECTION 8 - FINISHED GOODS RECEIPT AND INVENTORY CHECKS */

-- FinishedGoodsReceipt checks. Expected: no rows.
SELECT fgr.FinishedGoodsReceiptID,
       fgr.ProductionBatchID,
       fgr.ProductionOrderLineID,
       fgr.GoodQuantity,
       fgr.UnitCost,
       fgr.ReceiptValue
FROM dbo.FinishedGoodsReceipt fgr
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = fgr.ProductionBatchID
LEFT JOIN dbo.ProductionOrderLine pol ON pol.ProductionOrderLineID = fgr.ProductionOrderLineID
LEFT JOIN dbo.Warehouse w ON w.WarehouseID = fgr.WarehouseID
WHERE pb.ProductionBatchID IS NULL
   OR pol.ProductionOrderLineID IS NULL
   OR fgr.ProductID <> pb.ProductID
   OR fgr.ProductID <> pol.ProductID
   OR fgr.PlantID <> pb.PlantID
   OR w.WarehouseID IS NULL
   OR fgr.ReceiptDate < '2025-01-01'
   OR fgr.ReceiptDate > '2025-12-31'
   OR fgr.ReceiptDate < pb.ActualEndDate
   OR fgr.GoodQuantity <= 0
   OR fgr.ScrapQuantity < 0
   OR fgr.UnitCost <= 0
   OR ABS(fgr.ReceiptValue - (fgr.GoodQuantity * fgr.UnitCost)) > 0.01
   OR fgr.ReceiptStatus NOT IN ('Received', 'Cancelled');

-- FinishedGoodsInventory rollup checks. Expected: no rows.
WITH FGRollup AS (
    SELECT ProductID,
           PlantID,
           WarehouseID,
           SUM(GoodQuantity) AS ExpectedOnHandQuantity,
           SUM(ReceiptValue) AS ExpectedOnHandValue,
           MAX(ReceiptDate) AS ExpectedLastReceiptDate
    FROM dbo.FinishedGoodsReceipt
    GROUP BY ProductID, PlantID, WarehouseID
)
SELECT fgi.FinishedGoodsInventoryID,
       fgi.ProductID,
       fgi.PlantID,
       fgi.WarehouseID,
       fgi.OnHandQuantity,
       r.ExpectedOnHandQuantity,
       fgi.OnHandValue,
       r.ExpectedOnHandValue,
       fgi.AvailableQuantity,
       fgi.LastReceiptDate
FROM dbo.FinishedGoodsInventory fgi
LEFT JOIN dbo.ProductMaster pm ON pm.ProductID = fgi.ProductID
LEFT JOIN dbo.Plant p ON p.PlantID = fgi.PlantID
LEFT JOIN dbo.Warehouse w ON w.WarehouseID = fgi.WarehouseID
LEFT JOIN FGRollup r
    ON r.ProductID = fgi.ProductID
   AND r.PlantID = fgi.PlantID
   AND r.WarehouseID = fgi.WarehouseID
WHERE pm.ProductID IS NULL
   OR p.PlantID IS NULL
   OR w.WarehouseID IS NULL
   OR r.ProductID IS NULL
   OR ABS(fgi.OnHandQuantity - r.ExpectedOnHandQuantity) > 0.0001
   OR ABS(fgi.OnHandValue - r.ExpectedOnHandValue) > 0.01
   OR fgi.ReservedQuantity > fgi.OnHandQuantity + 0.0001
   OR ABS(fgi.AvailableQuantity - (fgi.OnHandQuantity - fgi.ReservedQuantity)) > 0.0001
   OR fgi.LastReceiptDate <> r.ExpectedLastReceiptDate
   OR fgi.InventoryStatus NOT IN ('Available', 'LowStock', 'Hold', 'OutOfStock');

-- Demo summary: finished goods inventory.
SELECT fgi.ProductID,
       pm.ProductName,
       fgi.PlantID,
       fgi.WarehouseID,
       fgi.OnHandQuantity,
       fgi.ReservedQuantity,
       fgi.AvailableQuantity,
       fgi.OnHandValue,
       fgi.LastReceiptDate,
       fgi.InventoryStatus
FROM dbo.FinishedGoodsInventory fgi
JOIN dbo.ProductMaster pm ON pm.ProductID = fgi.ProductID;

/* SECTION 9 - PRODUCTION GENEALOGY / TRACEABILITY CHECKS */

-- ProductionGenealogy traceability checks. Expected: no rows.
SELECT pg.ProductionGenealogyID,
       pg.FinishedGoodsReceiptID,
       pg.ProductionBatchID,
       pg.MaterialIssueLineID,
       pg.ComponentID,
       pg.InventoryReceiptDetailID,
       pg.SourceInventoryTransactionID,
       pg.SupplierID,
       pg.ConsumedQuantity
FROM dbo.ProductionGenealogy pg
LEFT JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = pg.FinishedGoodsReceiptID
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = pg.ProductionBatchID
LEFT JOIN dbo.MaterialIssueLine mil ON mil.MaterialIssueLineID = pg.MaterialIssueLineID
LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = pg.InventoryReceiptDetailID
LEFT JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = pg.SourceInventoryTransactionID
WHERE fgr.FinishedGoodsReceiptID IS NULL
   OR pb.ProductionBatchID IS NULL
   OR mil.MaterialIssueLineID IS NULL
   OR pg.ComponentID <> mil.ComponentID
   OR pg.InventoryReceiptDetailID <> mil.InventoryReceiptDetailID
   OR pg.SourceInventoryTransactionID <> mil.SourceInventoryTransactionID
   OR ird.InventoryReceiptDetailID IS NULL
   OR it.InventoryTransactionID IS NULL
   OR pg.SupplierID <> ird.SupplierID
   OR ABS(pg.ConsumedQuantity - mil.IssuedQuantity) > 0.0001
   OR pg.TraceabilityStatus NOT IN ('Traced', 'MissingSource')
   OR pg.TraceabilityStatus <> 'Traced';

-- Demo query: finished goods to supplier/component receipt lineage.
SELECT fgr.FinishedGoodsReceiptID,
       pm.ProductName,
       pg.ProductionBatchID,
       cm.ComponentName,
       sm.SupplierName,
       pg.ConsumedQuantity,
       pg.InventoryReceiptDetailID,
       pg.SourceInventoryTransactionID,
       pg.TraceabilityStatus
FROM dbo.ProductionGenealogy pg
JOIN dbo.FinishedGoodsReceipt fgr ON fgr.FinishedGoodsReceiptID = pg.FinishedGoodsReceiptID
JOIN dbo.ProductMaster pm ON pm.ProductID = fgr.ProductID
JOIN dbo.ComponentMaster cm ON cm.ComponentID = pg.ComponentID
JOIN dbo.SupplierMaster sm ON sm.SupplierID = pg.SupplierID;

/* SECTION 10 - PRODUCTION COST SUMMARY CHECKS */

-- ProductionCostSummary formulas and finished goods receipt cost alignment. Expected: no rows.
WITH MaterialCostRollup AS (
    SELECT pol.ProductionOrderLineID,
           pb.ProductionBatchID,
           SUM(mil.IssueValue) AS ExpectedMaterialCost
    FROM dbo.ProductionOrderLine pol
    JOIN dbo.ProductionBatch pb ON pb.ProductionOrderLineID = pol.ProductionOrderLineID
    JOIN dbo.ProductionMaterialRequirement pmr ON pmr.ProductionOrderLineID = pol.ProductionOrderLineID
    JOIN dbo.MaterialIssueLine mil ON mil.MaterialRequirementID = pmr.MaterialRequirementID
    GROUP BY pol.ProductionOrderLineID, pb.ProductionBatchID
),
ScrapCostRollup AS (
    SELECT ProductionBatchID,
           SUM(CostImpact) AS ExpectedScrapCost
    FROM dbo.ScrapReworkEvent
    GROUP BY ProductionBatchID
)
SELECT pcs.ProductionCostSummaryID,
       pcs.ProductionOrderLineID,
       pcs.ProductionBatchID,
       pcs.MaterialCost,
       mcr.ExpectedMaterialCost,
       pcs.ScrapCost,
       COALESCE(scr.ExpectedScrapCost, 0) AS ExpectedScrapCost,
       pcs.TotalProductionCost,
       pcs.UnitProductionCost,
       fgr.GoodQuantity
FROM dbo.ProductionCostSummary pcs
LEFT JOIN dbo.ProductionOrderLine pol ON pol.ProductionOrderLineID = pcs.ProductionOrderLineID
LEFT JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = pcs.ProductionBatchID
LEFT JOIN dbo.FinishedGoodsReceipt fgr ON fgr.ProductionBatchID = pcs.ProductionBatchID
LEFT JOIN MaterialCostRollup mcr
    ON mcr.ProductionOrderLineID = pcs.ProductionOrderLineID
   AND mcr.ProductionBatchID = pcs.ProductionBatchID
LEFT JOIN ScrapCostRollup scr ON scr.ProductionBatchID = pcs.ProductionBatchID
WHERE pol.ProductionOrderLineID IS NULL
   OR pb.ProductionBatchID IS NULL
   OR pcs.ProductID <> pb.ProductID
   OR ABS(pcs.MaterialCost - mcr.ExpectedMaterialCost) > 0.01
   OR pcs.LaborCost < 0
   OR pcs.OverheadCost < 0
   OR ABS(pcs.ScrapCost - COALESCE(scr.ExpectedScrapCost, 0)) > 0.01
   OR ABS(pcs.TotalProductionCost - (pcs.MaterialCost + pcs.LaborCost + pcs.OverheadCost + pcs.ScrapCost)) > 0.01
   OR ABS(pcs.UnitProductionCost - (pcs.TotalProductionCost / NULLIF(fgr.GoodQuantity, 0))) > 0.01
   OR ABS(fgr.UnitCost - pcs.UnitProductionCost) > 0.01
   OR ABS(fgr.ReceiptValue - (fgr.GoodQuantity * pcs.UnitProductionCost)) > 0.01;

-- Demo summary: production cost summary.
SELECT pm.ProductName,
       pcs.ProductionBatchID,
       pcs.MaterialCost,
       pcs.LaborCost,
       pcs.OverheadCost,
       pcs.ScrapCost,
       pcs.TotalProductionCost,
       pcs.UnitProductionCost,
       fgr.GoodQuantity
FROM dbo.ProductionCostSummary pcs
JOIN dbo.ProductMaster pm ON pm.ProductID = pcs.ProductID
JOIN dbo.FinishedGoodsReceipt fgr ON fgr.ProductionBatchID = pcs.ProductionBatchID;

/* SECTION 11 - 2025 DATE SCOPE CHECK */

-- Combined 2025-only date scope. Expected: no rows.
SELECT 'BOMHeader.EffectiveFromDate' AS DateField, BOMID AS RecordID, CAST(EffectiveFromDate AS varchar(50)) AS DateValue FROM dbo.BOMHeader WHERE EffectiveFromDate < '2025-01-01' OR EffectiveFromDate > '2025-12-31'
UNION ALL SELECT 'BOMHeader.EffectiveToDate', BOMID, CAST(EffectiveToDate AS varchar(50)) FROM dbo.BOMHeader WHERE EffectiveToDate < '2025-01-01' OR EffectiveToDate > '2025-12-31'
UNION ALL SELECT 'ProductionShift.ShiftDate', ShiftID, CAST(ShiftDate AS varchar(50)) FROM dbo.ProductionShift WHERE ShiftDate < '2025-01-01' OR ShiftDate > '2025-12-31'
UNION ALL SELECT 'ProductionOrderHdr.OrderDate', ProductionOrderID, CAST(OrderDate AS varchar(50)) FROM dbo.ProductionOrderHdr WHERE OrderDate < '2025-01-01' OR OrderDate > '2025-12-31'
UNION ALL SELECT 'ProductionOrderHdr.PlannedStartDate', ProductionOrderID, CAST(PlannedStartDate AS varchar(50)) FROM dbo.ProductionOrderHdr WHERE PlannedStartDate < '2025-01-01' OR PlannedStartDate > '2025-12-31'
UNION ALL SELECT 'ProductionOrderHdr.PlannedEndDate', ProductionOrderID, CAST(PlannedEndDate AS varchar(50)) FROM dbo.ProductionOrderHdr WHERE PlannedEndDate < '2025-01-01' OR PlannedEndDate > '2025-12-31'
UNION ALL SELECT 'ProductionOrderHdr.ActualStartDate', ProductionOrderID, CAST(ActualStartDate AS varchar(50)) FROM dbo.ProductionOrderHdr WHERE ActualStartDate < '2025-01-01' OR ActualStartDate > '2025-12-31'
UNION ALL SELECT 'ProductionOrderHdr.ActualEndDate', ProductionOrderID, CAST(ActualEndDate AS varchar(50)) FROM dbo.ProductionOrderHdr WHERE ActualEndDate < '2025-01-01' OR ActualEndDate > '2025-12-31'
UNION ALL SELECT 'MaterialIssueHeader.IssueDate', MaterialIssueID, CAST(IssueDate AS varchar(50)) FROM dbo.MaterialIssueHeader WHERE IssueDate < '2025-01-01' OR IssueDate > '2025-12-31'
UNION ALL SELECT 'ProductionBatch.ActualStartDate', ProductionBatchID, CAST(ActualStartDate AS varchar(50)) FROM dbo.ProductionBatch WHERE ActualStartDate < '2025-01-01' OR ActualStartDate > '2025-12-31'
UNION ALL SELECT 'ProductionBatch.ActualEndDate', ProductionBatchID, CAST(ActualEndDate AS varchar(50)) FROM dbo.ProductionBatch WHERE ActualEndDate < '2025-01-01' OR ActualEndDate > '2025-12-31'
UNION ALL SELECT 'OperationExecution.ActualStartDateTime', OperationExecutionID, ActualStartDateTime FROM dbo.OperationExecution WHERE TRY_CONVERT(date, ActualStartDateTime) < '2025-01-01' OR TRY_CONVERT(date, ActualStartDateTime) > '2025-12-31'
UNION ALL SELECT 'OperationExecution.ActualEndDateTime', OperationExecutionID, ActualEndDateTime FROM dbo.OperationExecution WHERE TRY_CONVERT(date, ActualEndDateTime) < '2025-01-01' OR TRY_CONVERT(date, ActualEndDateTime) > '2025-12-31'
UNION ALL SELECT 'ProductionQualityInspection.InspectionDate', ProductionInspectionID, CAST(InspectionDate AS varchar(50)) FROM dbo.ProductionQualityInspection WHERE InspectionDate < '2025-01-01' OR InspectionDate > '2025-12-31'
UNION ALL SELECT 'ScrapReworkEvent.EventDate', ScrapReworkID, CAST(EventDate AS varchar(50)) FROM dbo.ScrapReworkEvent WHERE EventDate < '2025-01-01' OR EventDate > '2025-12-31'
UNION ALL SELECT 'FinishedGoodsReceipt.ReceiptDate', FinishedGoodsReceiptID, CAST(ReceiptDate AS varchar(50)) FROM dbo.FinishedGoodsReceipt WHERE ReceiptDate < '2025-01-01' OR ReceiptDate > '2025-12-31'
UNION ALL SELECT 'FinishedGoodsInventory.LastReceiptDate', FinishedGoodsInventoryID, CAST(LastReceiptDate AS varchar(50)) FROM dbo.FinishedGoodsInventory WHERE LastReceiptDate < '2025-01-01' OR LastReceiptDate > '2025-12-31';

/* SECTION 12 - UOM QUANTITY PRECISION CHECKS */

-- Countable UOM quantity precision checks. Expected: no rows.
WITH CountableUOM AS (
    SELECT UOM
    FROM (VALUES
        ('EA'), ('Each'), ('Unit'), ('Piece'), ('PCS'), ('Pack'), ('Set'),
        ('Module'), ('Assembly'), ('Device'), ('Controller'), ('Sensor'),
        ('Motor'), ('BatteryPack')
    ) v(UOM)
),
CountableComponent AS (
    SELECT ComponentID
    FROM dbo.ComponentMaster cm
    WHERE EXISTS (
        SELECT 1
        FROM CountableUOM cu
        WHERE UPPER(REPLACE(cm.UOM, ' ', '')) = UPPER(REPLACE(cu.UOM, ' ', ''))
    )
),
CountableProduct AS (
    SELECT ProductID
    FROM dbo.ProductMaster pm
    WHERE EXISTS (
        SELECT 1
        FROM CountableUOM cu
        WHERE UPPER(REPLACE(pm.UOM, ' ', '')) = UPPER(REPLACE(cu.UOM, ' ', ''))
    )
)
SELECT 'BOMLine.ComponentQuantity decimal for countable UOM' AS IssueName, BOMLineID AS RecordID, ComponentQuantity AS QuantityValue
FROM dbo.BOMLine
WHERE ComponentID IN (SELECT ComponentID FROM CountableComponent)
  AND ABS(ComponentQuantity - FLOOR(ComponentQuantity)) > 0.0001
UNION ALL SELECT 'ProductionOrderLine.PlannedQuantity decimal for countable UOM', ProductionOrderLineID, PlannedQuantity FROM dbo.ProductionOrderLine WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(PlannedQuantity - FLOOR(PlannedQuantity)) > 0.0001
UNION ALL SELECT 'ProductionOrderLine.ReleasedQuantity decimal for countable UOM', ProductionOrderLineID, ReleasedQuantity FROM dbo.ProductionOrderLine WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(ReleasedQuantity - FLOOR(ReleasedQuantity)) > 0.0001
UNION ALL SELECT 'ProductionOrderLine.CompletedQuantity decimal for countable UOM', ProductionOrderLineID, CompletedQuantity FROM dbo.ProductionOrderLine WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(CompletedQuantity - FLOOR(CompletedQuantity)) > 0.0001
UNION ALL SELECT 'ProductionOrderLine.GoodQuantity decimal for countable UOM', ProductionOrderLineID, GoodQuantity FROM dbo.ProductionOrderLine WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(GoodQuantity - FLOOR(GoodQuantity)) > 0.0001
UNION ALL SELECT 'ProductionOrderLine.ScrapQuantity decimal for countable UOM', ProductionOrderLineID, ScrapQuantity FROM dbo.ProductionOrderLine WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(ScrapQuantity - FLOOR(ScrapQuantity)) > 0.0001
UNION ALL SELECT 'ProductionMaterialRequirement.RequiredQuantity decimal for countable UOM', MaterialRequirementID, RequiredQuantity FROM dbo.ProductionMaterialRequirement WHERE ComponentID IN (SELECT ComponentID FROM CountableComponent) AND ABS(RequiredQuantity - FLOOR(RequiredQuantity)) > 0.0001
UNION ALL SELECT 'ProductionMaterialRequirement.ScrapAdjustedQuantity decimal for countable UOM', MaterialRequirementID, ScrapAdjustedQuantity FROM dbo.ProductionMaterialRequirement WHERE ComponentID IN (SELECT ComponentID FROM CountableComponent) AND ABS(ScrapAdjustedQuantity - FLOOR(ScrapAdjustedQuantity)) > 0.0001
UNION ALL SELECT 'ProductionMaterialRequirement.IssuedQuantity decimal for countable UOM', MaterialRequirementID, IssuedQuantity FROM dbo.ProductionMaterialRequirement WHERE ComponentID IN (SELECT ComponentID FROM CountableComponent) AND ABS(IssuedQuantity - FLOOR(IssuedQuantity)) > 0.0001
UNION ALL SELECT 'MaterialIssueLine.IssuedQuantity decimal for countable UOM', MaterialIssueLineID, IssuedQuantity FROM dbo.MaterialIssueLine WHERE ComponentID IN (SELECT ComponentID FROM CountableComponent) AND ABS(IssuedQuantity - FLOOR(IssuedQuantity)) > 0.0001
UNION ALL SELECT 'OperationExecution.InputQuantity decimal for countable UOM', OperationExecutionID, InputQuantity FROM dbo.OperationExecution oe JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = oe.ProductionBatchID WHERE pb.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(InputQuantity - FLOOR(InputQuantity)) > 0.0001
UNION ALL SELECT 'OperationExecution.OutputQuantity decimal for countable UOM', OperationExecutionID, OutputQuantity FROM dbo.OperationExecution oe JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = oe.ProductionBatchID WHERE pb.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(OutputQuantity - FLOOR(OutputQuantity)) > 0.0001
UNION ALL SELECT 'OperationExecution.ScrapQuantity decimal for countable UOM', OperationExecutionID, ScrapQuantity FROM dbo.OperationExecution oe JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = oe.ProductionBatchID WHERE pb.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(ScrapQuantity - FLOOR(ScrapQuantity)) > 0.0001
UNION ALL SELECT 'OperationExecution.ReworkQuantity decimal for countable UOM', OperationExecutionID, ReworkQuantity FROM dbo.OperationExecution oe JOIN dbo.ProductionBatch pb ON pb.ProductionBatchID = oe.ProductionBatchID WHERE pb.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(ReworkQuantity - FLOOR(ReworkQuantity)) > 0.0001
UNION ALL SELECT 'ProductionQualityInspection.SampleQuantity decimal for countable UOM', ProductionInspectionID, SampleQuantity FROM dbo.ProductionQualityInspection WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(SampleQuantity - FLOOR(SampleQuantity)) > 0.0001
UNION ALL SELECT 'ProductionQualityResult.TestedQuantity decimal for countable UOM', pqr.ProductionQualityResultID, pqr.TestedQuantity FROM dbo.ProductionQualityResult pqr JOIN dbo.ProductionQualityInspection pqi ON pqi.ProductionInspectionID = pqr.ProductionInspectionID WHERE pqi.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(pqr.TestedQuantity - FLOOR(pqr.TestedQuantity)) > 0.0001
UNION ALL SELECT 'ProductionQualityResult.PassedQuantity decimal for countable UOM', pqr.ProductionQualityResultID, pqr.PassedQuantity FROM dbo.ProductionQualityResult pqr JOIN dbo.ProductionQualityInspection pqi ON pqi.ProductionInspectionID = pqr.ProductionInspectionID WHERE pqi.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(pqr.PassedQuantity - FLOOR(pqr.PassedQuantity)) > 0.0001
UNION ALL SELECT 'ProductionQualityResult.FailedQuantity decimal for countable UOM', pqr.ProductionQualityResultID, pqr.FailedQuantity FROM dbo.ProductionQualityResult pqr JOIN dbo.ProductionQualityInspection pqi ON pqi.ProductionInspectionID = pqr.ProductionInspectionID WHERE pqi.ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(pqr.FailedQuantity - FLOOR(pqr.FailedQuantity)) > 0.0001
UNION ALL SELECT 'FinishedGoodsReceipt.GoodQuantity decimal for countable UOM', FinishedGoodsReceiptID, GoodQuantity FROM dbo.FinishedGoodsReceipt WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(GoodQuantity - FLOOR(GoodQuantity)) > 0.0001
UNION ALL SELECT 'FinishedGoodsReceipt.ScrapQuantity decimal for countable UOM', FinishedGoodsReceiptID, ScrapQuantity FROM dbo.FinishedGoodsReceipt WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(ScrapQuantity - FLOOR(ScrapQuantity)) > 0.0001
UNION ALL SELECT 'FinishedGoodsInventory.OnHandQuantity decimal for countable UOM', FinishedGoodsInventoryID, OnHandQuantity FROM dbo.FinishedGoodsInventory WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(OnHandQuantity - FLOOR(OnHandQuantity)) > 0.0001
UNION ALL SELECT 'FinishedGoodsInventory.AvailableQuantity decimal for countable UOM', FinishedGoodsInventoryID, AvailableQuantity FROM dbo.FinishedGoodsInventory WHERE ProductID IN (SELECT ProductID FROM CountableProduct) AND ABS(AvailableQuantity - FLOOR(AvailableQuantity)) > 0.0001
UNION ALL SELECT 'ProductionGenealogy.ConsumedQuantity decimal for countable UOM', ProductionGenealogyID, ConsumedQuantity FROM dbo.ProductionGenealogy WHERE ComponentID IN (SELECT ComponentID FROM CountableComponent) AND ABS(ConsumedQuantity - FLOOR(ConsumedQuantity)) > 0.0001;

/* SECTION 13 - FINAL SCORECARD */

-- Final Production v1 scorecard. Expected: all IssueCount = 0.
SELECT 'Missing Production tables' AS IssueName,
       COUNT(*) AS IssueCount
FROM (VALUES
    ('ProductMaster'), ('BOMHeader'), ('BOMLine'), ('WorkCenter'),
    ('RoutingHeader'), ('RoutingOperation'), ('ProductionShift'),
    ('ProductionOrderHdr'), ('ProductionOrderLine'), ('ProductionMaterialRequirement'),
    ('MaterialIssueHeader'), ('MaterialIssueLine'), ('ProductionBatch'),
    ('OperationExecution'), ('ProductionQualityInspection'), ('ProductionQualityResult'),
    ('ScrapReworkEvent'), ('FinishedGoodsReceipt'), ('FinishedGoodsInventory'),
    ('ProductionGenealogy'), ('ProductionCostSummary')
) e(TableName)
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
WHERE t.TABLE_NAME IS NULL
UNION ALL
SELECT 'Missing upstream Procurement tables', COUNT(*)
FROM (VALUES
    ('ComponentMaster'), ('Plant'), ('Warehouse'), ('Inventory'),
    ('InventoryTransaction'), ('InventoryReceiptDetail'), ('SupplierMaster')
) e(TableName)
LEFT JOIN INFORMATION_SCHEMA.TABLES t
    ON t.TABLE_SCHEMA = 'dbo'
   AND t.TABLE_NAME = e.TableName
WHERE t.TABLE_NAME IS NULL
UNION ALL
SELECT 'Upstream Plant count should be 1', ABS(COUNT(*) - 1)
FROM dbo.Plant
UNION ALL
SELECT 'Upstream Warehouse count should be 1', ABS(COUNT(*) - 1)
FROM dbo.Warehouse
UNION ALL
SELECT 'Invalid Production PlantID references', SUM(IssueCount)
FROM (
    SELECT COUNT(*) AS IssueCount FROM dbo.BOMHeader WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.WorkCenter WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.RoutingHeader WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.ProductionShift WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.ProductionOrderHdr WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.ProductionMaterialRequirement WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.MaterialIssueHeader WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.ProductionBatch WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.FinishedGoodsReceipt WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
    UNION ALL SELECT COUNT(*) FROM dbo.FinishedGoodsInventory WHERE PlantID <> (SELECT MIN(PlantID) FROM dbo.Plant)
) plant_scope
UNION ALL
SELECT 'Invalid Production WarehouseID references', SUM(IssueCount)
FROM (
    SELECT COUNT(*) AS IssueCount FROM dbo.ProductionMaterialRequirement WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
    UNION ALL SELECT COUNT(*) FROM dbo.MaterialIssueHeader WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
    UNION ALL SELECT COUNT(*) FROM dbo.FinishedGoodsReceipt WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
    UNION ALL SELECT COUNT(*) FROM dbo.FinishedGoodsInventory WHERE WarehouseID <> (SELECT MIN(WarehouseID) FROM dbo.Warehouse)
) warehouse_scope
UNION ALL
SELECT 'Invalid ProductionShift ShiftCode', COUNT(*)
FROM dbo.ProductionShift
WHERE ShiftCode <> 'A'
UNION ALL
SELECT 'Shift B/C should not exist', COUNT(*)
FROM dbo.ProductionShift
WHERE ShiftCode IN ('B', 'C')
UNION ALL
SELECT 'OperationExecution references non-A shift', COUNT(*)
FROM dbo.OperationExecution oe
LEFT JOIN dbo.ProductionShift ps ON ps.ShiftID = oe.ShiftID
WHERE ps.ShiftID IS NULL
   OR ps.ShiftCode <> 'A'
UNION ALL
SELECT 'OperationExecution WorkCenter/Shift mismatch', COUNT(*)
FROM dbo.OperationExecution oe
LEFT JOIN dbo.ProductionShift ps ON ps.ShiftID = oe.ShiftID
WHERE ps.ShiftID IS NULL
   OR oe.WorkCenterID <> ps.WorkCenterID
UNION ALL
SELECT 'Bad ProductMaster uniqueness', COUNT(*)
FROM (
    SELECT ProductID AS KeyValue FROM dbo.ProductMaster GROUP BY ProductID HAVING COUNT(*) > 1
    UNION ALL
    SELECT ProductCode FROM dbo.ProductMaster GROUP BY ProductCode HAVING COUNT(*) > 1
) x
UNION ALL
SELECT 'Bad BOM lineage', COUNT(*)
FROM dbo.BOMLine bl
LEFT JOIN dbo.BOMHeader bh ON bh.BOMID = bl.BOMID
LEFT JOIN dbo.ComponentMaster cm ON cm.ComponentID = bl.ComponentID
WHERE bh.BOMID IS NULL OR cm.ComponentID IS NULL OR bl.UOM <> cm.UOM
UNION ALL
SELECT 'Bad routing lineage', COUNT(*)
FROM dbo.RoutingOperation ro
LEFT JOIN dbo.RoutingHeader rh ON rh.RoutingID = ro.RoutingID
LEFT JOIN dbo.WorkCenter wc ON wc.WorkCenterID = ro.WorkCenterID
WHERE rh.RoutingID IS NULL OR wc.WorkCenterID IS NULL
UNION ALL
SELECT 'Bad production order quantities', COUNT(*)
FROM dbo.ProductionOrderLine
WHERE ABS(ReleasedQuantity - PlannedQuantity) > 0.0001
   OR ABS(CompletedQuantity - (GoodQuantity + ScrapQuantity)) > 0.0001
   OR GoodQuantity <= 0
UNION ALL
SELECT 'Bad material requirement formula', COUNT(*)
FROM dbo.ProductionMaterialRequirement pmr
JOIN dbo.ProductionOrderLine pol ON pol.ProductionOrderLineID = pmr.ProductionOrderLineID
JOIN dbo.BOMLine bl ON bl.BOMLineID = pmr.BOMLineID
WHERE ABS(pmr.RequiredQuantity - (pol.PlannedQuantity * bl.ComponentQuantity)) > 0.0001
   OR ABS(pmr.ScrapAdjustedQuantity - (pmr.RequiredQuantity * (1 + bl.ScrapFactorPct / 100.0))) > 0.0001
UNION ALL
SELECT 'Material issue exceeds Inventory.AvailableQuantity', COUNT(*)
FROM (
    SELECT mil.InventoryID
    FROM dbo.MaterialIssueLine mil
    JOIN dbo.Inventory i ON i.InventoryID = mil.InventoryID
    GROUP BY mil.InventoryID, i.AvailableQuantity
    HAVING SUM(mil.IssuedQuantity) > i.AvailableQuantity + 0.0001
) x
UNION ALL
SELECT 'Bad InventoryTransaction lineage', COUNT(*)
FROM dbo.MaterialIssueLine mil
LEFT JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = mil.SourceInventoryTransactionID
WHERE it.InventoryTransactionID IS NULL
   OR it.ComponentID <> mil.ComponentID
UNION ALL
SELECT 'Bad InventoryReceiptDetail lineage', COUNT(*)
FROM dbo.MaterialIssueLine mil
LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = mil.InventoryReceiptDetailID
LEFT JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = mil.SourceInventoryTransactionID
WHERE ird.InventoryReceiptDetailID IS NULL
   OR it.InventoryReceiptDetailID <> mil.InventoryReceiptDetailID
UNION ALL
SELECT 'Bad issue value formula', COUNT(*)
FROM dbo.MaterialIssueLine mil
JOIN dbo.InventoryTransaction it ON it.InventoryTransactionID = mil.SourceInventoryTransactionID
WHERE ABS(mil.UnitCost - it.UnitPrice) > 0.0001
   OR ABS(mil.IssueValue - (mil.IssuedQuantity * mil.UnitCost)) > 0.01
UNION ALL
SELECT 'Bad operation output formula', COUNT(*)
FROM dbo.OperationExecution
WHERE ABS(OutputQuantity - (InputQuantity - ScrapQuantity)) > 0.0001
UNION ALL
SELECT 'Bad quality result math', COUNT(*)
FROM dbo.ProductionQualityResult pqr
JOIN dbo.ProductionQualityInspection pqi ON pqi.ProductionInspectionID = pqr.ProductionInspectionID
WHERE ABS(pqr.TestedQuantity - pqi.SampleQuantity) > 0.0001
   OR ABS((pqr.PassedQuantity + pqr.FailedQuantity) - pqr.TestedQuantity) > 0.0001
   OR (pqr.FailedQuantity = 0 AND (pqr.ResultStatus <> 'Passed' OR pqr.DefectCode <> 'NoDefect' OR pqr.DefectSeverity <> 'None'))
   OR (pqr.FailedQuantity > 0 AND (NULLIF(LTRIM(RTRIM(pqr.DefectCode)), '') IS NULL OR pqr.DefectCode IN ('NoDefect', 'None') OR pqr.DefectSeverity = 'None' OR pqr.ResultStatus NOT IN ('PartiallyFailed', 'Failed')))
   OR pqr.DefectCode NOT IN ('NoDefect', 'TorqueDeviation', 'ElectricalContinuityFailure', 'ThermalLeak', 'CalibrationFailure', 'CosmeticDamage', 'ConnectorFitmentIssue')
UNION ALL
SELECT 'Bad scrap/rework linkage', COUNT(*)
FROM dbo.ScrapReworkEvent sre
LEFT JOIN dbo.OperationExecution oe ON oe.OperationExecutionID = sre.OperationExecutionID
WHERE oe.OperationExecutionID IS NULL
   OR (sre.EventType = 'Scrap' AND ABS(sre.Quantity - oe.ScrapQuantity) > 0.0001)
   OR (sre.EventType = 'Rework' AND ABS(sre.Quantity - oe.ReworkQuantity) > 0.0001)
UNION ALL
SELECT 'Bad finished goods receipt formula', COUNT(*)
FROM dbo.FinishedGoodsReceipt
WHERE ABS(ReceiptValue - (GoodQuantity * UnitCost)) > 0.01
UNION ALL
SELECT 'Bad finished goods inventory rollup', COUNT(*)
FROM dbo.FinishedGoodsInventory fgi
LEFT JOIN (
    SELECT ProductID, PlantID, WarehouseID,
           SUM(GoodQuantity) AS ExpectedOnHandQuantity,
           SUM(ReceiptValue) AS ExpectedOnHandValue,
           MAX(ReceiptDate) AS ExpectedLastReceiptDate
    FROM dbo.FinishedGoodsReceipt
    GROUP BY ProductID, PlantID, WarehouseID
) r ON r.ProductID = fgi.ProductID
   AND r.PlantID = fgi.PlantID
   AND r.WarehouseID = fgi.WarehouseID
WHERE r.ProductID IS NULL
   OR ABS(fgi.OnHandQuantity - r.ExpectedOnHandQuantity) > 0.0001
   OR ABS(fgi.OnHandValue - r.ExpectedOnHandValue) > 0.01
   OR ABS(fgi.AvailableQuantity - (fgi.OnHandQuantity - fgi.ReservedQuantity)) > 0.0001
UNION ALL
SELECT 'Bad genealogy traceability', COUNT(*)
FROM dbo.ProductionGenealogy pg
LEFT JOIN dbo.MaterialIssueLine mil ON mil.MaterialIssueLineID = pg.MaterialIssueLineID
LEFT JOIN dbo.InventoryReceiptDetail ird ON ird.InventoryReceiptDetailID = pg.InventoryReceiptDetailID
WHERE mil.MaterialIssueLineID IS NULL
   OR pg.ComponentID <> mil.ComponentID
   OR pg.InventoryReceiptDetailID <> mil.InventoryReceiptDetailID
   OR pg.SourceInventoryTransactionID <> mil.SourceInventoryTransactionID
   OR pg.SupplierID <> ird.SupplierID
   OR ABS(pg.ConsumedQuantity - mil.IssuedQuantity) > 0.0001
UNION ALL
SELECT 'Bad production cost summary', COUNT(*)
FROM dbo.ProductionCostSummary pcs
JOIN dbo.FinishedGoodsReceipt fgr ON fgr.ProductionBatchID = pcs.ProductionBatchID
WHERE pcs.LaborCost < 0
   OR pcs.OverheadCost < 0
   OR ABS(pcs.TotalProductionCost - (pcs.MaterialCost + pcs.LaborCost + pcs.OverheadCost + pcs.ScrapCost)) > 0.01
   OR ABS(pcs.UnitProductionCost - (pcs.TotalProductionCost / NULLIF(fgr.GoodQuantity, 0))) > 0.01
   OR ABS(fgr.UnitCost - pcs.UnitProductionCost) > 0.01
UNION ALL
SELECT 'Dates outside 2025', COUNT(*)
FROM (
    SELECT BOMID AS RecordID FROM dbo.BOMHeader WHERE EffectiveFromDate < '2025-01-01' OR EffectiveToDate > '2025-12-31'
    UNION ALL SELECT ShiftID FROM dbo.ProductionShift WHERE ShiftDate < '2025-01-01' OR ShiftDate > '2025-12-31'
    UNION ALL SELECT ProductionOrderID FROM dbo.ProductionOrderHdr WHERE OrderDate < '2025-01-01' OR ActualEndDate > '2025-12-31'
    UNION ALL SELECT MaterialIssueID FROM dbo.MaterialIssueHeader WHERE IssueDate < '2025-01-01' OR IssueDate > '2025-12-31'
    UNION ALL SELECT ProductionBatchID FROM dbo.ProductionBatch WHERE ActualStartDate < '2025-01-01' OR ActualEndDate > '2025-12-31'
    UNION ALL SELECT ProductionInspectionID FROM dbo.ProductionQualityInspection WHERE InspectionDate < '2025-01-01' OR InspectionDate > '2025-12-31'
    UNION ALL SELECT ScrapReworkID FROM dbo.ScrapReworkEvent WHERE EventDate < '2025-01-01' OR EventDate > '2025-12-31'
    UNION ALL SELECT FinishedGoodsReceiptID FROM dbo.FinishedGoodsReceipt WHERE ReceiptDate < '2025-01-01' OR ReceiptDate > '2025-12-31'
    UNION ALL SELECT FinishedGoodsInventoryID FROM dbo.FinishedGoodsInventory WHERE LastReceiptDate < '2025-01-01' OR LastReceiptDate > '2025-12-31'
) x
UNION ALL
SELECT 'Countable UOM decimal quantity issues', COUNT(*)
FROM (
    SELECT bl.BOMLineID AS RecordID
    FROM dbo.BOMLine bl
    JOIN dbo.ComponentMaster cm ON cm.ComponentID = bl.ComponentID
    WHERE UPPER(REPLACE(cm.UOM, ' ', '')) IN ('EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE', 'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK')
      AND ABS(bl.ComponentQuantity - FLOOR(bl.ComponentQuantity)) > 0.0001
    UNION ALL
    SELECT pol.ProductionOrderLineID
    FROM dbo.ProductionOrderLine pol
    JOIN dbo.ProductMaster pm ON pm.ProductID = pol.ProductID
    WHERE UPPER(REPLACE(pm.UOM, ' ', '')) IN ('EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE', 'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK')
      AND (
          ABS(pol.PlannedQuantity - FLOOR(pol.PlannedQuantity)) > 0.0001
       OR ABS(pol.GoodQuantity - FLOOR(pol.GoodQuantity)) > 0.0001
      )
    UNION ALL
    SELECT mil.MaterialIssueLineID
    FROM dbo.MaterialIssueLine mil
    JOIN dbo.ComponentMaster cm ON cm.ComponentID = mil.ComponentID
    WHERE UPPER(REPLACE(cm.UOM, ' ', '')) IN ('EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE', 'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK')
      AND ABS(mil.IssuedQuantity - FLOOR(mil.IssuedQuantity)) > 0.0001
    UNION ALL
    SELECT fgi.FinishedGoodsInventoryID
    FROM dbo.FinishedGoodsInventory fgi
    JOIN dbo.ProductMaster pm ON pm.ProductID = fgi.ProductID
    WHERE UPPER(REPLACE(pm.UOM, ' ', '')) IN ('EA', 'EACH', 'UNIT', 'PIECE', 'PCS', 'PACK', 'SET', 'MODULE', 'ASSEMBLY', 'DEVICE', 'CONTROLLER', 'SENSOR', 'MOTOR', 'BATTERYPACK')
      AND ABS(fgi.OnHandQuantity - FLOOR(fgi.OnHandQuantity)) > 0.0001
) x;
