"""Production Execution module within MES context v1 transaction and execution data generator."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.modules.shared.quantity_precision import (
    apply_quantity_precision,
    is_whole_quantity,
    requires_integer_quantity,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_industry_profile_or_default


PRODUCTION_TRANSACTION_TABLES = (
    "ProductionOrderHdr",
    "ProductionOrderLine",
    "ProductionMaterialRequirement",
    "MaterialIssueHeader",
    "MaterialIssueLine",
    "ProductionBatch",
    "OperationExecution",
    "ProductionQualityInspection",
    "ProductionQualityResult",
    "ScrapReworkEvent",
    "FinishedGoodsReceipt",
    "FinishedGoodsInventory",
    "ProductionGenealogy",
    "ProductionCostSummary",
)
PRODUCTION_MASTER_TABLES = (
    "ProductMaster",
    "BOMHeader",
    "BOMLine",
    "WorkCenter",
    "RoutingHeader",
    "RoutingOperation",
    "ProductionShift",
)


@dataclass(frozen=True)
class ProductionMasterContext:
    """Production setup tables generated in Phase 3."""

    product_master: pd.DataFrame
    bom_header: pd.DataFrame
    bom_line: pd.DataFrame
    work_center: pd.DataFrame
    routing_header: pd.DataFrame
    routing_operation: pd.DataFrame
    production_shift: pd.DataFrame


@dataclass(frozen=True)
class ProcurementExecutionContext:
    """Procurement stock and traceability context consumed by Production."""

    component_master: pd.DataFrame
    plant: pd.DataFrame
    warehouse: pd.DataFrame
    inventory: pd.DataFrame
    inventory_transaction: pd.DataFrame
    inventory_receipt_detail: pd.DataFrame
    supplier_master: pd.DataFrame
    used_fallback: bool = False


class ProductionTransactionGenerator:
    """Generate the fourteen Production Execution module within MES context v1 transaction/execution tables."""

    def __init__(self, industry_profile: IndustryProfile | None = None, profile_id: str | None = None) -> None:
        self.industry_profile = industry_profile or get_industry_profile_or_default(profile_id)

    def generate_transaction_data(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        master_data: dict[str, pd.DataFrame] | ProductionMasterContext,
        upstream_data: dict[str, pd.DataFrame] | ProcurementExecutionContext | None = None,
        seed: int | None = None,
    ) -> tuple[dict[str, pd.DataFrame], ValidationReport]:
        """Generate integrated Production transaction data from master and Procurement stock data."""

        report = ValidationReport(
            total_tables_detected=len(schema.tables),
            total_columns_detected=sum(len(table.columns) for table in schema.tables.values()),
        )
        rng = random.Random(seed)
        master = _coerce_master_context(master_data)
        upstream = self._coerce_upstream_context(upstream_data, master, report)

        inventory_remaining = {
            int(row.InventoryID): float(row.AvailableQuantity)
            for row in upstream.inventory.itertuples(index=False)
        }
        txn_remaining = {
            int(row.InventoryTransactionID): float(row.TransactionQuantity)
            for row in upstream.inventory_transaction.itertuples(index=False)
        }

        generated = self._generate_orders_requirements_and_issues(
            schema=schema,
            plan=plan,
            master=master,
            upstream=upstream,
            inventory_remaining=inventory_remaining,
            txn_remaining=txn_remaining,
            rng=rng,
        )
        batches = self._generate_batches(schema.tables["ProductionBatch"], plan, generated, rng)
        operations = self._generate_operations(schema.tables["OperationExecution"], plan, master, generated, batches, rng)
        self._align_order_line_output(generated["ProductionOrderLine"], operations, batches)
        inspections, quality_results = self._generate_quality(schema, plan, master, batches, operations, rng)
        scrap_rework = self._generate_scrap_rework(schema.tables["ScrapReworkEvent"], plan, batches, operations, rng)
        receipts = self._generate_finished_goods_receipts(schema.tables["FinishedGoodsReceipt"], plan, master, generated, batches, operations, rng)
        cost_summary = self._generate_cost_summary(schema.tables["ProductionCostSummary"], plan, generated, batches, operations, scrap_rework, receipts, rng)
        self._align_receipt_costs(receipts, cost_summary)
        inventory = self._generate_finished_goods_inventory(schema.tables["FinishedGoodsInventory"], receipts, rng)
        genealogy = self._generate_genealogy(schema.tables["ProductionGenealogy"], generated, receipts, upstream)

        dataframes = {
            **generated,
            "ProductionBatch": batches,
            "OperationExecution": operations,
            "ProductionQualityInspection": inspections,
            "ProductionQualityResult": quality_results,
            "ScrapReworkEvent": scrap_rework,
            "FinishedGoodsReceipt": receipts,
            "FinishedGoodsInventory": inventory,
            "ProductionGenealogy": genealogy,
            "ProductionCostSummary": cost_summary,
        }
        self.validate_generated_transaction_data(dataframes, master, upstream, report)
        return dataframes, report

    def load_master_data(self, folder: str | Path) -> ProductionMasterContext:
        """Load Production master/setup CSV files from a folder."""

        path = Path(folder)
        frames = {table: pd.read_csv(path / f"{table}.csv") for table in PRODUCTION_MASTER_TABLES}
        return _coerce_master_context(frames)

    def load_upstream_data(self, folder: str | Path | None, master: ProductionMasterContext | None = None, report: ValidationReport | None = None) -> ProcurementExecutionContext:
        """Load Procurement final data or deterministic fallback context."""

        if folder is not None:
            path = Path(folder)
            required = [
                "ComponentMaster",
                "Plant",
                "Warehouse",
                "Inventory",
                "InventoryTransaction",
                "InventoryReceiptDetail",
                "SupplierMaster",
            ]
            if all((path / f"{table}.csv").exists() for table in required):
                return ProcurementExecutionContext(
                    component_master=pd.read_csv(path / "ComponentMaster.csv"),
                    plant=pd.read_csv(path / "Plant.csv"),
                    warehouse=pd.read_csv(path / "Warehouse.csv"),
                    inventory=pd.read_csv(path / "Inventory.csv"),
                    inventory_transaction=pd.read_csv(path / "InventoryTransaction.csv"),
                    inventory_receipt_detail=pd.read_csv(path / "InventoryReceiptDetail.csv"),
                    supplier_master=pd.read_csv(path / "SupplierMaster.csv"),
                    used_fallback=False,
                )
            if report is not None:
                report.add_warning(
                    message="Upstream Procurement folder is missing required final data CSVs; using deterministic fallback execution context.",
                    suggested_fix="Provide Procurement v2 final_data with Inventory, InventoryTransaction, InventoryReceiptDetail, ComponentMaster, Plant, Warehouse, and SupplierMaster.",
                )
        elif report is not None:
            report.add_warning(
                message="No upstream Procurement final data was supplied; using deterministic fallback execution context.",
                suggested_fix="Pass --upstream-data pointing to Procurement v2 final_data for integrated generation.",
            )
        return _fallback_upstream_context(master)

    def export_transaction_data(self, dataframes: dict[str, pd.DataFrame], output_folder: str | Path) -> list[Path]:
        """Export generated transaction/execution tables to CSV files."""

        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        paths = []
        for table_name in PRODUCTION_TRANSACTION_TABLES:
            path = output_path / f"{table_name}.csv"
            dataframes[table_name].to_csv(path, index=False)
            paths.append(path)
        return paths

    def get_target_rows(self, table: TableContract, plan: LLMGenerationPlan) -> int:
        for row_count in plan.row_count_plan:
            if row_count.table_name == table.table_name:
                return row_count.target_rows
        return table.target_rows

    def validate_generated_transaction_data(
        self,
        dataframes: dict[str, pd.DataFrame],
        master: ProductionMasterContext,
        upstream: ProcurementExecutionContext,
        report: ValidationReport,
    ) -> None:
        """Lightweight self-checks for Phase 4 generation."""

        if set(dataframes) != set(PRODUCTION_TRANSACTION_TABLES):
            report.add_error(
                message="Production Phase 4 must generate exactly the fourteen transaction/execution tables.",
                suggested_fix="Keep master/setup generation in Phase 3 and transaction generation in Phase 4.",
            )
        self._validate_inventory_consumption(dataframes["MaterialIssueLine"], upstream.inventory, report)
        self._validate_formula_columns(dataframes, report)
        self._validate_2025_dates(dataframes, report)
        self._validate_genealogy(dataframes, upstream, report)
        self._validate_uom_precision(dataframes, master, upstream, report)

    def _coerce_upstream_context(
        self,
        upstream_data: dict[str, pd.DataFrame] | ProcurementExecutionContext | None,
        master: ProductionMasterContext,
        report: ValidationReport,
    ) -> ProcurementExecutionContext:
        if isinstance(upstream_data, ProcurementExecutionContext):
            return upstream_data
        if isinstance(upstream_data, dict):
            return ProcurementExecutionContext(
                component_master=upstream_data["ComponentMaster"],
                plant=upstream_data["Plant"],
                warehouse=upstream_data["Warehouse"],
                inventory=upstream_data["Inventory"],
                inventory_transaction=upstream_data["InventoryTransaction"],
                inventory_receipt_detail=upstream_data["InventoryReceiptDetail"],
                supplier_master=upstream_data["SupplierMaster"],
                used_fallback=False,
            )
        return self.load_upstream_data(None, master, report)

    def _generate_orders_requirements_and_issues(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        master: ProductionMasterContext,
        upstream: ProcurementExecutionContext,
        inventory_remaining: dict[int, float],
        txn_remaining: dict[int, float],
        rng: random.Random,
    ) -> dict[str, pd.DataFrame]:
        target_orders = min(
            self.get_target_rows(schema.tables["ProductionOrderHdr"], plan),
            self.get_target_rows(schema.tables["ProductionOrderLine"], plan),
            200,
        )
        max_requirements = min(self.get_target_rows(schema.tables["ProductionMaterialRequirement"], plan), 1200)
        headers: list[dict[str, Any]] = []
        lines: list[dict[str, Any]] = []
        requirements: list[dict[str, Any]] = []
        issue_headers: list[dict[str, Any]] = []
        issue_lines: list[dict[str, Any]] = []
        issue_header_lookup: dict[tuple[int, int, int], int] = {}

        bom_lines_by_bom = {bom_id: rows for bom_id, rows in master.bom_line.groupby("BOMID")}
        bom_by_product = {product_id: rows for product_id, rows in master.bom_header.groupby("ProductID")}
        routing_by_product = {product_id: rows for product_id, rows in master.routing_header.groupby("ProductID")}
        component_uom = _component_uom_lookup(upstream.component_master)
        requirement_id = 1
        issue_line_id = 1
        production_order_id = 1
        production_order_line_id = 1
        attempts = 0

        while production_order_line_id <= target_orders and requirement_id <= max_requirements and attempts < target_orders * 8:
            attempts += 1
            product = master.product_master.iloc[(attempts - 1) % len(master.product_master)]
            product_id = int(product.ProductID)
            product_boms = bom_by_product.get(product_id)
            product_routings = routing_by_product.get(product_id)
            if product_boms is None or product_routings is None:
                continue
            bom = product_boms.iloc[(attempts - 1) % len(product_boms)]
            routing = product_routings.iloc[(attempts - 1) % len(product_routings)]
            bom_lines = bom_lines_by_bom.get(bom.BOMID)
            if bom_lines is None or bom_lines.empty:
                continue

            planned_quantity = float(rng.randint(1, 4))
            allocations = self._allocate_bom(
                bom_lines=bom_lines,
                planned_quantity=planned_quantity,
                upstream=upstream,
                inventory_remaining=inventory_remaining,
                txn_remaining=txn_remaining,
                rng=rng,
            )
            if allocations is None and planned_quantity != 1:
                planned_quantity = 1.0
                allocations = self._allocate_bom(
                    bom_lines=bom_lines,
                    planned_quantity=planned_quantity,
                    upstream=upstream,
                    inventory_remaining=inventory_remaining,
                    txn_remaining=txn_remaining,
                    rng=rng,
                )
            if allocations is None:
                continue

            order_date = date(2025, 1, 1) + timedelta(days=rng.randint(0, 300))
            actual_start = order_date + timedelta(days=rng.randint(0, 5))
            actual_end = min(actual_start + timedelta(days=rng.randint(0, 7)), date(2025, 12, 31))
            planned_start = actual_start
            planned_end = actual_end
            plant_id = int(bom.PlantID)
            headers.append(
                {
                    "ProductionOrderID": production_order_id,
                    "PlantID": plant_id,
                    "OrderDate": order_date.isoformat(),
                    "PlannedStartDate": planned_start.isoformat(),
                    "PlannedEndDate": planned_end.isoformat(),
                    "ActualStartDate": actual_start.isoformat(),
                    "ActualEndDate": actual_end.isoformat(),
                    "ProductionOrderStatus": "Completed",
                    "Priority": _weighted_choice(rng, ["Low", "Normal", "High", "Urgent"], [0.1, 0.65, 0.2, 0.05]),
                }
            )
            lines.append(
                {
                    "ProductionOrderLineID": production_order_line_id,
                    "ProductionOrderID": production_order_id,
                    "ProductID": product_id,
                    "BOMID": int(bom.BOMID),
                    "RoutingID": int(routing.RoutingID),
                    "PlannedQuantity": planned_quantity,
                    "ReleasedQuantity": planned_quantity,
                    "CompletedQuantity": planned_quantity,
                    "GoodQuantity": planned_quantity,
                    "ScrapQuantity": 0.0,
                    "UOM": product.UOM,
                    "LineStatus": "Completed",
                }
            )

            for allocation in allocations:
                bom_line, required_quantity, scrap_adjusted, inventory_row, txn_row, receipt_row = allocation
                inventory_id = int(inventory_row.InventoryID)
                txn_id = int(txn_row.InventoryTransactionID)
                inventory_remaining[inventory_id] -= scrap_adjusted
                txn_remaining[txn_id] -= scrap_adjusted
                warehouse_id = int(inventory_row.WarehouseID)
                issue_key = (production_order_id, plant_id, warehouse_id)
                if issue_key not in issue_header_lookup:
                    issue_header_lookup[issue_key] = len(issue_headers) + 1
                    issue_headers.append(
                        {
                            "MaterialIssueID": issue_header_lookup[issue_key],
                            "ProductionOrderID": production_order_id,
                            "PlantID": plant_id,
                            "WarehouseID": warehouse_id,
                            "IssueDate": actual_start.isoformat(),
                            "IssueStatus": "Issued",
                        }
                    )
                issue_id = issue_header_lookup[issue_key]
                component_id = int(bom_line.ComponentID)
                uom = component_uom.get(component_id, str(bom_line.UOM))
                requirements.append(
                    {
                        "MaterialRequirementID": requirement_id,
                        "ProductionOrderLineID": production_order_line_id,
                        "BOMLineID": int(bom_line.BOMLineID),
                        "ComponentID": component_id,
                        "PlantID": int(inventory_row.PlantID),
                        "WarehouseID": warehouse_id,
                        "InventoryID": inventory_id,
                        "RequiredQuantity": required_quantity,
                        "ScrapAdjustedQuantity": scrap_adjusted,
                        "IssuedQuantity": scrap_adjusted,
                        "RequirementStatus": "Consumed",
                    }
                )
                unit_cost = round(float(txn_row.UnitPrice), 2)
                issue_lines.append(
                    {
                        "MaterialIssueLineID": issue_line_id,
                        "MaterialIssueID": issue_id,
                        "MaterialRequirementID": requirement_id,
                        "ComponentID": component_id,
                        "InventoryID": inventory_id,
                        "SourceInventoryTransactionID": txn_id,
                        "InventoryReceiptDetailID": int(receipt_row.InventoryReceiptDetailID),
                        "IssuedQuantity": scrap_adjusted,
                        "UOM": uom,
                        "UnitCost": unit_cost,
                        "IssueValue": round(scrap_adjusted * unit_cost, 2),
                        "IssueStatus": "Issued",
                    }
                )
                requirement_id += 1
                issue_line_id += 1

            production_order_id += 1
            production_order_line_id += 1

        return {
            "ProductionOrderHdr": pd.DataFrame(headers),
            "ProductionOrderLine": pd.DataFrame(lines),
            "ProductionMaterialRequirement": pd.DataFrame(requirements),
            "MaterialIssueHeader": pd.DataFrame(issue_headers),
            "MaterialIssueLine": pd.DataFrame(issue_lines),
        }

    def _allocate_bom(
        self,
        bom_lines: pd.DataFrame,
        planned_quantity: float,
        upstream: ProcurementExecutionContext,
        inventory_remaining: dict[int, float],
        txn_remaining: dict[int, float],
        rng: random.Random,
    ) -> list[tuple[Any, float, float, Any, Any, Any]] | None:
        allocations = []
        used_inventory: dict[int, float] = {}
        used_txn: dict[int, float] = {}
        for bom_line in bom_lines.itertuples(index=False):
            uom = str(bom_line.UOM)
            required_quantity = float(bom_line.ComponentQuantity) * planned_quantity
            scrap_adjusted = required_quantity * (1 + float(bom_line.ScrapFactorPct) / 100)
            scrap_adjusted = apply_quantity_precision(
                scrap_adjusted,
                uom,
                minimum=1 if requires_integer_quantity(uom) else 0.01,
            )
            required_quantity = apply_quantity_precision(
                required_quantity,
                uom,
                minimum=1 if requires_integer_quantity(uom) else 0.01,
            )
            allocation = self._allocate_component(
                component_id=int(bom_line.ComponentID),
                quantity=scrap_adjusted,
                upstream=upstream,
                inventory_remaining=inventory_remaining,
                txn_remaining=txn_remaining,
                used_inventory=used_inventory,
                used_txn=used_txn,
                rng=rng,
            )
            if allocation is None:
                return None
            inventory_row, txn_row, receipt_row = allocation
            used_inventory[int(inventory_row.InventoryID)] = used_inventory.get(int(inventory_row.InventoryID), 0.0) + scrap_adjusted
            used_txn[int(txn_row.InventoryTransactionID)] = used_txn.get(int(txn_row.InventoryTransactionID), 0.0) + scrap_adjusted
            allocations.append((bom_line, required_quantity, scrap_adjusted, inventory_row, txn_row, receipt_row))
        return allocations

    def _allocate_component(
        self,
        component_id: int,
        quantity: float,
        upstream: ProcurementExecutionContext,
        inventory_remaining: dict[int, float],
        txn_remaining: dict[int, float],
        used_inventory: dict[int, float],
        used_txn: dict[int, float],
        rng: random.Random,
    ) -> tuple[Any, Any, Any] | None:
        inventory_candidates = upstream.inventory[upstream.inventory["ComponentID"] == component_id]
        if inventory_candidates.empty:
            return None
        inventory_records = inventory_candidates.sample(frac=1, random_state=rng.randint(1, 1_000_000)).itertuples(index=False)
        receipts_by_id = {
            int(row.InventoryReceiptDetailID): row
            for row in upstream.inventory_receipt_detail.itertuples(index=False)
        }
        for inventory_row in inventory_records:
            inventory_id = int(inventory_row.InventoryID)
            inventory_available = inventory_remaining.get(inventory_id, 0.0) - used_inventory.get(inventory_id, 0.0)
            if inventory_available + 0.0001 < quantity:
                continue
            txn_candidates = upstream.inventory_transaction[
                (upstream.inventory_transaction["ComponentID"] == component_id)
                & (upstream.inventory_transaction["PlantID"] == inventory_row.PlantID)
                & (upstream.inventory_transaction["WarehouseID"] == inventory_row.WarehouseID)
            ]
            for txn_row in txn_candidates.itertuples(index=False):
                txn_id = int(txn_row.InventoryTransactionID)
                txn_available = txn_remaining.get(txn_id, 0.0) - used_txn.get(txn_id, 0.0)
                if txn_available + 0.0001 < quantity:
                    continue
                receipt_id = _receipt_id_from_reference(txn_row.ReferenceDocument)
                receipt_row = receipts_by_id.get(receipt_id)
                if receipt_row is None:
                    receipt_match = upstream.inventory_receipt_detail[
                        upstream.inventory_receipt_detail["InspectionResultID"] == txn_row.InspectionResultID
                    ]
                    if receipt_match.empty:
                        continue
                    receipt_row = next(receipt_match.itertuples(index=False))
                return inventory_row, txn_row, receipt_row
        return None

    def _generate_batches(self, table: TableContract, plan: LLMGenerationPlan, generated: dict[str, pd.DataFrame], rng: random.Random) -> pd.DataFrame:
        rows = []
        orders = generated["ProductionOrderHdr"].set_index("ProductionOrderID")
        for index, line in enumerate(generated["ProductionOrderLine"].itertuples(index=False), start=1):
            order = orders.loc[line.ProductionOrderID]
            rows.append(
                {
                    "ProductionBatchID": index,
                    "ProductionOrderLineID": int(line.ProductionOrderLineID),
                    "BatchNumber": f"PB-2025-{index:06d}",
                    "ProductID": int(line.ProductID),
                    "PlantID": int(order.PlantID),
                    "PlannedBatchQuantity": float(line.PlannedQuantity),
                    "ActualStartDate": order.ActualStartDate,
                    "ActualEndDate": order.ActualEndDate,
                    "BatchStatus": "Completed",
                }
            )
        return pd.DataFrame(rows)

    def _generate_operations(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        master: ProductionMasterContext,
        generated: dict[str, pd.DataFrame],
        batches: pd.DataFrame,
        rng: random.Random,
    ) -> pd.DataFrame:
        routing_operations_by_routing = {routing_id: rows.sort_values("OperationSequence") for routing_id, rows in master.routing_operation.groupby("RoutingID")}
        line_by_id = generated["ProductionOrderLine"].set_index("ProductionOrderLineID")
        shifts_by_wc = {wc_id: rows for wc_id, rows in master.production_shift.groupby("WorkCenterID")}
        rows = []
        operation_id = 1
        for batch in batches.itertuples(index=False):
            line = line_by_id.loc[batch.ProductionOrderLineID]
            routing_operations = routing_operations_by_routing.get(line.RoutingID)
            if routing_operations is None or routing_operations.empty:
                continue
            input_quantity = float(batch.PlannedBatchQuantity)
            batch_date = pd.to_datetime(batch.ActualStartDate).date()
            for op_index, routing_operation in enumerate(routing_operations.itertuples(index=False), start=1):
                scrap = 0.0
                if input_quantity >= 2 and rng.random() < 0.08:
                    scrap = 1.0
                rework = 1.0 if input_quantity >= 2 and rng.random() < 0.04 else 0.0
                output_quantity = max(input_quantity - scrap, 0.0)
                shift_id = _shift_for_work_center(shifts_by_wc, int(routing_operation.WorkCenterID), batch_date)
                start_dt = datetime.combine(batch_date, datetime.min.time()) + timedelta(hours=8 + op_index)
                end_dt = start_dt + timedelta(minutes=60)
                rows.append(
                    {
                        "OperationExecutionID": operation_id,
                        "ProductionBatchID": int(batch.ProductionBatchID),
                        "RoutingOperationID": int(routing_operation.RoutingOperationID),
                        "WorkCenterID": int(routing_operation.WorkCenterID),
                        "ShiftID": int(shift_id),
                        "OperationSequence": int(routing_operation.OperationSequence),
                        "ActualStartDateTime": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "ActualEndDateTime": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "InputQuantity": input_quantity,
                        "OutputQuantity": output_quantity,
                        "ScrapQuantity": scrap,
                        "ReworkQuantity": rework,
                        "OperationStatus": "Completed",
                    }
                )
                input_quantity = output_quantity
                operation_id += 1
        return pd.DataFrame(rows)

    def _align_order_line_output(self, order_lines: pd.DataFrame, operations: pd.DataFrame, batches: pd.DataFrame) -> None:
        if operations.empty:
            return
        final_output = operations.sort_values(["ProductionBatchID", "OperationSequence"]).groupby("ProductionBatchID").tail(1)
        scrap_by_batch = operations.groupby("ProductionBatchID")["ScrapQuantity"].sum().to_dict()
        batch_to_line = dict(zip(batches["ProductionBatchID"], batches["ProductionOrderLineID"]))
        for row in final_output.itertuples(index=False):
            line_id = batch_to_line[row.ProductionBatchID]
            mask = order_lines["ProductionOrderLineID"] == line_id
            scrap = float(scrap_by_batch.get(row.ProductionBatchID, 0.0))
            order_lines.loc[mask, "GoodQuantity"] = float(row.OutputQuantity)
            order_lines.loc[mask, "ScrapQuantity"] = scrap
            order_lines.loc[mask, "CompletedQuantity"] = float(row.OutputQuantity) + scrap

    def _generate_quality(self, schema: SchemaContract, plan: LLMGenerationPlan, master: ProductionMasterContext, batches: pd.DataFrame, operations: pd.DataFrame, rng: random.Random) -> tuple[pd.DataFrame, pd.DataFrame]:
        inspection_rows = []
        result_rows = []
        batch_product = dict(zip(batches["ProductionBatchID"], batches["ProductID"]))
        final_ops = operations.sort_values(["ProductionBatchID", "OperationSequence"]).groupby("ProductionBatchID").tail(1)
        candidate_ops = list(final_ops.itertuples(index=False))
        for index, operation in enumerate(candidate_ops, start=1):
            output_quantity = float(operation.OutputQuantity)
            sample_quantity = max(1.0, min(output_quantity, float(round(output_quantity * 0.2)) if output_quantity >= 5 else output_quantity))
            failed = 1.0 if sample_quantity >= 10 and rng.random() < 0.12 else 0.0
            passed = sample_quantity - failed
            inspection_status = "PartiallyPassed" if failed > 0 else "Passed"
            if failed == 0:
                result_status = "Passed"
                defect_code = "NoDefect"
                defect_severity = "None"
            else:
                result_status = "PartiallyFailed" if passed > 0 else "Failed"
                defect_code = self._quality_defect_code(rng)
                defect_severity = self._quality_defect_severity(rng)
            inspection_date = pd.to_datetime(operation.ActualEndDateTime).date().isoformat()
            inspection_rows.append(
                {
                    "ProductionInspectionID": index,
                    "ProductionBatchID": int(operation.ProductionBatchID),
                    "OperationExecutionID": int(operation.OperationExecutionID),
                    "ProductID": int(batch_product[operation.ProductionBatchID]),
                    "InspectionDate": inspection_date,
                    "InspectionType": "Final",
                    "SampleQuantity": sample_quantity,
                    "InspectorName": f"Production Inspector {((index - 1) % 12) + 1}",
                    "InspectionStatus": inspection_status,
                }
            )
            result_rows.append(
                {
                    "ProductionQualityResultID": index,
                    "ProductionInspectionID": index,
                    "TestedQuantity": sample_quantity,
                    "PassedQuantity": passed,
                    "FailedQuantity": failed,
                    "DefectCode": defect_code,
                    "DefectSeverity": defect_severity,
                    "ResultStatus": result_status,
                }
            )
        return pd.DataFrame(inspection_rows), pd.DataFrame(result_rows)

    def _quality_defect_code(self, rng: random.Random) -> str:
        defect_codes = tuple(code for code in self.industry_profile.production.quality_defect_codes if code and code != "NoDefect")
        if not defect_codes:
            defect_codes = ("FunctionalFailure",)
        return str(defect_codes[rng.randrange(len(defect_codes))])

    def _quality_defect_severity(self, rng: random.Random) -> str:
        return rng.choices(("Low", "Medium", "High", "Critical"), weights=(0.65, 0.25, 0.08, 0.02), k=1)[0]

    def _generate_scrap_rework(self, table: TableContract, plan: LLMGenerationPlan, batches: pd.DataFrame, operations: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
        product_by_batch = dict(zip(batches["ProductionBatchID"], batches["ProductID"]))
        rows = []
        event_id = 1
        for operation in operations.itertuples(index=False):
            event_date = pd.to_datetime(operation.ActualEndDateTime).date().isoformat()
            if float(operation.ScrapQuantity) > 0:
                rows.append(
                    {
                        "ScrapReworkID": event_id,
                        "ProductionBatchID": int(operation.ProductionBatchID),
                        "OperationExecutionID": int(operation.OperationExecutionID),
                        "ProductID": int(product_by_batch[operation.ProductionBatchID]),
                        "EventType": "Scrap",
                        "Quantity": float(operation.ScrapQuantity),
                        "ReasonCode": "Process Defect",
                        "CostImpact": round(float(operation.ScrapQuantity) * rng.uniform(75, 250), 2),
                        "EventDate": event_date,
                    }
                )
                event_id += 1
            if float(operation.ReworkQuantity) > 0:
                rows.append(
                    {
                        "ScrapReworkID": event_id,
                        "ProductionBatchID": int(operation.ProductionBatchID),
                        "OperationExecutionID": int(operation.OperationExecutionID),
                        "ProductID": int(product_by_batch[operation.ProductionBatchID]),
                        "EventType": "Rework",
                        "Quantity": float(operation.ReworkQuantity),
                        "ReasonCode": "Rework Hold",
                        "CostImpact": round(float(operation.ReworkQuantity) * rng.uniform(40, 180), 2),
                        "EventDate": event_date,
                    }
                )
                event_id += 1
        return pd.DataFrame(rows, columns=[column.column_name for column in table.columns])

    def _generate_finished_goods_receipts(self, table: TableContract, plan: LLMGenerationPlan, master: ProductionMasterContext, generated: dict[str, pd.DataFrame], batches: pd.DataFrame, operations: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
        final_output = operations.sort_values(["ProductionBatchID", "OperationSequence"]).groupby("ProductionBatchID").tail(1)
        output_by_batch = dict(zip(final_output["ProductionBatchID"], final_output["OutputQuantity"]))
        scrap_by_batch = operations.groupby("ProductionBatchID")["ScrapQuantity"].sum().to_dict()
        line_by_id = generated["ProductionOrderLine"].set_index("ProductionOrderLineID")
        product_cost = dict(zip(master.product_master["ProductID"], master.product_master["StandardCost"]))
        rows = []
        for index, batch in enumerate(batches.itertuples(index=False), start=1):
            line = line_by_id.loc[batch.ProductionOrderLineID]
            issue_headers_for_order = generated["MaterialIssueHeader"][
                generated["MaterialIssueHeader"]["ProductionOrderID"] == line.ProductionOrderID
            ]
            warehouse_id = int(issue_headers_for_order.iloc[0]["WarehouseID"]) if not issue_headers_for_order.empty else int(batch.PlantID)
            receipt_date = min(pd.to_datetime(batch.ActualEndDate).date() + timedelta(days=1), date(2025, 12, 31))
            rows.append(
                {
                    "FinishedGoodsReceiptID": index,
                    "ProductionBatchID": int(batch.ProductionBatchID),
                    "ProductionOrderLineID": int(batch.ProductionOrderLineID),
                    "ProductID": int(batch.ProductID),
                    "PlantID": int(batch.PlantID),
                    "WarehouseID": warehouse_id,
                    "ReceiptDate": receipt_date.isoformat(),
                    "GoodQuantity": float(output_by_batch.get(batch.ProductionBatchID, line.GoodQuantity)),
                    "ScrapQuantity": float(scrap_by_batch.get(batch.ProductionBatchID, 0.0)),
                    "UnitCost": round(float(product_cost.get(batch.ProductID, 1000.0)), 2),
                    "ReceiptValue": 0.0,
                    "ReceiptStatus": "Received",
                }
            )
        receipts = pd.DataFrame(rows)
        receipts["ReceiptValue"] = (receipts["GoodQuantity"] * receipts["UnitCost"]).round(2)
        return receipts

    def _generate_finished_goods_inventory(self, table: TableContract, receipts: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
        rows = []
        for index, ((product_id, plant_id, warehouse_id), group) in enumerate(receipts.groupby(["ProductID", "PlantID", "WarehouseID"]), start=1):
            on_hand = float(group["GoodQuantity"].sum())
            on_hand_value = round(float(group["ReceiptValue"].sum()), 2)
            reserved = 0.0 if on_hand < 5 else float(rng.randint(0, max(0, int(on_hand * 0.1))))
            available = on_hand - reserved
            status = "OutOfStock" if on_hand <= 0 else ("Hold" if available <= 0 else ("LowStock" if available <= on_hand * 0.1 else "Available"))
            rows.append(
                {
                    "FinishedGoodsInventoryID": index,
                    "ProductID": int(product_id),
                    "PlantID": int(plant_id),
                    "WarehouseID": int(warehouse_id),
                    "OnHandQuantity": on_hand,
                    "ReservedQuantity": reserved,
                    "AvailableQuantity": available,
                    "OnHandValue": on_hand_value,
                    "LastReceiptDate": pd.to_datetime(group["ReceiptDate"]).max().date().isoformat(),
                    "InventoryStatus": status,
                }
            )
        return pd.DataFrame(rows)

    def _generate_genealogy(self, table: TableContract, generated: dict[str, pd.DataFrame], receipts: pd.DataFrame, upstream: ProcurementExecutionContext) -> pd.DataFrame:
        req_to_line = dict(zip(generated["ProductionMaterialRequirement"]["MaterialRequirementID"], generated["ProductionMaterialRequirement"]["ProductionOrderLineID"]))
        receipts_by_line = {line_id: row for line_id, row in receipts.set_index("ProductionOrderLineID").iterrows()}
        receipt_supplier = dict(zip(upstream.inventory_receipt_detail["InventoryReceiptDetailID"], upstream.inventory_receipt_detail["SupplierID"]))
        rows = []
        genealogy_id = 1
        for issue in generated["MaterialIssueLine"].itertuples(index=False):
            line_id = req_to_line[issue.MaterialRequirementID]
            receipt = receipts_by_line.get(line_id)
            if receipt is None:
                continue
            rows.append(
                {
                    "ProductionGenealogyID": genealogy_id,
                    "FinishedGoodsReceiptID": int(receipt.FinishedGoodsReceiptID),
                    "ProductionBatchID": int(receipt.ProductionBatchID),
                    "MaterialIssueLineID": int(issue.MaterialIssueLineID),
                    "ComponentID": int(issue.ComponentID),
                    "InventoryReceiptDetailID": int(issue.InventoryReceiptDetailID),
                    "SourceInventoryTransactionID": int(issue.SourceInventoryTransactionID),
                    "SupplierID": int(receipt_supplier.get(issue.InventoryReceiptDetailID, 1)),
                    "ConsumedQuantity": float(issue.IssuedQuantity),
                    "TraceabilityStatus": "Traced",
                }
            )
            genealogy_id += 1
        return pd.DataFrame(rows)

    def _generate_cost_summary(self, table: TableContract, plan: LLMGenerationPlan, generated: dict[str, pd.DataFrame], batches: pd.DataFrame, operations: pd.DataFrame, scrap_rework: pd.DataFrame, receipts: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
        req_to_line = dict(zip(generated["ProductionMaterialRequirement"]["MaterialRequirementID"], generated["ProductionMaterialRequirement"]["ProductionOrderLineID"]))
        issue_lines = generated["MaterialIssueLine"].copy()
        issue_lines["ProductionOrderLineID"] = issue_lines["MaterialRequirementID"].map(req_to_line)
        material_cost_by_line = issue_lines.groupby("ProductionOrderLineID")["IssueValue"].sum().to_dict()
        op_count_by_batch = operations.groupby("ProductionBatchID")["OperationExecutionID"].count().to_dict()
        scrap_cost_by_batch = scrap_rework.groupby("ProductionBatchID")["CostImpact"].sum().to_dict() if not scrap_rework.empty else {}
        receipt_good_by_batch = dict(zip(receipts["ProductionBatchID"], receipts["GoodQuantity"]))
        rows = []
        for index, batch in enumerate(batches.itertuples(index=False), start=1):
            material_cost = round(float(material_cost_by_line.get(batch.ProductionOrderLineID, 0.0)), 2)
            labor_cost = round(float(op_count_by_batch.get(batch.ProductionBatchID, 1)) * rng.uniform(45, 95), 2)
            overhead_cost = round((material_cost + labor_cost) * rng.uniform(0.12, 0.24), 2)
            scrap_cost = round(float(scrap_cost_by_batch.get(batch.ProductionBatchID, 0.0)), 2)
            total = round(material_cost + labor_cost + overhead_cost + scrap_cost, 2)
            good_quantity = max(float(receipt_good_by_batch.get(batch.ProductionBatchID, batch.PlannedBatchQuantity)), 1.0)
            rows.append(
                {
                    "ProductionCostSummaryID": index,
                    "ProductionOrderLineID": int(batch.ProductionOrderLineID),
                    "ProductionBatchID": int(batch.ProductionBatchID),
                    "ProductID": int(batch.ProductID),
                    "MaterialCost": material_cost,
                    "LaborCost": labor_cost,
                    "OverheadCost": overhead_cost,
                    "ScrapCost": scrap_cost,
                    "TotalProductionCost": total,
                    "UnitProductionCost": round(total / good_quantity, 2),
                }
            )
        return pd.DataFrame(rows)

    def _align_receipt_costs(self, receipts: pd.DataFrame, cost_summary: pd.DataFrame) -> None:
        unit_cost_by_batch = dict(zip(cost_summary["ProductionBatchID"], cost_summary["UnitProductionCost"]))
        receipts["UnitCost"] = receipts["ProductionBatchID"].map(unit_cost_by_batch).astype(float).round(2)
        receipts["ReceiptValue"] = (receipts["GoodQuantity"] * receipts["UnitCost"]).round(2)

    def _validate_inventory_consumption(self, material_issue_line: pd.DataFrame, inventory: pd.DataFrame, report: ValidationReport) -> None:
        issued = material_issue_line.groupby("InventoryID")["IssuedQuantity"].sum()
        available = inventory.set_index("InventoryID")["AvailableQuantity"]
        for inventory_id, issued_quantity in issued.items():
            if float(issued_quantity) > float(available.get(inventory_id, 0.0)) + 0.0001:
                report.add_error(
                    table_name="MaterialIssueLine",
                    column_name="IssuedQuantity",
                    message=f"Cumulative issued quantity exceeds Inventory.AvailableQuantity for InventoryID {inventory_id}.",
                    suggested_fix="Reduce production demand or allocate from a different available inventory bucket.",
                )

    def _validate_formula_columns(self, dataframes: dict[str, pd.DataFrame], report: ValidationReport) -> None:
        if (abs(dataframes["MaterialIssueLine"]["IssueValue"] - dataframes["MaterialIssueLine"]["IssuedQuantity"] * dataframes["MaterialIssueLine"]["UnitCost"]) > 0.011).any():
            report.add_error(table_name="MaterialIssueLine", column_name="IssueValue", message="IssueValue formula mismatch.", suggested_fix="Set IssueValue = IssuedQuantity * UnitCost.")
        if (abs(dataframes["OperationExecution"]["OutputQuantity"] - (dataframes["OperationExecution"]["InputQuantity"] - dataframes["OperationExecution"]["ScrapQuantity"])) > 0.0001).any():
            report.add_error(table_name="OperationExecution", column_name="OutputQuantity", message="OutputQuantity formula mismatch.", suggested_fix="Set OutputQuantity = InputQuantity - ScrapQuantity.")
        if (abs(dataframes["ProductionQualityResult"]["TestedQuantity"] - (dataframes["ProductionQualityResult"]["PassedQuantity"] + dataframes["ProductionQualityResult"]["FailedQuantity"])) > 0.0001).any():
            report.add_error(table_name="ProductionQualityResult", column_name="TestedQuantity", message="Quality quantity formula mismatch.", suggested_fix="Set PassedQuantity + FailedQuantity = TestedQuantity.")
        if (abs(dataframes["FinishedGoodsReceipt"]["ReceiptValue"] - dataframes["FinishedGoodsReceipt"]["GoodQuantity"] * dataframes["FinishedGoodsReceipt"]["UnitCost"]) > 0.011).any():
            report.add_error(table_name="FinishedGoodsReceipt", column_name="ReceiptValue", message="ReceiptValue formula mismatch.", suggested_fix="Set ReceiptValue = GoodQuantity * UnitCost.")
        cost = dataframes["ProductionCostSummary"]
        if (abs(cost["TotalProductionCost"] - (cost["MaterialCost"] + cost["LaborCost"] + cost["OverheadCost"] + cost["ScrapCost"])) > 0.011).any():
            report.add_error(table_name="ProductionCostSummary", column_name="TotalProductionCost", message="TotalProductionCost formula mismatch.", suggested_fix="Recalculate total production cost.")

    def _validate_2025_dates(self, dataframes: dict[str, pd.DataFrame], report: ValidationReport) -> None:
        date_columns = {
            "ProductionOrderHdr": ["OrderDate", "PlannedStartDate", "PlannedEndDate", "ActualStartDate", "ActualEndDate"],
            "MaterialIssueHeader": ["IssueDate"],
            "ProductionBatch": ["ActualStartDate", "ActualEndDate"],
            "OperationExecution": ["ActualStartDateTime", "ActualEndDateTime"],
            "ProductionQualityInspection": ["InspectionDate"],
            "ScrapReworkEvent": ["EventDate"],
            "FinishedGoodsReceipt": ["ReceiptDate"],
            "FinishedGoodsInventory": ["LastReceiptDate"],
        }
        for table_name, columns in date_columns.items():
            dataframe = dataframes[table_name]
            if dataframe.empty:
                continue
            for column in columns:
                values = pd.to_datetime(dataframe[column], errors="coerce")
                if values.isna().any() or (values.dt.date < date(2025, 1, 1)).any() or (values.dt.date > date(2025, 12, 31)).any():
                    report.add_error(table_name=table_name, column_name=column, message="Generated date is outside 2025.", suggested_fix="Keep all Production v1 dates in calendar year 2025.")

    def _validate_genealogy(self, dataframes: dict[str, pd.DataFrame], upstream: ProcurementExecutionContext, report: ValidationReport) -> None:
        genealogy = dataframes["ProductionGenealogy"]
        issue = dataframes["MaterialIssueLine"].set_index("MaterialIssueLineID")
        receipt_supplier = dict(zip(upstream.inventory_receipt_detail["InventoryReceiptDetailID"], upstream.inventory_receipt_detail["SupplierID"]))
        for row in genealogy.itertuples(index=False):
            issue_row = issue.loc[row.MaterialIssueLineID]
            if int(row.ComponentID) != int(issue_row.ComponentID) or int(row.SourceInventoryTransactionID) != int(issue_row.SourceInventoryTransactionID):
                report.add_error(table_name="ProductionGenealogy", message="Genealogy does not match MaterialIssueLine lineage.", suggested_fix="Copy component and stock source lineage from MaterialIssueLine.")
            if int(row.SupplierID) != int(receipt_supplier.get(row.InventoryReceiptDetailID, -1)):
                report.add_error(table_name="ProductionGenealogy", column_name="SupplierID", message="Genealogy SupplierID does not match InventoryReceiptDetail.SupplierID.", suggested_fix="Trace supplier from InventoryReceiptDetail.")

    def _validate_uom_precision(self, dataframes: dict[str, pd.DataFrame], master: ProductionMasterContext, upstream: ProcurementExecutionContext, report: ValidationReport) -> None:
        product_uom = dict(zip(master.product_master["ProductID"], master.product_master["UOM"]))
        for row in dataframes["ProductionOrderLine"].itertuples(index=False):
            if requires_integer_quantity(product_uom[row.ProductID]):
                for value in [row.PlannedQuantity, row.ReleasedQuantity, row.CompletedQuantity, row.GoodQuantity, row.ScrapQuantity]:
                    if not is_whole_quantity(value):
                        report.add_error(table_name="ProductionOrderLine", column_name="PlannedQuantity", message="Countable product quantity is not whole.", suggested_fix="Use integer quantities for countable finished goods.")
        component_uom = _component_uom_lookup(upstream.component_master)
        for row in dataframes["MaterialIssueLine"].itertuples(index=False):
            if requires_integer_quantity(component_uom.get(row.ComponentID, row.UOM)) and not is_whole_quantity(row.IssuedQuantity):
                report.add_error(table_name="MaterialIssueLine", column_name="IssuedQuantity", message="Countable component issue quantity is not whole.", suggested_fix="Use integer quantities for countable component issues.")


def _coerce_master_context(master_data: dict[str, pd.DataFrame] | ProductionMasterContext) -> ProductionMasterContext:
    if isinstance(master_data, ProductionMasterContext):
        return master_data
    return ProductionMasterContext(
        product_master=master_data["ProductMaster"],
        bom_header=master_data["BOMHeader"],
        bom_line=master_data["BOMLine"],
        work_center=master_data["WorkCenter"],
        routing_header=master_data["RoutingHeader"],
        routing_operation=master_data["RoutingOperation"],
        production_shift=master_data["ProductionShift"],
    )


def _fallback_upstream_context(master: ProductionMasterContext | None) -> ProcurementExecutionContext:
    component_ids = list(master.bom_line["ComponentID"].drop_duplicates()) if master is not None else [1, 2, 3]
    component_master = pd.DataFrame(
        [{"ComponentID": component_id, "ComponentName": f"Fallback Component {component_id}", "UOM": "EA"} for component_id in component_ids]
    )
    plant = pd.DataFrame([{"PlantID": 1, "PlantName": "Fallback Plant"}])
    warehouse = pd.DataFrame([{"WarehouseID": 1, "PlantID": 1, "WarehouseName": "Fallback Warehouse"}])
    inventory = pd.DataFrame(
        [
            {
                "InventoryID": index,
                "ComponentID": component_id,
                "PlantID": 1,
                "WarehouseID": 1,
                "OnHandQuantity": 100000.0,
                "ReservedQuantity": 0.0,
                "AvailableQuantity": 100000.0,
                "OnHandValue": 1000000.0,
            }
            for index, component_id in enumerate(component_ids, start=1)
        ]
    )
    inventory_transaction = pd.DataFrame(
        [
            {
                "InventoryTransactionID": index,
                "InspectionResultID": index,
                "GoodsReceiptLineID": index,
                "PurchaseOrderLineID": index,
                "SupplierID": 1,
                "ComponentID": component_id,
                "PlantID": 1,
                "WarehouseID": 1,
                "TransactionDate": "2025-01-01",
                "TransactionType": "StockIn",
                "TransactionQuantity": 100000.0,
                "UnitPrice": 10.0,
                "InventoryValue": 1000000.0,
                "ReferenceDocument": f"IRD-{index:06d}",
                "InventoryStatus": "Posted",
            }
            for index, component_id in enumerate(component_ids, start=1)
        ]
    )
    inventory_receipt_detail = pd.DataFrame(
        [
            {
                "InventoryReceiptDetailID": index,
                "InspectionResultID": index,
                "GoodsReceiptLineID": index,
                "PurchaseOrderLineID": index,
                "PurchaseOrderID": index,
                "SupplierID": 1,
                "ComponentID": component_id,
                "PlantID": 1,
                "WarehouseID": 1,
                "AcceptedQuantity": 100000.0,
                "DeliveredUnitPrice": 10.0,
            }
            for index, component_id in enumerate(component_ids, start=1)
        ]
    )
    supplier_master = pd.DataFrame([{"SupplierID": 1, "SupplierName": "Fallback Supplier"}])
    return ProcurementExecutionContext(component_master, plant, warehouse, inventory, inventory_transaction, inventory_receipt_detail, supplier_master, True)


def _component_uom_lookup(component_master: pd.DataFrame) -> dict[int, str]:
    uom_column = next((column for column in ["UOM", "UnitOfMeasure", "Unit_Of_Measure"] if column in component_master.columns), None)
    if uom_column is None:
        return {int(row.ComponentID): "EA" for row in component_master.itertuples(index=False)}
    return {int(row.ComponentID): str(getattr(row, uom_column)) for row in component_master.itertuples(index=False)}


def _weighted_choice(rng: random.Random, values: list[str], weights: list[float]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def _receipt_id_from_reference(reference: Any) -> int:
    text = str(reference or "")
    digits = "".join(character for character in text if character.isdigit())
    return int(digits) if digits else -1


def _shift_for_work_center(shifts_by_wc: dict[int, pd.DataFrame], work_center_id: int, target_date: date) -> int:
    shifts = shifts_by_wc.get(work_center_id)
    if shifts is None or shifts.empty:
        for candidate in shifts_by_wc.values():
            if not candidate.empty:
                return int(candidate.iloc[0]["ShiftID"])
        return 1
    same_date = shifts[pd.to_datetime(shifts["ShiftDate"]).dt.date == target_date]
    if not same_date.empty:
        return int(same_date.iloc[0]["ShiftID"])
    return int(shifts.iloc[0]["ShiftID"])


def format_production_transaction_generation_report(
    dataframes: dict[str, pd.DataFrame],
    report: ValidationReport,
    output_folder: str | Path | None = None,
) -> str:
    """Format Production transaction generation output for CLI usage."""

    lines = ["Production transaction data generation completed.", f"Tables generated: {len(dataframes)}"]
    for table_name in PRODUCTION_TRANSACTION_TABLES:
        if table_name in dataframes:
            lines.append(f"{table_name} rows: {len(dataframes[table_name])}")
    lines.extend([f"Validation errors: {len(report.errors)}", f"Validation warnings: {len(report.warnings)}"])
    if output_folder is not None:
        lines.append(f"Output folder: {output_folder}")
    lines.append(f"Generation status: {'passed' if report.is_valid else 'failed'}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, issue in enumerate(report.warnings, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))
    return "\n".join(lines)


def _format_issue(index: int, table_name: str | None, column_name: str | None, message: str, suggested_fix: str) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines

