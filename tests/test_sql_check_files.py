from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_SQL = ROOT / "docs" / "procurement_v2_lifecycle_quantity_sql_checks.sql"
INVENTORY_SQL = ROOT / "docs" / "procurement_v2_inventory_sql_checks.sql"


def test_procurement_v2_lifecycle_quantity_sql_checks_file_exists() -> None:
    assert LIFECYCLE_SQL.exists()


def test_procurement_v2_inventory_sql_checks_file_exists() -> None:
    assert INVENTORY_SQL.exists()


def test_lifecycle_sql_includes_stock_in_total_ordered_check() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "StockIn total > OrderedQuantity" in text
    assert "SUM(it.TransactionQuantity)" in text
    assert "pol.OrderedQuantity" in text


def test_lifecycle_sql_includes_rfq_requested_check() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "RFQQuantity > RequestedQuantity" in text
    assert "rfl.RFQQuantity > prl.RequestedQuantity + 0.0001" in text


def test_lifecycle_sql_includes_schedule_ordered_check() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "ScheduledQuantity total > OrderedQuantity" in text
    assert "SUM(ps.ScheduledQuantity)" in text


def test_lifecycle_sql_includes_inventory_on_hand_check() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "Inventory OnHandQuantity mismatch" in text
    assert "ExpectedOnHandQuantity" in text


def test_lifecycle_sql_documents_zero_issue_expected_scorecard() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "Expected: all IssueCount = 0" in text
    assert "IssueName" in text
    assert "IssueCount" in text


def test_lifecycle_sql_includes_quotation_to_po_cumulative_check() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "OrderedQuantity total > Awarded QuotedQuantity" in text
    assert "GROUP BY sqln.QuotationLineID" in text


def test_lifecycle_sql_includes_status_consistency_checks() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "POStatus not Received" in text
    assert "LineStatus not Received" in text
    assert "Invalid lifecycle statuses" in text
    assert "PartiallyReceived" in text


def test_sql_files_include_inventory_receipt_detail_and_25_table_contract() -> None:
    lifecycle_text = LIFECYCLE_SQL.read_text(encoding="utf-8")
    inventory_text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "25 expected tables" in lifecycle_text
    assert "InventoryReceiptDetail" in lifecycle_text
    assert "InventoryReceiptDetail" in inventory_text
    assert "InventoryTransaction" in inventory_text
    assert "InventoryBalance" in lifecycle_text
    assert "InventoryBalance" in inventory_text


def test_sql_files_include_received_only_status_checks() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "POStatus <> 'Received'" in text
    assert "LineStatus <> 'Received'" in text
    assert "POStatus = Received only" in text
    assert "LineStatus = Received only" in text


def test_lifecycle_sql_includes_full_received_quantity_equality_checks() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "Full-received quantity equality" in text
    assert "TotalScheduledQuantity" in text
    assert "TotalShippedQuantity" in text
    assert "TotalReceivedQuantity" in text
    assert "TotalInspectedQuantity" in text
    assert "TotalReceiptDetailAcceptedQuantity" in text
    assert "TotalStockInQuantity" in text
    assert "RejectedQuantity nonzero" in text
    assert "ShortQuantity or DamagedQuantity nonzero" in text


def test_inventory_sql_includes_receipt_detail_date_and_year_checks() -> None:
    text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "POOrderDate" in text
    assert "ExpectedDeliveryDate" in text
    assert "ActualDeliveryDate" in text
    assert "StockPostedDate" in text
    assert "CrossYearDeliveryFlag <> 0" in text
    assert "OrderYear <> 2025" in text
    assert "DeliveryYear <> 2025" in text


def test_inventory_sql_includes_price_and_value_checks() -> None:
    text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "PriceDifference - ROUND(DeliveredUnitPrice - OrderedUnitPrice, 2)" in text
    assert "PriceDifferencePct" in text
    assert "OrderedValue - ROUND(OrderedQuantity * OrderedUnitPrice, 2)" in text
    assert "DeliveredValue - ROUND(ReceivedQuantity * DeliveredUnitPrice, 2)" in text
    assert "AcceptedStockValue - ROUND(AcceptedQuantity * DeliveredUnitPrice, 2)" in text


def test_inventory_sql_includes_inventory_transaction_receipt_detail_checks() -> None:
    text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "InventoryTransaction vs InventoryReceiptDetail" in text
    assert "it.TransactionDate <> ird.StockPostedDate" in text
    assert "it.TransactionQuantity - ird.AcceptedQuantity" in text
    assert "it.UnitPrice - ird.DeliveredUnitPrice" in text
    assert "it.TransactionType <> 'StockIn'" in text
    assert "CONCAT('IRD-'" in text


def test_inventory_sql_includes_inventory_rollup_checks() -> None:
    text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "Inventory OnHandQuantity and OnHandValue rollup" in text
    assert "SUM(TransactionQuantity) AS ExpectedOnHandQuantity" in text
    assert "SUM(InventoryValue) AS ExpectedOnHandValue" in text
    assert "AvailableQuantity - (OnHandQuantity - ReservedQuantity)" in text
    assert "AvailableValue" in text


def test_sql_files_include_countable_component_precision_checks() -> None:
    lifecycle_text = LIFECYCLE_SQL.read_text(encoding="utf-8")
    inventory_text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "Countable component lifecycle quantity precision checks" in lifecycle_text
    assert "Countable component quantity precision checks" in inventory_text
    assert "PurchaseOrderLine.OrderedQuantity decimal for countable UOM" in lifecycle_text
    assert "InspectionResult.AcceptedQuantity decimal for countable UOM" in lifecycle_text
    assert "InventoryTransaction.TransactionQuantity decimal for countable UOM" in inventory_text
    assert "Inventory.OnHandQuantity decimal for countable UOM" in inventory_text
    assert "FLOOR(" in lifecycle_text
    assert "BATTERYPACK" in inventory_text


def test_sql_files_include_final_scorecard_sections() -> None:
    lifecycle_text = LIFECYCLE_SQL.read_text(encoding="utf-8")
    inventory_text = INVENTORY_SQL.read_text(encoding="utf-8")

    assert "Final lifecycle quantity and status scorecard" in lifecycle_text
    assert "Final InventoryReceiptDetail / InventoryTransaction / Inventory scorecard" in inventory_text
    assert "IssueName, IssueCount" in lifecycle_text
    assert "IssueName, IssueCount" in inventory_text


def test_procurement_sql_files_include_one_location_scope_checks() -> None:
    lifecycle_text = LIFECYCLE_SQL.read_text(encoding="utf-8")
    inventory_text = INVENTORY_SQL.read_text(encoding="utf-8")

    for text in (lifecycle_text, inventory_text):
        assert "Simplified operating scope summary" in text
        assert "Plant count should be 1" in text
        assert "Warehouse count should be 1" in text
        assert "Warehouse.PlantID not single PlantID" in text
        assert "Invalid Procurement PlantID references" in text
        assert "Invalid Procurement WarehouseID references" in text
        assert "DistinctPlantCount" in text
        assert "DistinctWarehouseCount" in text
        assert "GoodsReceiptHeader" in text
        assert "InventoryReceiptDetail" in text
        assert "InventoryTransaction" in text
        assert "Inventory" in text
        assert "IssueName" in text
        assert "IssueCount" in text
