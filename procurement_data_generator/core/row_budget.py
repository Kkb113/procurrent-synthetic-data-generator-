"""Row budget planning for analytics-scale lifecycle generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract


SCALABLE_CLASSIFICATIONS = {
    "transaction_header",
    "transaction_detail",
    "ledger_event",
}
ANALYTICS_SCALE_MIN_ROWS = 300_000
ANALYTICS_LIFECYCLE_RESERVE_FACTOR = 1.04
NATURALLY_DERIVED_CLASSIFICATIONS = {
    "balance_snapshot",
    "derived",
}
NOT_SCALED_CLASSIFICATIONS = {
    "dimension_master",
    "bridge_reference",
}


@dataclass(frozen=True)
class RowBudgetTablePlan:
    """Planned target for one table."""

    module_id: str
    table_name: str
    table_role: str
    area: str
    classification: str
    metadata_target: int
    planned_target: int
    scaled_target: int
    scale_applied: bool
    capped: bool
    notes: str


@dataclass(frozen=True)
class RowBudgetPlan:
    """Full run row-budget plan."""

    requested_target_total_rows: int | None
    base_metadata_total_rows: int
    planned_total_rows: int
    applied_row_scale_factor: float
    tables: tuple[RowBudgetTablePlan, ...]

    @property
    def planned_row_targets(self) -> dict[str, int]:
        return {table.table_name: table.planned_target for table in self.tables}

    def module_targets(self, module_id: str) -> dict[str, int]:
        return {
            table.table_name: table.planned_target
            for table in self.tables
            if table.module_id == module_id
        }

    def to_report(self, actual_counts: Mapping[str, Mapping[str, int]] | None = None) -> dict[str, Any]:
        actual_counts = actual_counts or {}
        actual_total = 0
        modules: dict[str, dict[str, Any]] = {}
        flat_tables: dict[str, dict[str, Any]] = {}
        not_scaled: list[str] = []
        naturally_derived: list[str] = []

        for table in self.tables:
            module_actuals = actual_counts.get(table.module_id, {})
            actual_rows = module_actuals.get(table.table_name)
            if actual_rows is not None:
                actual_total += int(actual_rows)
            table_payload = _table_report_payload(table, actual_rows)
            modules.setdefault(
                table.module_id,
                {
                    "module_id": table.module_id,
                    "metadata_target_rows": 0,
                    "planned_target_rows": 0,
                    "actual_rows": 0,
                    "tables": [],
                },
            )
            modules[table.module_id]["metadata_target_rows"] += table.metadata_target
            modules[table.module_id]["planned_target_rows"] += table.planned_target
            modules[table.module_id]["actual_rows"] += int(actual_rows or 0)
            modules[table.module_id]["tables"].append(table_payload)
            key = table.table_name if table.table_name not in flat_tables else f"{table.module_id}.{table.table_name}"
            flat_tables[key] = table_payload
            if table.classification in NOT_SCALED_CLASSIFICATIONS:
                not_scaled.append(key)
            if table.classification in NATURALLY_DERIVED_CLASSIFICATIONS:
                naturally_derived.append(key)

        for module in modules.values():
            module["delta_rows"] = module["actual_rows"] - module["planned_target_rows"]

        return {
            "report_type": "row_budget_report",
            "requested_target_total_rows": self.requested_target_total_rows,
            "base_metadata_total_rows": self.base_metadata_total_rows,
            "planned_total_rows": self.planned_total_rows,
            "actual_total_rows": actual_total,
            "applied_row_scale_factor": round(self.applied_row_scale_factor, 6),
            "tolerance_pct": 15,
            "modules": list(modules.values()),
            "tables": flat_tables,
            "not_scaled_tables": not_scaled,
            "naturally_derived_tables": naturally_derived,
        }

    def write_report(
        self,
        output_folder: str | Path,
        actual_counts: Mapping[str, Mapping[str, int]] | None = None,
    ) -> Path:
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "row_budget_report.json"
        report_path.write_text(json.dumps(self.to_report(actual_counts), indent=2, default=str), encoding="utf-8")
        return report_path


class RowBudgetPlanner:
    """Plan table-level row budgets from metadata and runtime scale settings."""

    def plan_modules(
        self,
        module_schemas: Mapping[str, SchemaContract],
        config: GenerationConfig,
    ) -> RowBudgetPlan:
        candidates = [
            _candidate(module_id, table)
            for module_id, schema in module_schemas.items()
            for table in schema.ordered_tables
        ]
        base_total = sum(candidate["metadata_target"] for candidate in candidates)
        fixed_total = sum(
            candidate["metadata_target"]
            for candidate in candidates
            if candidate["classification"] not in SCALABLE_CLASSIFICATIONS
        )
        scalable_total = sum(
            candidate["metadata_target"]
            for candidate in candidates
            if candidate["classification"] in SCALABLE_CLASSIFICATIONS
        )
        applied_scale = _applied_scale_factor(config, fixed_total, scalable_total)

        table_plans = []
        for candidate in candidates:
            metadata_target = candidate["metadata_target"]
            classification = candidate["classification"]
            if classification in SCALABLE_CLASSIFICATIONS:
                scaled_target = max(1, int(round(metadata_target * applied_scale)))
                note = "Scaled from metadata TargetRows."
                scale_applied = applied_scale != 1.0
            else:
                scaled_target = metadata_target
                scale_applied = False
                note = _non_scaled_note(classification)

            planned_target = scaled_target
            capped = False
            if config.max_rows_per_table is not None and planned_target > config.max_rows_per_table:
                planned_target = config.max_rows_per_table
                capped = True
                note = f"{note} Capped by max_rows_per_table."

            table_plans.append(
                RowBudgetTablePlan(
                    module_id=candidate["module_id"],
                    table_name=candidate["table_name"],
                    table_role=candidate["table_role"],
                    area=candidate["area"],
                    classification=classification,
                    metadata_target=metadata_target,
                    planned_target=planned_target,
                    scaled_target=scaled_target,
                    scale_applied=scale_applied,
                    capped=capped,
                    notes=note,
                )
            )

        return RowBudgetPlan(
            requested_target_total_rows=config.target_total_rows,
            base_metadata_total_rows=base_total,
            planned_total_rows=sum(table.planned_target for table in table_plans),
            applied_row_scale_factor=applied_scale,
            tables=tuple(table_plans),
        )


def planned_target_rows(config: GenerationConfig | None, table_name: str, default: int) -> int:
    """Resolve planned table target rows with safe fallback."""

    if config is not None and config.planned_row_targets:
        target = config.planned_row_targets.get(table_name)
        if target is not None:
            return int(target)
    return int(default)


def _candidate(module_id: str, table: TableContract) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "table_name": table.table_name,
        "table_role": table.table_role,
        "area": table.area,
        "classification": classify_table(table),
        "metadata_target": int(table.target_rows),
    }


def classify_table(table: TableContract) -> str:
    """Classify tables for row scaling using deterministic metadata hints."""

    name = table.table_name.lower()
    role = table.table_role.lower()
    area = table.area.lower()
    combined = f"{name} {role} {area}"

    if name in {"inventory", "finishedgoodsinventory"} or "balance" in combined or "snapshot" in combined:
        return "balance_snapshot"
    if any(term in combined for term in ("traceability", "genealogy", "costsummary", "scraprework", "return")):
        return "derived"
    if any(term in role for term in ("master", "dimension")) or area == "master":
        if any(term in role for term in ("supplier_component", "bom_line")) or role.endswith("_line"):
            return "bridge_reference"
        return "dimension_master"
    if any(term in name for term in ("header", "hdr")):
        return "transaction_header"
    if any(term in name for term in ("line", "ln", "detail", "requirement", "operation", "result")):
        return "transaction_detail"
    if any(term in combined for term in ("invoice", "payment", "receipt", "shipment", "inspection", "reservation", "picklist", "batch", "issue", "transaction", "schedule", "quotation", "rfq", "order")):
        return "ledger_event"
    return "transaction_detail"


def _applied_scale_factor(config: GenerationConfig, fixed_total: int, scalable_total: int) -> float:
    if config.target_total_rows is not None and scalable_total > 0:
        requested_total = config.target_total_rows
        if requested_total >= ANALYTICS_SCALE_MIN_ROWS:
            requested_total = int(round(requested_total * ANALYTICS_LIFECYCLE_RESERVE_FACTOR))
        requested_scalable_total = max(1, requested_total - fixed_total)
        return max(1.0, requested_scalable_total / scalable_total)
    return float(config.row_scale_factor)


def _non_scaled_note(classification: str) -> str:
    if classification == "balance_snapshot":
        return "Naturally derived from lifecycle facts; not blindly scaled."
    if classification == "derived":
        return "Derived from lifecycle events; target is advisory."
    return "Dimension/master/reference table; not scaled by analytics row factor."


def _table_report_payload(table: RowBudgetTablePlan, actual_rows: int | None) -> dict[str, Any]:
    if actual_rows is None:
        status = "missing"
        delta_rows = -table.planned_target
        notes = table.notes
    else:
        actual_rows = int(actual_rows)
        delta_rows = actual_rows - table.planned_target
        status = _status_for_table(table, actual_rows)
        notes = table.notes
        if status == "below_target" and table.classification in SCALABLE_CLASSIFICATIONS:
            notes = f"{notes} {_below_target_reason(table)}"
    return {
        "module_id": table.module_id,
        "table_name": table.table_name,
        "table_role": table.table_role,
        "area": table.area,
        "classification": table.classification,
        "metadata_target": table.metadata_target,
        "planned_target": table.planned_target,
        "actual_rows": actual_rows,
        "delta_rows": delta_rows,
        "status": status,
        "notes": notes,
    }


def _status_for_table(table: RowBudgetTablePlan, actual_rows: int) -> str:
    if table.capped:
        return "intentionally_capped"
    if table.classification == "balance_snapshot":
        return "naturally_derived"
    if table.classification == "derived":
        return "naturally_derived"
    if table.classification in NOT_SCALED_CLASSIFICATIONS and not table.scale_applied:
        return "not_scaled"
    if actual_rows == table.planned_target:
        return "matched"
    tolerance = max(1, int(round(table.planned_target * 0.15)))
    if abs(actual_rows - table.planned_target) <= tolerance:
        return "within_tolerance"
    if actual_rows < table.planned_target:
        return "below_target"
    return "above_target"


def _below_target_reason(table: RowBudgetTablePlan) -> str:
    if table.module_id == "production":
        return "Actual rows are below planned target; reason=limited_by_raw_material_inventory."
    if table.module_id == "sales":
        return "Actual rows are below planned target; reason=limited_by_finished_goods_inventory."
    if table.module_id == "procurement":
        return "Actual rows are below planned target; reason=lifecycle_parent_child_ratio."
    return "Actual rows are below planned target; reason=lifecycle_constrained."
