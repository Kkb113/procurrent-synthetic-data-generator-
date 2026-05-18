"""Sales module plugin adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.contracts.data_quality_report import DataQualityReport
from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.metadata.metadata_reader import read_metadata_schema
from procurement_data_generator.core.modules.contracts import PromptSection, UpstreamRequirement
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import SQLServerLoader, save_sql_load_report
from procurement_data_generator.modules.sales.master_generator import SALES_MASTER_TABLES, SalesMasterDataGenerator
from procurement_data_generator.modules.sales.prompt_sections import get_sales_prompt_sections
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES, get_sales_role_catalog
from procurement_data_generator.modules.sales.role_validator import validate_sales_roles
from procurement_data_generator.modules.sales.transaction_generator import (
    SALES_PHASE4_TRANSACTION_TABLES,
    SALES_PHASE5_TRANSACTION_TABLES,
    SALES_PHASE6_TRANSACTION_TABLES,
    SALES_PHASE7_TRANSACTION_TABLES,
    SalesTransactionGenerator,
)
from procurement_data_generator.modules.sales.validation_rules import SalesDataQualityEngine, get_sales_validation_rules


SQLLoaderFactory = Callable[[DatabaseConfig], SQLServerLoader]
SALES_REQUIRES_UPSTREAM_CHAIN = (
    "Sales requires upstream Procurement and Production data. "
    "Run modules=['procurement','production','sales']."
)
SALES_EXECUTION_NOT_IMPLEMENTED = SALES_REQUIRES_UPSTREAM_CHAIN


@dataclass(frozen=True)
class SalesPipelineRunResult:
    """Result summary for a Sales module run through the generic backend."""

    run_id: str
    status: str
    seed: int | None
    upstream_data_paths: dict[str, str]
    generated_table_count: int
    row_counts_by_table: dict[str, int]
    validation_status: str
    validation_error_count: int
    validation_warning_count: int
    output_folders: dict[str, str]
    final_data_csv_count: int
    adjusted_finished_goods_inventory_path: str | None
    notes: list[str]
    errors: list[str]
    warnings: list[str]
    validation_report: DataQualityReport | None = None
    sql_load_status: str = "not_run"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "seed": self.seed,
            "upstream_data_paths": self.upstream_data_paths,
            "generated_table_count": self.generated_table_count,
            "row_counts_by_table": self.row_counts_by_table,
            "validation_status": self.validation_status,
            "validation_error_count": self.validation_error_count,
            "validation_warning_count": self.validation_warning_count,
            "output_folders": self.output_folders,
            "final_data_csv_count": self.final_data_csv_count,
            "adjusted_finished_goods_inventory_path": self.adjusted_finished_goods_inventory_path,
            "notes": self.notes,
            "errors": self.errors,
            "warnings": self.warnings,
            "sql_load_status": self.sql_load_status,
            "validation_report": self.validation_report.to_dict() if self.validation_report is not None else None,
        }


class SalesModulePlugin:
    """Registered Sales / Order-to-Cash module boundary."""

    module_id = "sales"
    module_name = "Sales"
    module_version = "v1"

    @property
    def supported_table_roles(self) -> tuple[str, ...]:
        return tuple(self.get_role_catalog())

    def get_role_catalog(self):
        return get_sales_role_catalog(self.module_version)

    def validate_roles(
        self,
        schema: SchemaContract,
        report: ValidationReport | None = None,
        model_version: str | None = None,
    ):
        return validate_sales_roles(schema, report=report, model_version=model_version or self.module_version)

    def get_prompt_sections(
        self,
        schema: SchemaContract | None = None,
        relationships: Sequence[RelationshipContract] | None = None,
        scenario: str | None = None,
    ) -> tuple[PromptSection, ...]:
        return get_sales_prompt_sections(schema=schema, relationships=relationships, scenario=scenario)

    def validate_plan(
        self,
        plan: LLMGenerationPlan,
        schema: SchemaContract,
        relationships: Sequence[RelationshipContract],
    ):
        raise NotImplementedError("Sales plan validation is not implemented yet.")

    def create_master_generator(self, **kwargs: Any) -> SalesMasterDataGenerator:
        return SalesMasterDataGenerator(**kwargs)

    def create_transaction_generator(self, **kwargs: Any) -> SalesTransactionGenerator:
        return SalesTransactionGenerator(**kwargs)

    def create_data_quality_engine(self) -> SalesDataQualityEngine:
        return SalesDataQualityEngine()

    def get_validation_rules(self) -> tuple[str, ...]:
        return get_sales_validation_rules()

    def run_pipeline(self, **kwargs: Any) -> SalesPipelineRunResult:
        """Run Sales v1 generation, validation, and CSV artifact export."""

        output_folder = kwargs.get("output_folder")
        upstream_data_paths = kwargs.get("upstream_data_paths")
        upstream_data = kwargs.get("upstream_data")
        seed = kwargs.get("seed")
        operating_scope = _coerce_operating_scope(kwargs.get("operating_scope"))
        generation_config = _coerce_generation_config(kwargs.get("generation_config"), seed)
        run_id = str(kwargs.get("run_id") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}")
        metadata_path = kwargs.get("metadata_path")
        load_sql = bool(kwargs.get("load_sql", False))
        allow_unvalidated_sql_load = bool(kwargs.get("allow_unvalidated_sql_load", False))
        if_table_exists = str(kwargs.get("if_table_exists") or "replace")
        sql_loader_factory = kwargs.get("sql_loader_factory")

        if output_folder is None:
            raise ValueError("Sales pipeline execution requires output_folder.")

        upstream = (
            _validate_upstream_data_mapping(upstream_data, self.get_upstream_requirements())
            if upstream_data is not None
            else _load_required_upstream_data(upstream_data_paths, self.get_upstream_requirements())
        )
        upstream_paths = _stringify_upstream_paths(upstream_data_paths)

        output_root = Path(output_folder)
        run_folder = output_root / run_id
        master_folder = run_folder / "master_data"
        transaction_folder = run_folder / "transaction_data"
        final_folder = run_folder / "final_data"
        artifacts_folder = run_folder / "artifacts"
        reports_folder = run_folder / "reports"
        for folder in (master_folder, transaction_folder, final_folder, artifacts_folder, reports_folder):
            folder.mkdir(parents=True, exist_ok=True)

        master_generator = self.create_master_generator(
            operating_scope=operating_scope,
            generation_config=generation_config,
        )
        sales_master_data = master_generator.generate_master_data(seed=seed, upstream_data=upstream)

        transaction_generator = self.create_transaction_generator(
            sales_master_data=sales_master_data,
            upstream_data=upstream,
            operating_scope=operating_scope,
            generation_config=generation_config,
        )
        phase4 = transaction_generator.generate_transaction_data(seed=seed)
        phase5 = transaction_generator.generate_invoice_payment_data(
            seed=seed,
            sales_master_data=sales_master_data,
            sales_transaction_data=phase4,
        )
        phase6 = transaction_generator.generate_returns_data(
            seed=seed,
            sales_master_data=sales_master_data,
            sales_transaction_data={**phase4, **phase5},
        )
        phase7 = transaction_generator.generate_shipment_traceability_data(
            sales_transaction_data={**phase4, **phase5, **phase6},
            upstream_data=upstream,
        )
        sales_data = {**sales_master_data, **phase4, **phase5, **phase6, **phase7}
        _validate_sales_table_contract(sales_data)

        adjusted_inventory = transaction_generator.update_finished_goods_inventory_after_sales(
            upstream_data=upstream,
            sales_transaction_data={**phase4, **phase5, **phase6},
        )

        validation_report = self.create_data_quality_engine().validate_dataset(
            sales_data=sales_data,
            upstream_data=upstream,
            adjusted_finished_goods_inventory=adjusted_inventory,
            profile_id=generation_config.profile_id,
        )

        _write_dataframes(master_folder, sales_master_data, SALES_MASTER_TABLES)
        _write_dataframes(
            transaction_folder,
            {**phase4, **phase5, **phase6, **phase7},
            SALES_PHASE4_TRANSACTION_TABLES
            + SALES_PHASE5_TRANSACTION_TABLES
            + SALES_PHASE6_TRANSACTION_TABLES
            + SALES_PHASE7_TRANSACTION_TABLES,
        )
        _write_dataframes(final_folder, sales_data, SALES_V1_EXPECTED_TABLES)
        adjusted_inventory_path = artifacts_folder / "FinishedGoodsInventory.csv"
        adjusted_inventory.to_csv(adjusted_inventory_path, index=False)

        row_counts = {table_name: int(len(sales_data[table_name])) for table_name in SALES_V1_EXPECTED_TABLES}
        errors = [issue.message for issue in validation_report.errors]
        warnings = [issue.message for issue in validation_report.warnings]
        status = validation_report.overall_status
        validation_report_path = _write_validation_report(validation_report, reports_folder)
        sql_load_status = "not_run"
        if load_sql:
            sql_load_status, sql_warnings, sql_errors = _run_sql_load(
                sales_data=sales_data,
                metadata_path=metadata_path,
                validation_report_path=validation_report_path,
                allow_unvalidated_sql_load=allow_unvalidated_sql_load,
                if_table_exists=if_table_exists,
                reports_folder=reports_folder,
                sql_loader_factory=sql_loader_factory,
            )
            warnings.extend(sql_warnings)
            errors.extend(sql_errors)
            if sql_errors:
                status = "failed"
            elif status == "passed" and sql_warnings:
                status = "passed_with_warnings"
        result = SalesPipelineRunResult(
            run_id=run_id,
            status=status,
            seed=generation_config.seed,
            upstream_data_paths=upstream_paths,
            generated_table_count=len(row_counts),
            row_counts_by_table=row_counts,
            validation_status=validation_report.overall_status,
            validation_error_count=validation_report.error_count,
            validation_warning_count=validation_report.warning_count,
            output_folders={
                "run": str(run_folder),
                "master_data": str(master_folder),
                "transaction_data": str(transaction_folder),
                "final_data": str(final_folder),
                "artifacts": str(artifacts_folder),
                "reports": str(reports_folder),
            },
            final_data_csv_count=len(list(final_folder.glob("*.csv"))),
            adjusted_finished_goods_inventory_path=str(adjusted_inventory_path),
            notes=[
                "Sales v1 generated through Order-to-Cash and shipment traceability.",
                "Sales-adjusted FinishedGoodsInventory is exported as an artifact, not counted as a Sales table.",
            ],
            errors=errors,
            warnings=warnings,
            validation_report=validation_report,
            sql_load_status=sql_load_status,
        )
        _write_pipeline_reports(result, reports_folder)
        return result

    def get_upstream_requirements(self) -> tuple[UpstreamRequirement, ...]:
        return (
            UpstreamRequirement(
                module_id="production",
                table_names=(
                    "ProductMaster",
                    "FinishedGoodsInventory",
                    "FinishedGoodsReceipt",
                    "ProductionBatch",
                    "ProductionGenealogy",
                    "ProductionCostSummary",
                    "MaterialIssueLine",
                ),
                required=True,
                description="Sales v1 starts from Production finished goods inventory and traceability outputs.",
            ),
            UpstreamRequirement(
                module_id="procurement",
                table_names=(
                    "SupplierMaster",
                    "ComponentMaster",
                    "InventoryReceiptDetail",
                    "InventoryTransaction",
                ),
                required=True,
                description="Sales v1 traceability follows Production genealogy back to Procurement suppliers and components.",
            ),
        )


def _coerce_operating_scope(value: OperatingScope | None) -> OperatingScope:
    return value or DEFAULT_OPERATING_SCOPE


def _coerce_generation_config(value: GenerationConfig | None, seed: int | None) -> GenerationConfig:
    if value is None:
        return GenerationConfig(seed=seed if seed is not None else 42)
    if seed is not None and value.seed != seed:
        return GenerationConfig(
            seed=seed,
            output_dir=value.output_dir,
            allow_demo_fallback=value.allow_demo_fallback,
            run_name=value.run_name,
            profile_id=value.profile_id,
        )
    return value


def _load_required_upstream_data(
    upstream_data_paths: Any,
    requirements: tuple[UpstreamRequirement, ...],
) -> dict[str, pd.DataFrame]:
    if not isinstance(upstream_data_paths, dict):
        raise ValueError(SALES_REQUIRES_UPSTREAM_CHAIN)
    dataframes: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for requirement in requirements:
        module_path_value = upstream_data_paths.get(requirement.module_id)
        if not module_path_value:
            missing.append(requirement.module_id)
            continue
        module_path = Path(module_path_value)
        for table_name in requirement.table_names:
            csv_path = module_path / f"{table_name}.csv"
            if not csv_path.exists():
                missing.append(f"{requirement.module_id}.{table_name}")
                continue
            dataframes[table_name] = pd.read_csv(csv_path)
    if missing:
        raise ValueError(
            SALES_REQUIRES_UPSTREAM_CHAIN
            + " Missing required upstream data: "
            + ", ".join(sorted(missing))
            + "."
        )
    return dataframes


def _validate_upstream_data_mapping(
    upstream_data: Any,
    requirements: tuple[UpstreamRequirement, ...],
) -> dict[str, pd.DataFrame]:
    if not isinstance(upstream_data, dict):
        raise ValueError(SALES_REQUIRES_UPSTREAM_CHAIN)
    dataframes = {
        str(table_name): dataframe.copy(deep=True)
        for table_name, dataframe in upstream_data.items()
        if isinstance(dataframe, pd.DataFrame)
    }
    missing = [
        table_name
        for requirement in requirements
        for table_name in requirement.table_names
        if table_name not in dataframes or dataframes[table_name].empty
    ]
    if missing:
        raise ValueError(
            SALES_REQUIRES_UPSTREAM_CHAIN
            + " Missing required upstream tables: "
            + ", ".join(sorted(missing))
            + "."
        )
    return dataframes


def _stringify_upstream_paths(upstream_data_paths: Any) -> dict[str, str]:
    if not isinstance(upstream_data_paths, dict):
        return {}
    return {str(module_id): str(path) for module_id, path in upstream_data_paths.items() if path is not None}


def _validate_sales_table_contract(sales_data: dict[str, pd.DataFrame]) -> None:
    generated_tables = tuple(sales_data)
    if generated_tables != SALES_V1_EXPECTED_TABLES:
        extra = sorted(set(generated_tables) - set(SALES_V1_EXPECTED_TABLES))
        missing = sorted(set(SALES_V1_EXPECTED_TABLES) - set(generated_tables))
        raise ValueError(
            "Sales v1 execution must generate exactly the 18 approved Sales tables. "
            f"Missing: {', '.join(missing) or 'none'}; extra: {', '.join(extra) or 'none'}."
        )
    if "SalesCreditMemo" in sales_data:
        raise ValueError("SalesCreditMemo is excluded from Sales v1 and must not be generated.")


def _write_dataframes(output_folder: Path, dataframes: dict[str, pd.DataFrame], table_order: tuple[str, ...]) -> None:
    output_folder.mkdir(parents=True, exist_ok=True)
    for table_name in table_order:
        dataframes[table_name].to_csv(output_folder / f"{table_name}.csv", index=False)


def _write_validation_report(validation_report: DataQualityReport, reports_folder: Path) -> Path:
    reports_folder.mkdir(parents=True, exist_ok=True)
    json_path = reports_folder / "data_quality_report.json"
    json_path.write_text(json.dumps(validation_report.to_dict(), indent=2, default=str), encoding="utf-8")
    return json_path


def _run_sql_load(
    *,
    sales_data: dict[str, pd.DataFrame],
    metadata_path: Any,
    validation_report_path: Path,
    allow_unvalidated_sql_load: bool,
    if_table_exists: str,
    reports_folder: Path,
    sql_loader_factory: SQLLoaderFactory | None,
) -> tuple[str, list[str], list[str]]:
    if metadata_path is None:
        return (
            "failed",
            [],
            ["Sales SQL load requires Sales metadata_path so only Sales v1 tables are loaded."],
        )

    try:
        schema = read_metadata_schema(metadata_path)
    except ValueError as exc:
        return "failed", [], [f"Sales SQL load metadata validation failed: {exc}"]
    schema_tables = tuple(table.table_name for table in schema.ordered_tables)
    if schema_tables != SALES_V1_EXPECTED_TABLES:
        missing = sorted(set(SALES_V1_EXPECTED_TABLES) - set(schema_tables))
        extra = sorted(set(schema_tables) - set(SALES_V1_EXPECTED_TABLES))
        return (
            "failed",
            [],
            [
                "Sales SQL load requires Sales v1 metadata with exactly the 18 approved Sales tables. "
                f"Missing: {', '.join(missing) or 'none'}; extra: {', '.join(extra) or 'none'}."
            ],
        )

    config = DatabaseConfig.from_env(if_table_exists_override=if_table_exists)
    loader_factory = sql_loader_factory or (lambda loader_config: SQLServerLoader(loader_config))
    sql_report = loader_factory(config).load_dataset(
        sales_data,
        schema,
        validation_report_path=validation_report_path,
        allow_unvalidated_load=allow_unvalidated_sql_load,
    )
    save_sql_load_report(sql_report, reports_folder)
    warnings = [f"SQL load warning: {warning}" for warning in sql_report.warnings]
    errors = [f"SQL load error: {error}" for error in sql_report.errors]
    return sql_report.status, warnings, errors


def _write_pipeline_reports(result: SalesPipelineRunResult, reports_folder: Path) -> None:
    reports_folder.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    (reports_folder / "sales_pipeline_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Sales v1 Pipeline Report",
        "",
        f"- Run ID: {result.run_id}",
        f"- Status: {result.status}",
        f"- Seed: {result.seed}",
        f"- Validation status: {result.validation_status}",
        f"- Validation errors: {result.validation_error_count}",
        f"- Validation warnings: {result.validation_warning_count}",
        f"- Generated table count: {result.generated_table_count}",
        f"- Final data CSV count: {result.final_data_csv_count}",
        f"- SQL load status: {result.sql_load_status}",
        "",
        "## Output Folders",
    ]
    lines.extend(f"- {key}: {value}" for key, value in result.output_folders.items())
    if result.adjusted_finished_goods_inventory_path:
        lines.append(f"- adjusted_finished_goods_inventory: {result.adjusted_finished_goods_inventory_path}")
    lines.extend(["", "## Row Counts"])
    lines.extend(f"- {table_name}: {row_count}" for table_name, row_count in result.row_counts_by_table.items())
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in result.warnings or ["None."])
    lines.extend(["", "## Errors"])
    lines.extend(f"- {error}" for error in result.errors or ["None."])
    (reports_folder / "sales_pipeline_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
