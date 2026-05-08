from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_SQL = ROOT / "docs" / "procurement_v2_lifecycle_quantity_sql_checks.sql"


def test_procurement_v2_lifecycle_quantity_sql_checks_file_exists() -> None:
    assert LIFECYCLE_SQL.exists()


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
    assert "IssueCount" in text


def test_lifecycle_sql_includes_quotation_to_po_cumulative_check() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "OrderedQuantity total > Awarded QuotedQuantity" in text
    assert "GROUP BY sqln.QuotationLineID" in text


def test_lifecycle_sql_includes_status_consistency_checks() -> None:
    text = LIFECYCLE_SQL.read_text(encoding="utf-8")

    assert "Closed PO line with partial StockIn" in text
    assert "Closed PO header with partial StockIn" in text
    assert "Payment status mismatch" in text
    assert "Receipt status hides short or damaged quantity" in text
    assert "Inspection status or rejection reason mismatch" in text
