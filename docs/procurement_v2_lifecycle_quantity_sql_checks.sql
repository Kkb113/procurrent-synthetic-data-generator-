/*
Procurement v2 lifecycle quantity-control SQL validation checks.

Purpose:
Validate that downstream procurement lifecycle quantities never exceed upstream
approved quantities, especially that inbound StockIn postings do not exceed the
PurchaseOrderLine.OrderedQuantity.

Expected output:
- Checks 1 through 21 should return no rows.
- Check 22 final scorecard should return IssueCount = 0 for every CheckName.

Lifecycle:
PurchaseReqLine.RequestedQuantity
-> RFQLine.RFQQuantity
-> SupplierQuotationLn.QuotedQuantity
-> PurchaseOrderLine.OrderedQuantity
-> POSchedule.ScheduledQuantity
-> ShipmentLine.ShippedQuantity
-> GoodsReceiptLine.ReceivedQuantity
-> InspectionResult.AcceptedQuantity
-> InventoryTransaction.TransactionQuantity
-> Inventory.OnHandQuantity
*/

-- 1. RFQQuantity <= RequestedQuantity. Expected: no rows.
SELECT
    rfl.RFQLineID,
    rfl.RequisitionLineID,
    prl.RequestedQuantity,
    rfl.RFQQuantity,
    rfl.RFQQuantity - prl.RequestedQuantity AS ExcessQuantity
FROM dbo.RFQLine rfl
JOIN dbo.PurchaseReqLine prl
    ON rfl.RequisitionLineID = prl.RequisitionLineID
WHERE rfl.RFQQuantity > prl.RequestedQuantity + 0.0001;

-- 2. QuotedQuantity <= RFQQuantity. Expected: no rows.
SELECT
    sqln.QuotationLineID,
    sqln.RFQLineID,
    rfl.RFQQuantity,
    sqln.QuotedQuantity,
    sqln.QuotedQuantity - rfl.RFQQuantity AS ExcessQuantity
FROM dbo.SupplierQuotationLn sqln
JOIN dbo.RFQLine rfl
    ON sqln.RFQLineID = rfl.RFQLineID
WHERE sqln.QuotedQuantity > rfl.RFQQuantity + 0.0001;

-- 3. OrderedQuantity <= awarded QuotedQuantity. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.QuotationLineID,
    sqln.QuotedQuantity,
    pol.OrderedQuantity,
    pol.OrderedQuantity - sqln.QuotedQuantity AS ExcessQuantity
FROM dbo.PurchaseOrderLine pol
JOIN dbo.SupplierQuotationLn sqln
    ON pol.QuotationLineID = sqln.QuotationLineID
WHERE pol.OrderedQuantity > sqln.QuotedQuantity + 0.0001;

-- 4. Cumulative OrderedQuantity by QuotationLineID <= awarded QuotedQuantity. Expected: no rows.
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

-- 5. ScheduledQuantity cumulative <= OrderedQuantity. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    SUM(ps.ScheduledQuantity) AS TotalScheduledQuantity,
    SUM(ps.ScheduledQuantity) - pol.OrderedQuantity AS ExcessQuantity
FROM dbo.PurchaseOrderLine pol
JOIN dbo.POSchedule ps
    ON pol.PurchaseOrderLineID = ps.PurchaseOrderLineID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity
HAVING SUM(ps.ScheduledQuantity) > pol.OrderedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;

-- 6. ShippedQuantity cumulative <= ScheduledQuantity by POScheduleID. Expected: no rows.
SELECT
    ps.POScheduleID,
    ps.ScheduledQuantity,
    SUM(sl.ShippedQuantity) AS TotalShippedQuantity,
    SUM(sl.ShippedQuantity) - ps.ScheduledQuantity AS ExcessQuantity
FROM dbo.POSchedule ps
JOIN dbo.ShipmentLine sl
    ON ps.POScheduleID = sl.POScheduleID
GROUP BY
    ps.POScheduleID,
    ps.ScheduledQuantity
HAVING SUM(sl.ShippedQuantity) > ps.ScheduledQuantity + 0.0001
ORDER BY ExcessQuantity DESC;

-- 7. ShippedQuantity cumulative <= OrderedQuantity by PurchaseOrderLineID. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    SUM(sl.ShippedQuantity) AS TotalShippedQuantity,
    SUM(sl.ShippedQuantity) - pol.OrderedQuantity AS ExcessQuantity
FROM dbo.PurchaseOrderLine pol
JOIN dbo.ShipmentLine sl
    ON pol.PurchaseOrderLineID = sl.PurchaseOrderLineID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity
HAVING SUM(sl.ShippedQuantity) > pol.OrderedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;

-- 8. ReceivedQuantity cumulative <= ShippedQuantity by ShipmentLineID. Expected: no rows.
SELECT
    sl.ShipmentLineID,
    sl.ShippedQuantity,
    SUM(grl.ReceivedQuantity) AS TotalReceivedQuantity,
    SUM(grl.ReceivedQuantity) - sl.ShippedQuantity AS ExcessQuantity
FROM dbo.ShipmentLine sl
JOIN dbo.GoodsReceiptLine grl
    ON sl.ShipmentLineID = grl.ShipmentLineID
GROUP BY
    sl.ShipmentLineID,
    sl.ShippedQuantity
HAVING SUM(grl.ReceivedQuantity) > sl.ShippedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;

-- 9. ReceivedQuantity cumulative <= OrderedQuantity by PurchaseOrderLineID. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    SUM(grl.ReceivedQuantity) AS TotalReceivedQuantity,
    SUM(grl.ReceivedQuantity) - pol.OrderedQuantity AS ExcessQuantity
FROM dbo.PurchaseOrderLine pol
JOIN dbo.GoodsReceiptLine grl
    ON pol.PurchaseOrderLineID = grl.PurchaseOrderLineID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity
HAVING SUM(grl.ReceivedQuantity) > pol.OrderedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;

-- 10. InspectedQuantity <= ReceivedQuantity. Expected: no rows.
SELECT
    ir.InspectionResultID,
    ii.GoodsReceiptLineID,
    grl.ReceivedQuantity,
    ir.InspectedQuantity,
    ir.InspectedQuantity - grl.ReceivedQuantity AS ExcessQuantity
FROM dbo.InspectionResult ir
JOIN dbo.IncomingInspection ii
    ON ir.InspectionID = ii.InspectionID
JOIN dbo.GoodsReceiptLine grl
    ON ii.GoodsReceiptLineID = grl.GoodsReceiptLineID
WHERE ir.InspectedQuantity > grl.ReceivedQuantity + 0.0001;

-- 11. AcceptedQuantity + RejectedQuantity = InspectedQuantity. Expected: no rows.
SELECT
    InspectionResultID,
    InspectedQuantity,
    AcceptedQuantity,
    RejectedQuantity,
    AcceptedQuantity + RejectedQuantity AS AcceptedPlusRejected,
    (AcceptedQuantity + RejectedQuantity) - InspectedQuantity AS Difference
FROM dbo.InspectionResult
WHERE ABS((AcceptedQuantity + RejectedQuantity) - InspectedQuantity) > 0.0001;

-- 12. AcceptedQuantity cumulative <= OrderedQuantity by PurchaseOrderLineID. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    SUM(ir.AcceptedQuantity) AS TotalAcceptedQuantity,
    SUM(ir.AcceptedQuantity) - pol.OrderedQuantity AS ExcessQuantity
FROM dbo.PurchaseOrderLine pol
JOIN dbo.GoodsReceiptLine grl
    ON pol.PurchaseOrderLineID = grl.PurchaseOrderLineID
JOIN dbo.IncomingInspection ii
    ON grl.GoodsReceiptLineID = ii.GoodsReceiptLineID
JOIN dbo.InspectionResult ir
    ON ii.InspectionID = ir.InspectionID
GROUP BY
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity
HAVING SUM(ir.AcceptedQuantity) > pol.OrderedQuantity + 0.0001
ORDER BY ExcessQuantity DESC;

-- 13. InventoryTransaction quantity = AcceptedQuantity. Expected: no rows.
SELECT
    it.InventoryTransactionID,
    it.InspectionResultID,
    ir.AcceptedQuantity,
    it.TransactionQuantity,
    it.TransactionQuantity - ir.AcceptedQuantity AS Difference
FROM dbo.InventoryTransaction it
JOIN dbo.InspectionResult ir
    ON it.InspectionResultID = ir.InspectionResultID
WHERE ABS(it.TransactionQuantity - ir.AcceptedQuantity) > 0.0001;

-- 14. InventoryTransaction cumulative <= OrderedQuantity by PurchaseOrderLineID.
-- This is the manager's main issue. Expected: no rows.
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

-- 15. Inventory OnHandQuantity = grouped InventoryTransaction quantity. Expected: no rows.
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

-- Additional status scorecard checks. Expected: all IssueCount = 0.
SELECT 'Closed PO line with partial StockIn' AS CheckName, COUNT(*) AS IssueCount
FROM (
    SELECT
        pol.PurchaseOrderLineID,
        pol.OrderedQuantity,
        COALESCE(SUM(it.TransactionQuantity), 0) AS TotalStockInQuantity
    FROM dbo.PurchaseOrderLine pol
    LEFT JOIN dbo.InventoryTransaction it
        ON pol.PurchaseOrderLineID = it.PurchaseOrderLineID
    WHERE pol.LineStatus = 'Closed'
    GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
) x
WHERE TotalStockInQuantity < OrderedQuantity - 0.0001

UNION ALL
SELECT 'Closed PO header with partial StockIn', COUNT(*)
FROM (
    SELECT
        poh.PurchaseOrderID,
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
    GROUP BY poh.PurchaseOrderID
) x
WHERE TotalStockInQuantity < TotalOrderedQuantity - 0.0001

UNION ALL
SELECT 'Receipt status hides short or damaged quantity', COUNT(*)
FROM (
    SELECT
        grh.GoodsReceiptID,
        grh.ReceiptStatus,
        SUM(grl.ShortQuantity) AS TotalShortQuantity,
        SUM(grl.DamagedQuantity) AS TotalDamagedQuantity
    FROM dbo.GoodsReceiptHeader grh
    JOIN dbo.GoodsReceiptLine grl
        ON grh.GoodsReceiptID = grl.GoodsReceiptID
    WHERE grh.ReceiptStatus IN ('Received', 'Closed')
    GROUP BY grh.GoodsReceiptID, grh.ReceiptStatus
) x
WHERE TotalShortQuantity > 0.0001
   OR TotalDamagedQuantity > 0.0001

UNION ALL
SELECT 'Inspection status or rejection reason mismatch', COUNT(*)
FROM dbo.InspectionResult
WHERE
    (RejectedQuantity = 0 AND ResultStatus <> 'Passed')
    OR (RejectedQuantity > 0 AND AcceptedQuantity > 0 AND ResultStatus <> 'PartiallyRejected')
    OR (RejectedQuantity > 0 AND AcceptedQuantity = 0 AND ResultStatus <> 'Failed')
    OR (RejectedQuantity = 0 AND COALESCE(NULLIF(RejectionReason, ''), 'Not Applicable') <> 'Not Applicable')
    OR (RejectedQuantity > 0 AND COALESCE(NULLIF(RejectionReason, ''), 'Not Applicable') = 'Not Applicable')

UNION ALL
SELECT 'Payment status mismatch', COUNT(*)
FROM dbo.PaymentTransaction pt
JOIN dbo.SupplierInvoice si
    ON pt.SupplierInvoiceID = si.SupplierInvoiceID
WHERE
    (pt.PaymentAmount <= 0.0001 AND pt.PaymentStatus NOT IN ('Pending', 'Failed'))
    OR (pt.PaymentAmount > 0.0001 AND pt.PaymentAmount < si.TotalInvoiceAmount - 0.01 AND pt.PaymentStatus <> 'PartiallyPaid')
    OR (pt.PaymentAmount >= si.TotalInvoiceAmount - 0.01 AND pt.PaymentStatus <> 'Paid')

UNION ALL
SELECT 'Paid invoice with partial payment', COUNT(*)
FROM (
    SELECT
        si.SupplierInvoiceID,
        si.TotalInvoiceAmount,
        si.InvoiceStatus,
        COALESCE(SUM(pt.PaymentAmount), 0) AS TotalPaidAmount
    FROM dbo.SupplierInvoice si
    LEFT JOIN dbo.PaymentTransaction pt
        ON si.SupplierInvoiceID = pt.SupplierInvoiceID
    WHERE si.InvoiceStatus = 'Paid'
    GROUP BY si.SupplierInvoiceID, si.TotalInvoiceAmount, si.InvoiceStatus
) x
WHERE TotalPaidAmount < TotalInvoiceAmount - 0.01;

-- 16. PO line Closed status requires full stock-in. Expected: no rows.
SELECT
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    pol.LineStatus,
    COALESCE(SUM(it.TransactionQuantity), 0) AS TotalStockInQuantity
FROM dbo.PurchaseOrderLine pol
LEFT JOIN dbo.InventoryTransaction it
    ON pol.PurchaseOrderLineID = it.PurchaseOrderLineID
WHERE pol.LineStatus = 'Closed'
GROUP BY
    pol.PurchaseOrderLineID,
    pol.OrderedQuantity,
    pol.LineStatus
HAVING COALESCE(SUM(it.TransactionQuantity), 0) < pol.OrderedQuantity - 0.0001;

-- 17. PO header Closed status requires full stock-in across all lines. Expected: no rows.
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

-- 18. Receipt status consistency for short/damaged rows. Expected: no rows.
SELECT
    grh.GoodsReceiptID,
    grh.ReceiptStatus,
    SUM(grl.ShortQuantity) AS TotalShortQuantity,
    SUM(grl.DamagedQuantity) AS TotalDamagedQuantity
FROM dbo.GoodsReceiptHeader grh
JOIN dbo.GoodsReceiptLine grl
    ON grh.GoodsReceiptID = grl.GoodsReceiptID
WHERE grh.ReceiptStatus IN ('Received', 'Closed')
GROUP BY
    grh.GoodsReceiptID,
    grh.ReceiptStatus
HAVING SUM(grl.ShortQuantity) > 0.0001
    OR SUM(grl.DamagedQuantity) > 0.0001;

-- 19. Inspection result status and rejection reason consistency. Expected: no rows.
SELECT
    InspectionResultID,
    AcceptedQuantity,
    RejectedQuantity,
    ResultStatus,
    RejectionReason
FROM dbo.InspectionResult
WHERE
    (RejectedQuantity = 0 AND ResultStatus <> 'Passed')
    OR (RejectedQuantity > 0 AND AcceptedQuantity > 0 AND ResultStatus <> 'PartiallyRejected')
    OR (RejectedQuantity > 0 AND AcceptedQuantity = 0 AND ResultStatus <> 'Failed')
    OR (RejectedQuantity = 0 AND COALESCE(NULLIF(RejectionReason, ''), 'Not Applicable') <> 'Not Applicable')
    OR (RejectedQuantity > 0 AND COALESCE(NULLIF(RejectionReason, ''), 'Not Applicable') = 'Not Applicable');

-- 20. Payment status consistency. Expected: no rows.
SELECT
    pt.PaymentTransactionID,
    pt.SupplierInvoiceID,
    si.TotalInvoiceAmount,
    pt.PaymentAmount,
    pt.PaymentStatus
FROM dbo.PaymentTransaction pt
JOIN dbo.SupplierInvoice si
    ON pt.SupplierInvoiceID = si.SupplierInvoiceID
WHERE
    (pt.PaymentAmount <= 0.0001 AND pt.PaymentStatus NOT IN ('Pending', 'Failed'))
    OR (pt.PaymentAmount > 0.0001 AND pt.PaymentAmount < si.TotalInvoiceAmount - 0.01 AND pt.PaymentStatus <> 'PartiallyPaid')
    OR (pt.PaymentAmount >= si.TotalInvoiceAmount - 0.01 AND pt.PaymentStatus <> 'Paid');

-- 21. Invoice paid status consistency. Expected: no rows.
SELECT
    si.SupplierInvoiceID,
    si.TotalInvoiceAmount,
    si.InvoiceStatus,
    COALESCE(SUM(pt.PaymentAmount), 0) AS TotalPaidAmount
FROM dbo.SupplierInvoice si
LEFT JOIN dbo.PaymentTransaction pt
    ON si.SupplierInvoiceID = pt.SupplierInvoiceID
WHERE si.InvoiceStatus = 'Paid'
GROUP BY
    si.SupplierInvoiceID,
    si.TotalInvoiceAmount,
    si.InvoiceStatus
HAVING COALESCE(SUM(pt.PaymentAmount), 0) < si.TotalInvoiceAmount - 0.01;

-- 22. Final lifecycle quantity and status scorecard. Expected: all IssueCount = 0.
SELECT 'RFQQuantity > RequestedQuantity' AS CheckName, COUNT(*) AS IssueCount
FROM dbo.RFQLine rfl
JOIN dbo.PurchaseReqLine prl
    ON rfl.RequisitionLineID = prl.RequisitionLineID
WHERE rfl.RFQQuantity > prl.RequestedQuantity + 0.0001

UNION ALL
SELECT 'QuotedQuantity > RFQQuantity', COUNT(*)
FROM dbo.SupplierQuotationLn sqln
JOIN dbo.RFQLine rfl
    ON sqln.RFQLineID = rfl.RFQLineID
WHERE sqln.QuotedQuantity > rfl.RFQQuantity + 0.0001

UNION ALL
SELECT 'OrderedQuantity > Awarded QuotedQuantity', COUNT(*)
FROM dbo.PurchaseOrderLine pol
JOIN dbo.SupplierQuotationLn sqln
    ON pol.QuotationLineID = sqln.QuotationLineID
WHERE pol.OrderedQuantity > sqln.QuotedQuantity + 0.0001

UNION ALL
SELECT 'OrderedQuantity total > Awarded QuotedQuantity', COUNT(*)
FROM (
    SELECT
        sqln.QuotationLineID,
        sqln.QuotedQuantity,
        SUM(pol.OrderedQuantity) AS TotalOrderedQuantity
    FROM dbo.SupplierQuotationLn sqln
    JOIN dbo.PurchaseOrderLine pol
        ON sqln.QuotationLineID = pol.QuotationLineID
    GROUP BY sqln.QuotationLineID, sqln.QuotedQuantity
) x
WHERE TotalOrderedQuantity > QuotedQuantity + 0.0001

UNION ALL
SELECT 'ScheduledQuantity total > OrderedQuantity', COUNT(*)
FROM (
    SELECT
        pol.PurchaseOrderLineID,
        pol.OrderedQuantity,
        SUM(ps.ScheduledQuantity) AS TotalScheduledQuantity
    FROM dbo.PurchaseOrderLine pol
    JOIN dbo.POSchedule ps
        ON pol.PurchaseOrderLineID = ps.PurchaseOrderLineID
    GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
) x
WHERE TotalScheduledQuantity > OrderedQuantity + 0.0001

UNION ALL
SELECT 'ShippedQuantity total > ScheduledQuantity', COUNT(*)
FROM (
    SELECT
        ps.POScheduleID,
        ps.ScheduledQuantity,
        SUM(sl.ShippedQuantity) AS TotalShippedQuantity
    FROM dbo.POSchedule ps
    JOIN dbo.ShipmentLine sl
        ON ps.POScheduleID = sl.POScheduleID
    GROUP BY ps.POScheduleID, ps.ScheduledQuantity
) x
WHERE TotalShippedQuantity > ScheduledQuantity + 0.0001

UNION ALL
SELECT 'ShippedQuantity total > OrderedQuantity', COUNT(*)
FROM (
    SELECT
        pol.PurchaseOrderLineID,
        pol.OrderedQuantity,
        SUM(sl.ShippedQuantity) AS TotalShippedQuantity
    FROM dbo.PurchaseOrderLine pol
    JOIN dbo.ShipmentLine sl
        ON pol.PurchaseOrderLineID = sl.PurchaseOrderLineID
    GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
) x
WHERE TotalShippedQuantity > OrderedQuantity + 0.0001

UNION ALL
SELECT 'ReceivedQuantity total > ShippedQuantity', COUNT(*)
FROM (
    SELECT
        sl.ShipmentLineID,
        sl.ShippedQuantity,
        SUM(grl.ReceivedQuantity) AS TotalReceivedQuantity
    FROM dbo.ShipmentLine sl
    JOIN dbo.GoodsReceiptLine grl
        ON sl.ShipmentLineID = grl.ShipmentLineID
    GROUP BY sl.ShipmentLineID, sl.ShippedQuantity
) x
WHERE TotalReceivedQuantity > ShippedQuantity + 0.0001

UNION ALL
SELECT 'ReceivedQuantity total > OrderedQuantity', COUNT(*)
FROM (
    SELECT
        pol.PurchaseOrderLineID,
        pol.OrderedQuantity,
        SUM(grl.ReceivedQuantity) AS TotalReceivedQuantity
    FROM dbo.PurchaseOrderLine pol
    JOIN dbo.GoodsReceiptLine grl
        ON pol.PurchaseOrderLineID = grl.PurchaseOrderLineID
    GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
) x
WHERE TotalReceivedQuantity > OrderedQuantity + 0.0001

UNION ALL
SELECT 'InspectedQuantity > ReceivedQuantity', COUNT(*)
FROM dbo.InspectionResult ir
JOIN dbo.IncomingInspection ii
    ON ir.InspectionID = ii.InspectionID
JOIN dbo.GoodsReceiptLine grl
    ON ii.GoodsReceiptLineID = grl.GoodsReceiptLineID
WHERE ir.InspectedQuantity > grl.ReceivedQuantity + 0.0001

UNION ALL
SELECT 'Accepted + Rejected != Inspected', COUNT(*)
FROM dbo.InspectionResult
WHERE ABS((AcceptedQuantity + RejectedQuantity) - InspectedQuantity) > 0.0001

UNION ALL
SELECT 'AcceptedQuantity total > OrderedQuantity', COUNT(*)
FROM (
    SELECT
        pol.PurchaseOrderLineID,
        pol.OrderedQuantity,
        SUM(ir.AcceptedQuantity) AS TotalAcceptedQuantity
    FROM dbo.PurchaseOrderLine pol
    JOIN dbo.GoodsReceiptLine grl
        ON pol.PurchaseOrderLineID = grl.PurchaseOrderLineID
    JOIN dbo.IncomingInspection ii
        ON grl.GoodsReceiptLineID = ii.GoodsReceiptLineID
    JOIN dbo.InspectionResult ir
        ON ii.InspectionID = ir.InspectionID
    GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
) x
WHERE TotalAcceptedQuantity > OrderedQuantity + 0.0001

UNION ALL
SELECT 'InventoryTransaction quantity != AcceptedQuantity', COUNT(*)
FROM dbo.InventoryTransaction it
JOIN dbo.InspectionResult ir
    ON it.InspectionResultID = ir.InspectionResultID
WHERE ABS(it.TransactionQuantity - ir.AcceptedQuantity) > 0.0001

UNION ALL
SELECT 'StockIn total > OrderedQuantity', COUNT(*)
FROM (
    SELECT
        pol.PurchaseOrderLineID,
        pol.OrderedQuantity,
        SUM(it.TransactionQuantity) AS TotalStockInQuantity
    FROM dbo.PurchaseOrderLine pol
    JOIN dbo.InventoryTransaction it
        ON pol.PurchaseOrderLineID = it.PurchaseOrderLineID
    GROUP BY pol.PurchaseOrderLineID, pol.OrderedQuantity
) x
WHERE TotalStockInQuantity > OrderedQuantity + 0.0001

UNION ALL
SELECT 'Inventory OnHandQuantity mismatch', COUNT(*)
FROM dbo.Inventory inv
JOIN (
    SELECT
        ComponentID,
        PlantID,
        WarehouseID,
        SUM(TransactionQuantity) AS ExpectedOnHandQuantity
    FROM dbo.InventoryTransaction
    GROUP BY ComponentID, PlantID, WarehouseID
) tb
    ON inv.ComponentID = tb.ComponentID
   AND inv.PlantID = tb.PlantID
   AND inv.WarehouseID = tb.WarehouseID
WHERE ABS(inv.OnHandQuantity - tb.ExpectedOnHandQuantity) > 0.0001;
