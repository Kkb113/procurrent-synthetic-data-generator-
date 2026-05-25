from __future__ import annotations

import random
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.services.mes_lifecycle_response import artifact_paths, enrich_mes_lifecycle_summary
from procurement_data_generator.modules.production.allocation import (
    InventoryLot,
    InventoryTransactionLot,
    ProductionAllocationContext,
    allocate_bom,
    allocate_component,
)
from procurement_data_generator.modules.production.performance_profile import profile_stage, summarize_profile
from procurement_data_generator.modules.sales.status_rules import (
    finished_goods_inventory_status,
    invoice_status,
    line_status,
    order_status,
    quantity_equal,
    return_line_status,
)


def test_production_allocation_consumes_matching_inventory_and_transaction_lot() -> None:
    receipt = SimpleNamespace(InventoryReceiptDetailID=7001)
    context = ProductionAllocationContext(
        products=(),
        bom_by_product={},
        routing_by_product={},
        bom_lines_by_bom={},
        inventory_lots_by_component={
            101: [InventoryLot(1, 101, 1, 1, 10.0)],
        },
        txn_lots_by_inventory_key={
            (101, 1, 1): [InventoryTransactionLot(500, 101, 1, 1, 10.0, 2.5, 7001, receipt)],
        },
        component_uom={101: "EA"},
    )

    allocation = allocate_component(101, 4.0, context, random.Random(42))

    assert allocation is not None
    inventory_lot, txn_lot, receipt_row = allocation
    assert inventory_lot.available_quantity == 6.0
    assert txn_lot.remaining_quantity == 6.0
    assert receipt_row.InventoryReceiptDetailID == 7001


def test_production_bom_allocation_rolls_back_when_later_component_is_short() -> None:
    BomLine = namedtuple("BomLine", "ComponentID ComponentQuantity ScrapFactorPct UOM BOMLineID")
    receipt = SimpleNamespace(InventoryReceiptDetailID=7001)
    inventory_lot = InventoryLot(1, 101, 1, 1, 10.0)
    txn_lot = InventoryTransactionLot(500, 101, 1, 1, 10.0, 2.5, 7001, receipt)
    context = ProductionAllocationContext(
        products=(),
        bom_by_product={},
        routing_by_product={},
        bom_lines_by_bom={},
        inventory_lots_by_component={101: [inventory_lot]},
        txn_lots_by_inventory_key={(101, 1, 1): [txn_lot]},
        component_uom={101: "EA", 202: "EA"},
    )

    allocation = allocate_bom(
        (
            BomLine(101, 2.0, 0.0, "EA", 1),
            BomLine(202, 1.0, 0.0, "EA", 2),
        ),
        planned_quantity=2.0,
        allocation_context=context,
        rng=random.Random(42),
    )

    assert allocation is None
    assert inventory_lot.available_quantity == 10.0
    assert txn_lot.remaining_quantity == 10.0


def test_production_performance_profile_records_stage_counts() -> None:
    stages: list[dict] = []

    result = profile_stage(stages, "sample_stage", lambda: pd.DataFrame([{"A": 1}, {"A": 2}]))
    summary = summarize_profile(stages, 1.25)

    assert len(result) == 2
    assert stages[0]["stage_name"] == "sample_stage"
    assert stages[0]["row_count_output"]["dataframe"] == 2
    assert summary["top_suspected_bottleneck"] == "sample_stage"


def test_sales_status_rules_preserve_existing_tolerance_behavior() -> None:
    assert quantity_equal(10.0, 10.005)
    assert line_status(10.0, 10.0, 10.0) == "Closed"
    assert line_status(10.0, 4.0, 2.0) == "Backordered"
    assert line_status(10.0, 10.0, 2.0) == "PartiallyShipped"
    assert order_status(("Closed", "Closed")) == "Closed"
    assert order_status(("Closed", "Backordered")) == "Backordered"
    assert finished_goods_inventory_status(0.0, 0.0, 0.0) == "OutOfStock"
    assert finished_goods_inventory_status(100.0, 100.0, 0.0) == "Hold"
    assert finished_goods_inventory_status(100.0, 0.0, 5.0) == "LowStock"
    assert invoice_status(100.0, 25.0) == "PartiallyPaid"
    assert return_line_status(1.0, 0.0) == "Restocked"
    assert return_line_status(0.0, 1.0) == "Scrapped"
    assert return_line_status(1.0, 1.0) == "Received"


def test_mes_lifecycle_response_helper_discovers_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "pipeline_output"
    (output / "reports").mkdir(parents=True)
    (output / "final_data").mkdir()
    (output / "reports" / "row_budget_report.json").write_text("{}", encoding="utf-8")
    (output / "reports" / "row_count_audit.json").write_text("{}", encoding="utf-8")
    (output / "production" / "run_1" / "reports").mkdir(parents=True)
    (output / "production" / "run_1" / "reports" / "performance_profile_phase4.json").write_text("{}", encoding="utf-8")

    artifacts = artifact_paths(str(output))
    summary = enrich_mes_lifecycle_summary(
        {
            "run_id": "web_run_test",
            "status": "passed",
            "output_folder": str(output),
            "total_rows_generated": 12,
            "warnings": [],
            "errors": [],
            "validation_summary": {"procurement": "passed", "production": "passed", "sales": "passed"},
            "module_results": {
                "procurement": {"total_rows_generated": 5},
                "production": {"total_rows_generated": 4},
                "sales": {"total_rows_generated": 3},
            },
        }
    )

    assert set(artifacts) >= {"final_data", "row_budget_report", "row_count_audit", "performance_profile_phase4"}
    assert summary["message"] == "MES lifecycle generation completed."
    assert summary["total_rows"] == 12
    assert summary["per_module_row_counts"] == {"procurement": 5, "production": 4, "sales": 3}
    assert "final_data_zip" in summary["downloads"]
