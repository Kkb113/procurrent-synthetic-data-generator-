"""Runtime generation configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class GenerationConfig:
    """Small runtime configuration object for generation runs."""

    seed: int = 42
    output_dir: Path | None = None
    allow_demo_fallback: bool = False
    run_name: str | None = None
    profile_id: str | None = None
    row_scale_factor: float = 1.0
    target_total_rows: int | None = None
    max_rows_per_table: int | None = None
    max_production_orders: int | None = None
    max_production_requirements: int | None = None
    limit_sales_orders_by_customer: bool = False
    sales_orders_per_customer_cap: int = 50
    profile_file: Path | None = None
    planned_row_targets: Mapping[str, int] | None = None
    use_local_scenario_planner: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer.")
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        if not isinstance(self.limit_sales_orders_by_customer, bool):
            raise ValueError("limit_sales_orders_by_customer must be a boolean.")
        if not isinstance(self.use_local_scenario_planner, bool):
            raise ValueError("use_local_scenario_planner must be a boolean.")
        row_scale_factor = self.row_scale_factor
        if isinstance(row_scale_factor, bool) or not isinstance(row_scale_factor, (int, float)) or float(row_scale_factor) <= 0:
            raise ValueError("row_scale_factor must be a positive number.")
        object.__setattr__(self, "row_scale_factor", float(row_scale_factor))
        _validate_optional_positive_int(self.target_total_rows, "target_total_rows")
        _validate_optional_positive_int(self.max_rows_per_table, "max_rows_per_table")
        _validate_optional_positive_int(self.max_production_orders, "max_production_orders")
        _validate_optional_positive_int(self.max_production_requirements, "max_production_requirements")
        if isinstance(self.sales_orders_per_customer_cap, bool) or not isinstance(self.sales_orders_per_customer_cap, int) or self.sales_orders_per_customer_cap <= 0:
            raise ValueError("sales_orders_per_customer_cap must be a positive integer.")
        if self.profile_file is not None:
            object.__setattr__(self, "profile_file", Path(self.profile_file))
        if self.planned_row_targets is not None:
            planned_targets = {}
            for table_name, target_rows in self.planned_row_targets.items():
                if isinstance(target_rows, bool) or not isinstance(target_rows, int) or target_rows <= 0:
                    raise ValueError("planned_row_targets values must be positive integers.")
                normalized_table = str(table_name).strip()
                if not normalized_table:
                    raise ValueError("planned_row_targets keys must not be blank.")
                planned_targets[normalized_table] = target_rows
            object.__setattr__(self, "planned_row_targets", planned_targets)
        if self.run_name is not None:
            run_name = str(self.run_name).strip()
            if not run_name:
                raise ValueError("run_name must not be blank when provided.")
            object.__setattr__(self, "run_name", run_name)
        if self.profile_id is not None:
            profile_id = str(self.profile_id).strip()
            object.__setattr__(self, "profile_id", profile_id or None)


def _validate_optional_positive_int(value: int | None, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer when provided.")
