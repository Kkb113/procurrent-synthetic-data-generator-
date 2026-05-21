from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.core.row_budget import RowBudgetPlanner, classify_table, planned_target_rows
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.sales.transaction_generator import SalesTransactionGenerator


def test_row_budget_target_total_calculates_scale_factor() -> None:
    schema = _schema(
        [
            _table("CustomerMaster", "customer_master", "Master", 100),
            _table("SalesOrderHdr", "sales_order_header", "Sales", 100),
            _table("SalesOrderLine", "sales_order_line", "Sales", 200),
            _table("FinishedGoodsInventory", "finished_goods_inventory", "Inventory", 50),
        ]
    )

    plan = RowBudgetPlanner().plan_modules({"sales": schema}, GenerationConfig(target_total_rows=650))

    assert round(plan.applied_row_scale_factor, 2) == 1.67
    assert plan.planned_row_targets["CustomerMaster"] == 100
    assert plan.planned_row_targets["FinishedGoodsInventory"] == 50
    assert plan.planned_row_targets["SalesOrderHdr"] == 167
    assert plan.planned_row_targets["SalesOrderLine"] == 333
    assert plan.planned_total_rows == 650


def test_row_budget_row_scale_factor_and_max_rows_per_table() -> None:
    schema = _schema(
        [
            _table("PurchaseOrderHdr", "purchase_order_header", "Procurement", 100),
            _table("PurchaseOrderLine", "purchase_order_line", "Procurement", 300),
            _table("Inventory", "inventory", "Inventory", 40),
        ]
    )

    plan = RowBudgetPlanner().plan_modules(
        {"procurement": schema},
        GenerationConfig(row_scale_factor=3.0, max_rows_per_table=250),
    )

    assert plan.planned_row_targets["PurchaseOrderHdr"] == 250
    assert plan.planned_row_targets["PurchaseOrderLine"] == 250
    assert plan.planned_row_targets["Inventory"] == 40


def test_row_budget_applies_lifecycle_reserve_for_analytics_scale_targets() -> None:
    schema = _schema(
        [
            _table("CustomerMaster", "customer_master", "Master", 1000),
            _table("SalesOrderHdr", "sales_order_header", "Sales", 100000),
            _table("SalesOrderLine", "sales_order_line", "Sales", 100000),
        ]
    )

    plan = RowBudgetPlanner().plan_modules({"sales": schema}, GenerationConfig(target_total_rows=350000))

    assert plan.planned_total_rows == 364000
    assert plan.applied_row_scale_factor > 1.0


def test_row_budget_classifies_balance_and_dimension_tables() -> None:
    assert classify_table(_table("ComponentMaster", "component_master", "Master", 10)) == "dimension_master"
    assert classify_table(_table("Inventory", "inventory", "Inventory", 10)) == "balance_snapshot"
    assert classify_table(_table("SalesOrderLine", "sales_order_line", "Sales", 10)) == "transaction_detail"


def test_row_budget_report_includes_planned_actual_status_and_notes(tmp_path: Path) -> None:
    schema = _schema(
        [
            _table("SalesOrderHdr", "sales_order_header", "Sales", 100),
            _table("FinishedGoodsInventory", "finished_goods_inventory", "Inventory", 20),
        ]
    )
    plan = RowBudgetPlanner().plan_modules({"sales": schema}, GenerationConfig(row_scale_factor=2.0))

    path = plan.write_report(
        tmp_path,
        {"sales": {"SalesOrderHdr": 185, "FinishedGoodsInventory": 18}},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["planned_total_rows"] == 220
    assert payload["actual_total_rows"] == 203
    assert payload["tables"]["SalesOrderHdr"]["planned_target"] == 200
    assert payload["tables"]["SalesOrderHdr"]["status"] == "within_tolerance"
    assert payload["tables"]["FinishedGoodsInventory"]["status"] == "naturally_derived"
    assert "FinishedGoodsInventory" in payload["naturally_derived_tables"]


def test_planned_target_priority_for_generators() -> None:
    schema = _schema([_table("SalesOrderHdr", "sales_order_header", "Sales", 12)])
    config = GenerationConfig(planned_row_targets={"SalesOrderHdr": 75, "ProductMaster": 30})

    assert planned_target_rows(config, "SalesOrderHdr", 12) == 75
    assert SalesTransactionGenerator(generation_config=config)._target_rows(schema, "SalesOrderHdr", 12) == 75
    production_generator = ProductionMasterDataGenerator(generation_config=config)
    product_table = _table("ProductMaster", "product_master", "Master", 10)

    assert production_generator.get_target_rows(product_table, SimpleNamespace(row_count_plan=[])) == 30


def _schema(tables: list[TableContract]) -> SchemaContract:
    return SchemaContract(tables={table.table_name: table for table in tables})


def _table(table_name: str, table_role: str, area: str, target_rows: int) -> TableContract:
    return TableContract(
        table_name=table_name,
        process_order=1,
        area=area,
        table_role=table_role,
        target_rows=target_rows,
        columns=[],
    )
