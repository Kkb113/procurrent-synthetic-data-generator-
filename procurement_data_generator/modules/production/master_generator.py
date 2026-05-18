"""Production Execution module within MES context v1 master/setup data generator."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.modules.shared.quantity_precision import (
    apply_quantity_precision,
    is_whole_quantity,
    requires_integer_quantity,
)
from procurement_data_generator.modules.shared.operating_scope import (
    get_allowed_shift_codes,
    get_default_shift_code,
    get_expected_plant_count,
    get_expected_warehouse_count,
    is_allowed_shift_code,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_industry_profile_or_default


PRODUCTION_MASTER_TABLES = (
    "ProductMaster",
    "BOMHeader",
    "BOMLine",
    "WorkCenter",
    "RoutingHeader",
    "RoutingOperation",
    "ProductionShift",
)
def _fallback_components_from_profile(profile: IndustryProfile) -> tuple[tuple[int, str, str], ...]:
    return tuple(
        (int(component["ComponentID"]), str(component["ComponentName"]), str(component["UOM"]))
        for component in profile.production.fallback_components
    )


def _fallback_plants_from_profile(profile: IndustryProfile) -> tuple[tuple[int, str], ...]:
    return tuple(
        (int(plant["PlantID"]), str(plant["PlantName"]))
        for plant in profile.production.fallback_plants
    )


def _fallback_warehouses_from_profile(profile: IndustryProfile) -> tuple[tuple[int, int, str], ...]:
    return tuple(
        (int(warehouse["WarehouseID"]), int(warehouse["PlantID"]), str(warehouse["WarehouseName"]))
        for warehouse in profile.production.fallback_warehouses
    )


def _product_names_from_profile(profile: IndustryProfile) -> tuple[tuple[str, str, str, str, float, float], ...]:
    return tuple(
        (
            str(product["name"]),
            str(product["category"]),
            str(product["product_type"]),
            str(product["uom"]),
            float(product["base_cost"]),
            float(product["base_hours"]),
        )
        for product in profile.production.product_catalog
    )


def _work_center_names_from_profile(profile: IndustryProfile) -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(work_center["name"]), str(work_center["line_name"]))
        for work_center in profile.production.work_center_catalog
    )


@dataclass(frozen=True)
class UpstreamProductionContext:
    """Procurement context required by Production master/setup generation."""

    components: pd.DataFrame
    plants: pd.DataFrame
    warehouses: pd.DataFrame
    used_fallback: bool = False


class ProductionMasterDataGenerator:
    """Generate the seven Production Execution module within MES context v1 master/setup tables."""

    def __init__(
        self,
        industry_profile: IndustryProfile | None = None,
        profile_id: str | None = None,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self.operating_scope = operating_scope or DEFAULT_OPERATING_SCOPE
        self.generation_config = generation_config or GenerationConfig()
        effective_profile_id = profile_id or self.generation_config.profile_id
        self.industry_profile = industry_profile or get_industry_profile_or_default(effective_profile_id)
        self.fallback_components = _fallback_components_from_profile(self.industry_profile)
        self.fallback_plants = _fallback_plants_from_profile(self.industry_profile)
        self.fallback_warehouses = _fallback_warehouses_from_profile(self.industry_profile)
        self.product_names = _product_names_from_profile(self.industry_profile)
        self.work_center_names = _work_center_names_from_profile(self.industry_profile)
        self.operation_names = tuple(self.industry_profile.production.routing_operation_names)

    def generate_master_data(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        seed: int | None = None,
        upstream_data_folder: str | Path | None = None,
    ) -> tuple[dict[str, pd.DataFrame], ValidationReport]:
        """Generate Production v1 master/setup tables only."""

        report = ValidationReport(
            total_tables_detected=len(schema.tables),
            total_columns_detected=sum(len(table.columns) for table in schema.tables.values()),
        )
        rng = random.Random(seed)
        context = self.load_upstream_context(upstream_data_folder, report)

        product_master = self._generate_product_master(schema.tables["ProductMaster"], plan, rng)
        bom_header = self._generate_bom_header(schema.tables["BOMHeader"], plan, product_master, context.plants, rng)
        bom_line = self._generate_bom_line(schema.tables["BOMLine"], plan, bom_header, context.components, rng)
        work_center = self._generate_work_center(schema.tables["WorkCenter"], plan, context.plants, rng)
        routing_header = self._generate_routing_header(schema.tables["RoutingHeader"], plan, product_master, bom_header, context.plants, rng)
        routing_operation = self._generate_routing_operation(
            schema.tables["RoutingOperation"],
            plan,
            routing_header,
            work_center,
            rng,
        )
        production_shift = self._generate_production_shift(schema.tables["ProductionShift"], plan, work_center, rng)

        dataframes = {
            "ProductMaster": product_master,
            "BOMHeader": bom_header,
            "BOMLine": bom_line,
            "WorkCenter": work_center,
            "RoutingHeader": routing_header,
            "RoutingOperation": routing_operation,
            "ProductionShift": production_shift,
        }
        self.validate_generated_master_data(dataframes, schema, context, report)
        return dataframes, report

    def load_upstream_context(
        self,
        upstream_data_folder: str | Path | None,
        report: ValidationReport | None = None,
    ) -> UpstreamProductionContext:
        """Load Procurement context tables or deterministic fallback fixtures."""

        if upstream_data_folder is not None:
            folder = Path(upstream_data_folder)
            component_path = folder / "ComponentMaster.csv"
            plant_path = folder / "Plant.csv"
            warehouse_path = folder / "Warehouse.csv"
            if component_path.exists() and plant_path.exists() and warehouse_path.exists():
                plants = pd.read_csv(plant_path).head(get_expected_plant_count()).copy()
                warehouses = pd.read_csv(warehouse_path)
                if not plants.empty and "PlantID" in warehouses.columns and "PlantID" in plants.columns:
                    warehouses = warehouses[warehouses["PlantID"].isin(set(plants["PlantID"]))].copy()
                warehouses = warehouses.head(get_expected_warehouse_count()).copy()
                return UpstreamProductionContext(
                    components=pd.read_csv(component_path),
                    plants=plants,
                    warehouses=warehouses,
                    used_fallback=False,
                )
            if report is not None:
                report.add_warning(
                    message="Upstream Procurement context folder is missing ComponentMaster, Plant, or Warehouse CSV; using deterministic fallback context.",
                    suggested_fix="Provide a Procurement v2 final_data or master data folder with ComponentMaster.csv, Plant.csv, and Warehouse.csv.",
                )
        elif report is not None:
            report.add_warning(
                message="No upstream Procurement context was supplied; using deterministic fallback context for Production master generation.",
                suggested_fix="Pass --upstream-data pointing to Procurement v2 final_data when available.",
            )

        return UpstreamProductionContext(
            components=pd.DataFrame(self.fallback_components, columns=["ComponentID", "ComponentName", "UOM"]),
            plants=pd.DataFrame(self.fallback_plants, columns=["PlantID", "PlantName"]),
            warehouses=pd.DataFrame(self.fallback_warehouses, columns=["WarehouseID", "PlantID", "WarehouseName"]),
            used_fallback=True,
        )

    def export_master_data(self, dataframes: dict[str, pd.DataFrame], output_folder: str | Path) -> list[Path]:
        """Export generated master/setup dataframes to CSV files."""

        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        paths = []
        for table_name in PRODUCTION_MASTER_TABLES:
            dataframe = dataframes[table_name]
            path = output_path / f"{table_name}.csv"
            dataframe.to_csv(path, index=False)
            paths.append(path)
        return paths

    def get_target_rows(self, table: TableContract, plan: LLMGenerationPlan) -> int:
        """Use plan row_count_plan when present, otherwise metadata TargetRows."""

        for row_count in plan.row_count_plan:
            if row_count.table_name == table.table_name:
                return row_count.target_rows
        return table.target_rows

    def validate_generated_master_data(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        context: UpstreamProductionContext,
        report: ValidationReport,
    ) -> None:
        """Validate Phase 3 Production master/setup output."""

        if set(dataframes) != set(PRODUCTION_MASTER_TABLES):
            report.add_error(
                message="Production Phase 3 must generate exactly the seven master/setup tables.",
                suggested_fix="Do not generate Production execution tables until later phases.",
            )
        self._validate_unique(dataframes["ProductMaster"], "ProductMaster", "ProductID", report)
        self._validate_unique(dataframes["ProductMaster"], "ProductMaster", "ProductCode", report)
        self._validate_fk(dataframes["BOMHeader"], "BOMHeader", "ProductID", dataframes["ProductMaster"], "ProductID", report)
        self._validate_fk(dataframes["BOMHeader"], "BOMHeader", "PlantID", context.plants, "PlantID", report)
        self._validate_fk(dataframes["BOMLine"], "BOMLine", "BOMID", dataframes["BOMHeader"], "BOMID", report)
        self._validate_fk(dataframes["BOMLine"], "BOMLine", "ComponentID", context.components, "ComponentID", report)
        self._validate_fk(dataframes["WorkCenter"], "WorkCenter", "PlantID", context.plants, "PlantID", report)
        self._validate_fk(dataframes["RoutingHeader"], "RoutingHeader", "ProductID", dataframes["ProductMaster"], "ProductID", report)
        self._validate_fk(dataframes["RoutingHeader"], "RoutingHeader", "PlantID", context.plants, "PlantID", report)
        self._validate_fk(dataframes["RoutingOperation"], "RoutingOperation", "RoutingID", dataframes["RoutingHeader"], "RoutingID", report)
        self._validate_fk(dataframes["RoutingOperation"], "RoutingOperation", "WorkCenterID", dataframes["WorkCenter"], "WorkCenterID", report)
        self._validate_fk(dataframes["ProductionShift"], "ProductionShift", "WorkCenterID", dataframes["WorkCenter"], "WorkCenterID", report)
        self._validate_fk(dataframes["ProductionShift"], "ProductionShift", "PlantID", context.plants, "PlantID", report)
        self._validate_bom_line_uom(dataframes["BOMLine"], context.components, report)
        self._validate_shift_plants(dataframes["ProductionShift"], dataframes["WorkCenter"], report)
        self._validate_shift_codes(dataframes["ProductionShift"], report)
        self._validate_operation_sequence(dataframes["RoutingOperation"], report)
        self._validate_2025_dates(dataframes, schema, report)

    def _generate_product_master(self, table: TableContract, plan: LLMGenerationPlan, rng: random.Random) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        rows = []
        for index in range(1, count + 1):
            name, category, product_type, uom, base_cost, base_hours = self.product_names[(index - 1) % len(self.product_names)]
            variant = ((index - 1) // len(self.product_names)) + 1
            rows.append(
                {
                    "ProductID": index,
                    "ProductCode": f"PRD-{index:05d}",
                    "ProductName": name if variant == 1 else f"{name} Variant {variant}",
                    "ProductCategory": category,
                    "ProductType": product_type,
                    "UOM": uom,
                    "StandardCost": round(base_cost * rng.uniform(0.92, 1.12), 2),
                    "StandardBuildTimeHours": round(base_hours * rng.uniform(0.85, 1.2), 2),
                    "ProductStatus": "Inactive" if rng.random() < 0.05 else "Active",
                }
            )
        return pd.DataFrame(rows)

    def _generate_bom_header(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        products: pd.DataFrame,
        plants: pd.DataFrame,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        plant_ids = list(plants["PlantID"])
        rows = []
        for index in range(1, count + 1):
            product_id = int(products.iloc[(index - 1) % len(products)]["ProductID"])
            plant_id = int(plant_ids[(index - 1) % len(plant_ids)])
            effective_from = self.operating_scope.date_start + timedelta(days=rng.randint(0, 45))
            effective_to = self.operating_scope.date_end - timedelta(days=rng.randint(0, 30))
            rows.append(
                {
                    "BOMID": index,
                    "ProductID": product_id,
                    "PlantID": plant_id,
                    "BOMVersion": f"BOM-{product_id:03d}-V{((index - 1) // max(len(products), 1)) + 1}",
                    "EffectiveFromDate": effective_from.isoformat(),
                    "EffectiveToDate": max(effective_from, effective_to).isoformat(),
                    "BOMStatus": "Inactive" if rng.random() < 0.08 else "Active",
                }
            )
        return pd.DataFrame(rows)

    def _generate_bom_line(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        bom_header: pd.DataFrame,
        components: pd.DataFrame,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        component_records = components.to_dict("records")
        rows = []
        for index in range(1, count + 1):
            component = component_records[(index - 1 + rng.randrange(len(component_records))) % len(component_records)]
            uom = _component_uom(component)
            raw_quantity = rng.uniform(1, 12) if requires_integer_quantity(uom) else rng.uniform(0.05, 25)
            quantity = apply_quantity_precision(raw_quantity, uom, minimum=1 if requires_integer_quantity(uom) else 0.01)
            rows.append(
                {
                    "BOMLineID": index,
                    "BOMID": int(bom_header.iloc[(index - 1) % len(bom_header)]["BOMID"]),
                    "ComponentID": int(component["ComponentID"]),
                    "ComponentQuantity": quantity,
                    "UOM": uom,
                    "ScrapFactorPct": round(rng.uniform(0, 3), 2),
                    "IsCriticalComponent": 1 if rng.random() < 0.25 else 0,
                    "BOMLineStatus": "Inactive" if rng.random() < 0.05 else "Active",
                }
            )
        return pd.DataFrame(rows)

    def _generate_work_center(self, table: TableContract, plan: LLMGenerationPlan, plants: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        plant_ids = list(plants["PlantID"])
        rows = []
        for index in range(1, count + 1):
            name, line_name = self.work_center_names[(index - 1) % len(self.work_center_names)]
            plant_id = int(plant_ids[(index - 1) % len(plant_ids)])
            rows.append(
                {
                    "WorkCenterID": index,
                    "PlantID": plant_id,
                    "WorkCenterCode": f"WC-{plant_id:02d}-{index:04d}",
                    "WorkCenterName": name if index <= len(self.work_center_names) else f"{name} {((index - 1) // len(self.work_center_names)) + 1}",
                    "LineName": line_name,
                    "CapacityPerShift": round(rng.uniform(40, 450), 2),
                    "CapacityUOM": "EA",
                    "WorkCenterStatus": "Maintenance" if rng.random() < 0.04 else ("Inactive" if rng.random() < 0.04 else "Active"),
                }
            )
        return pd.DataFrame(rows)

    def _generate_routing_header(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        products: pd.DataFrame,
        bom_header: pd.DataFrame,
        plants: pd.DataFrame,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        bom_by_product = bom_header.groupby("ProductID")["PlantID"].first().to_dict()
        plant_ids = list(plants["PlantID"])
        rows = []
        for index in range(1, count + 1):
            product_id = int(products.iloc[(index - 1) % len(products)]["ProductID"])
            rows.append(
                {
                    "RoutingID": index,
                    "ProductID": product_id,
                    "PlantID": int(bom_by_product.get(product_id, plant_ids[(index - 1) % len(plant_ids)])),
                    "RoutingVersion": f"RTG-{product_id:03d}-V{((index - 1) // max(len(products), 1)) + 1}",
                    "RoutingStatus": "Inactive" if rng.random() < 0.06 else "Active",
                }
            )
        return pd.DataFrame(rows)

    def _generate_routing_operation(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        routing_header: pd.DataFrame,
        work_centers: pd.DataFrame,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        work_centers_by_plant = {plant_id: rows for plant_id, rows in work_centers.groupby("PlantID")}
        rows = []
        sequence_by_routing: dict[int, int] = {}
        for index in range(1, count + 1):
            routing = routing_header.iloc[(index - 1) % len(routing_header)]
            routing_id = int(routing["RoutingID"])
            plant_work_centers = work_centers_by_plant.get(routing["PlantID"], work_centers)
            work_center = plant_work_centers.iloc[(sequence_by_routing.get(routing_id, 0)) % len(plant_work_centers)]
            sequence_by_routing[routing_id] = sequence_by_routing.get(routing_id, 0) + 10
            operation_index = (sequence_by_routing[routing_id] // 10 - 1) % len(self.operation_names)
            rows.append(
                {
                    "RoutingOperationID": index,
                    "RoutingID": routing_id,
                    "WorkCenterID": int(work_center["WorkCenterID"]),
                    "OperationSequence": sequence_by_routing[routing_id],
                    "OperationName": self.operation_names[operation_index],
                    "SetupTimeMinutes": round(rng.uniform(10, 120), 2),
                    "RunTimeMinutesPerUnit": round(rng.uniform(0.5, 18), 2),
                    "StandardYieldPct": round(rng.uniform(95, 100), 2),
                    "OperationStatus": "Inactive" if rng.random() < 0.04 else "Active",
                }
            )
        return pd.DataFrame(rows)

    def _generate_production_shift(self, table: TableContract, plan: LLMGenerationPlan, work_centers: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        shift_code = get_default_shift_code()
        rows = []
        for index in range(1, count + 1):
            work_center = work_centers.iloc[(index - 1) % len(work_centers)]
            shift_date = self.operating_scope.date_start + timedelta(days=(index - 1) % 365)
            rows.append(
                {
                    "ShiftID": index,
                    "PlantID": int(work_center["PlantID"]),
                    "WorkCenterID": int(work_center["WorkCenterID"]),
                    "ShiftDate": shift_date.isoformat(),
                    "ShiftCode": shift_code,
                    "ShiftStartTime": "08:00",
                    "ShiftEndTime": "16:00",
                    "PlannedHours": 8.0 if rng.random() > 0.03 else 10.0,
                }
            )
        return pd.DataFrame(rows)

    def _validate_unique(self, dataframe: pd.DataFrame, table_name: str, column_name: str, report: ValidationReport) -> None:
        if dataframe[column_name].duplicated().any():
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message="Generated column contains duplicate values.",
                suggested_fix="Generate unique values for this key/business key column.",
            )

    def _validate_fk(
        self,
        child: pd.DataFrame,
        child_table: str,
        child_column: str,
        parent: pd.DataFrame,
        parent_column: str,
        report: ValidationReport,
    ) -> None:
        invalid = set(child[child_column].dropna()) - set(parent[parent_column].dropna())
        if invalid:
            report.add_error(
                table_name=child_table,
                column_name=child_column,
                message=f"FK values do not exist in parent table: {sorted(invalid)[:5]}.",
                suggested_fix="Generate FK values from parent keys only.",
            )

    def _validate_bom_line_uom(self, bom_line: pd.DataFrame, components: pd.DataFrame, report: ValidationReport) -> None:
        component_uom = {row.ComponentID: _component_uom(row._asdict()) for row in components.itertuples(index=False)}
        for row in bom_line.itertuples(index=False):
            expected_uom = component_uom.get(row.ComponentID)
            if row.UOM != expected_uom:
                report.add_error(
                    table_name="BOMLine",
                    column_name="UOM",
                    message="BOMLine.UOM does not match ComponentMaster.UOM.",
                    suggested_fix="Copy BOMLine.UOM from the referenced component.",
                )
            if expected_uom and requires_integer_quantity(expected_uom) and not is_whole_quantity(row.ComponentQuantity):
                report.add_error(
                    table_name="BOMLine",
                    column_name="ComponentQuantity",
                    message="Countable component BOM quantity is not a whole number.",
                    suggested_fix="Apply shared UOM-aware quantity precision to BOMLine.ComponentQuantity.",
                )

    def _validate_shift_plants(self, production_shift: pd.DataFrame, work_centers: pd.DataFrame, report: ValidationReport) -> None:
        work_center_plants = dict(zip(work_centers["WorkCenterID"], work_centers["PlantID"]))
        mismatches = [
            row.ShiftID
            for row in production_shift.itertuples(index=False)
            if work_center_plants.get(row.WorkCenterID) != row.PlantID
        ]
        if mismatches:
            report.add_error(
                table_name="ProductionShift",
                column_name="PlantID",
                message=f"ProductionShift.PlantID does not match WorkCenter.PlantID for rows: {mismatches[:5]}.",
                suggested_fix="Set ProductionShift.PlantID from the referenced WorkCenter.",
            )

    def _validate_shift_codes(self, production_shift: pd.DataFrame, report: ValidationReport) -> None:
        invalid = sorted({str(value) for value in production_shift["ShiftCode"].dropna() if not is_allowed_shift_code(str(value))})
        if invalid:
            report.add_error(
                table_name="ProductionShift",
                column_name="ShiftCode",
                message=f"ProductionShift contains shift codes outside {get_allowed_shift_codes()}: {invalid}.",
                suggested_fix="Generate only the shared operating scope shift codes.",
            )

    def _validate_operation_sequence(self, routing_operation: pd.DataFrame, report: ValidationReport) -> None:
        for routing_id, rows in routing_operation.groupby("RoutingID"):
            sequences = list(rows.sort_values("OperationSequence")["OperationSequence"])
            if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
                report.add_error(
                    table_name="RoutingOperation",
                    column_name="OperationSequence",
                    message=f"OperationSequence is not ordered and unique for RoutingID {routing_id}.",
                    suggested_fix="Generate monotonic operation sequence values per routing.",
                )

    def _validate_2025_dates(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract, report: ValidationReport) -> None:
        for table_name, dataframe in dataframes.items():
            table = schema.tables[table_name]
            for column in table.columns:
                if not column.data_type.lower().startswith("date"):
                    continue
                values = pd.to_datetime(dataframe[column.column_name], errors="coerce")
                if values.isna().any() or (values.dt.date < self.operating_scope.date_start).any() or (values.dt.date > self.operating_scope.date_end).any():
                    report.add_error(
                        table_name=table_name,
                        column_name=column.column_name,
                        message=f"Generated date is outside the {self.operating_scope.calendar_year} Production v1 scope.",
                        suggested_fix=f"Generate all Production v1 dates between {self.operating_scope.date_start.isoformat()} and {self.operating_scope.date_end.isoformat()}.",
                    )


def _component_uom(component: dict[str, Any]) -> str:
    for column_name in ("UOM", "UnitOfMeasure", "Unit_Of_Measure"):
        if column_name in component and pd.notna(component[column_name]):
            return str(component[column_name])
    return "EA"


def format_production_master_generation_report(
    dataframes: dict[str, pd.DataFrame],
    report: ValidationReport,
    output_folder: str | Path | None = None,
) -> str:
    """Format Production master generation output for CLI usage."""

    lines = ["Production master data generation completed.", f"Tables generated: {len(dataframes)}"]
    for table_name in PRODUCTION_MASTER_TABLES:
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

