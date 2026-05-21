"""Generic pipeline runner foundation for registered MES modules.

Phase 2 intentionally keeps orchestration conservative. The runner resolves
modules through the registry and delegates currently supported execution paths
without moving module business logic into core.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.audit.row_count_audit import RowCountAuditBuilder, RowCountAuditInput
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport
from procurement_data_generator.core.llm.llm_client_base import LLMClientBase
from procurement_data_generator.core.metadata.metadata_reader import read_metadata_schema
from procurement_data_generator.core.modules.contracts import MESModulePlugin
from procurement_data_generator.core.modules.registry import ModuleRegistry, create_default_module_registry
from procurement_data_generator.core.row_budget import RowBudgetPlan, RowBudgetPlanner
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import SQLServerLoader, save_sql_load_report


SQLLoaderFactory = Callable[[DatabaseConfig], SQLServerLoader]
LLMClientFactory = Callable[[], LLMClientBase]
SALES_REQUIRES_UPSTREAM_CHAIN = (
    "Sales requires upstream Procurement and Production data. "
    "Run modules=['procurement','production','sales']."
)


class PipelineConfigurationError(ValueError):
    """Raised when a generic pipeline request is invalid."""


class ModuleExecutionNotSupportedError(NotImplementedError):
    """Raised when a registered module is not yet executable by the generic runner."""


class ModuleDependencyError(PipelineConfigurationError):
    """Raised when requested module ordering or upstream data is invalid."""


@dataclass(frozen=True)
class ModulePipelineInput:
    """Input files and upstream data for one module in a generic run."""

    metadata_path: str
    erd_path: str
    scenario_path: str | None
    plan_path: str | None
    model_version: str | None = None
    upstream_data_path: str | None = None


@dataclass(frozen=True)
class PipelineRunSpec:
    """Inputs for a module pipeline run."""

    module_ids: tuple[str, ...]
    metadata_path: str
    erd_path: str
    scenario_path: str | None
    plan_path: str | None
    output_folder: str
    seed: int | None = None
    load_sql: bool = False
    allow_unvalidated_sql_load: bool = False
    build_prompt: bool = False
    generate_plan: bool = False
    use_existing_plan: bool = False
    if_table_exists: str = "replace"
    model_version: str | None = None
    operating_scope: OperatingScope | None = None
    generation_config: GenerationConfig | None = None
    module_inputs: dict[str, ModulePipelineInput | dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ModulePipelineRunResult:
    """Result for one module executed by the generic runner."""

    module_id: str
    status: str
    output_folder: str | None
    tables_generated: int = 0
    total_rows_generated: int = 0
    data_quality_status: str = "not_run"
    sql_load_status: str = "not_run"
    report: Any = None


@dataclass(frozen=True)
class GenericPipelineRunResult:
    """Structured result for generic multi-module execution."""

    status: str
    module_ids: tuple[str, ...]
    output_folder: str
    module_results: dict[str, ModulePipelineRunResult]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    row_count_audit_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "module_ids": list(self.module_ids),
            "output_folder": self.output_folder,
            "module_results": {
                module_id: {
                    "module_id": result.module_id,
                    "status": result.status,
                    "output_folder": result.output_folder,
                    "tables_generated": result.tables_generated,
                    "total_rows_generated": result.total_rows_generated,
                    "data_quality_status": result.data_quality_status,
                    "sql_load_status": result.sql_load_status,
                }
                for module_id, result in self.module_results.items()
            },
            "warnings": self.warnings,
            "errors": self.errors,
            "row_count_audit_paths": self.row_count_audit_paths,
        }


@dataclass(frozen=True)
class ModuleResolution:
    """Resolved module execution order."""

    module_ids: tuple[str, ...]
    plugins: tuple[MESModulePlugin, ...]


class SyntheticDataPipelineRunner:
    """Resolve and execute registered MES module plugins."""

    def __init__(
        self,
        module_registry: ModuleRegistry | None = None,
        sql_loader_factory: SQLLoaderFactory | None = None,
        llm_client_factory: LLMClientFactory | None = None,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self.module_registry = module_registry or create_default_module_registry()
        self.sql_loader_factory = sql_loader_factory
        self.llm_client_factory = llm_client_factory
        self.operating_scope = operating_scope or DEFAULT_OPERATING_SCOPE
        self.generation_config = generation_config or GenerationConfig()

    def resolve_modules(self, module_ids: list[str] | tuple[str, ...]) -> ModuleResolution:
        normalized = tuple(_normalize_module_id(module_id) for module_id in module_ids)
        if not normalized:
            raise PipelineConfigurationError("At least one module_id is required.")
        duplicates = sorted({module_id for module_id in normalized if normalized.count(module_id) > 1})
        if duplicates:
            raise PipelineConfigurationError(f"Duplicate module_id values are not allowed: {', '.join(duplicates)}.")
        plugins = tuple(self.module_registry.get(module_id) for module_id in normalized)
        return ModuleResolution(module_ids=normalized, plugins=plugins)

    def run(self, spec: PipelineRunSpec) -> PipelineRunReport | GenericPipelineRunResult:
        resolution = self.resolve_modules(spec.module_ids)
        self._validate_supported_execution_order(resolution)

        if resolution.module_ids == ("procurement",):
            return self._run_procurement(spec, resolution.plugins[0])

        return self._run_generic_modules(spec, resolution)

    def run_pipeline(
        self,
        module_id: str,
        metadata_path: str,
        erd_path: str,
        scenario_path: str | None,
        plan_path: str | None,
        output_folder: str,
        seed: int | None = None,
        load_sql: bool = False,
        allow_unvalidated_sql_load: bool = False,
        build_prompt: bool = False,
        generate_plan: bool = False,
        use_existing_plan: bool = False,
        if_table_exists: str = "replace",
        model_version: str | None = None,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> PipelineRunReport:
        return self.run(
            PipelineRunSpec(
                module_ids=(module_id,),
                metadata_path=metadata_path,
                erd_path=erd_path,
                scenario_path=scenario_path,
                plan_path=plan_path,
                output_folder=output_folder,
                seed=seed,
                load_sql=load_sql,
                allow_unvalidated_sql_load=allow_unvalidated_sql_load,
                build_prompt=build_prompt,
                generate_plan=generate_plan,
                use_existing_plan=use_existing_plan,
                if_table_exists=if_table_exists,
                model_version=model_version,
                operating_scope=operating_scope,
                generation_config=generation_config,
            )
        )

    def _run_procurement(self, spec: PipelineRunSpec, plugin: MESModulePlugin) -> PipelineRunReport:
        from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner

        module_input = self._module_input(spec, "procurement")
        runner = ProcurementPipelineRunner(
            sql_loader_factory=self.sql_loader_factory,
            llm_client_factory=self.llm_client_factory,
            module_plugin=plugin,
            operating_scope=spec.operating_scope or self.operating_scope,
            generation_config=spec.generation_config or self.generation_config,
        )
        return runner.run_pipeline(
            metadata_path=module_input.metadata_path,
            erd_path=module_input.erd_path,
            scenario_path=module_input.scenario_path,
            plan_path=module_input.plan_path,
            output_folder=str(Path(spec.output_folder)),
            seed=spec.seed,
            load_sql=spec.load_sql,
            allow_unvalidated_sql_load=spec.allow_unvalidated_sql_load,
            build_prompt=spec.build_prompt,
            generate_plan=spec.generate_plan,
            use_existing_plan=spec.use_existing_plan,
            if_table_exists=spec.if_table_exists,
            model_version=module_input.model_version or spec.model_version or plugin.module_version,
        )

    def _run_generic_modules(self, spec: PipelineRunSpec, resolution: ModuleResolution) -> GenericPipelineRunResult:
        root_output = Path(spec.output_folder)
        root_output.mkdir(parents=True, exist_ok=True)
        module_results: dict[str, ModulePipelineRunResult] = {}
        warnings: list[str] = []
        errors: list[str] = []
        upstream_paths: dict[str, Path] = {}
        runtime_generation_config = spec.generation_config or self.generation_config
        row_budget_plan = self._plan_row_budget(spec, resolution, runtime_generation_config, warnings)
        if row_budget_plan is not None:
            runtime_generation_config = replace(
                runtime_generation_config,
                planned_row_targets=row_budget_plan.planned_row_targets,
            )

        for plugin in resolution.plugins:
            module_input = self._module_input(spec, plugin.module_id)
            module_output_root = root_output / plugin.module_id

            if plugin.module_id == "procurement":
                procurement_spec = replace(
                    self._with_module_output(spec, plugin.module_id, module_output_root),
                    generation_config=runtime_generation_config,
                )
                procurement_report = self._run_procurement(procurement_spec, plugin)
                module_results["procurement"] = ModulePipelineRunResult(
                    module_id="procurement",
                    status=procurement_report.status,
                    output_folder=procurement_report.output_folder,
                    tables_generated=procurement_report.tables_generated,
                    total_rows_generated=procurement_report.total_rows_generated,
                    data_quality_status=procurement_report.data_quality_status,
                    sql_load_status=procurement_report.sql_load_status,
                    report=procurement_report,
                )
                if procurement_report.status not in {"passed", "passed_with_warnings"}:
                    errors.extend(procurement_report.errors)
                    break
                upstream_paths["procurement"] = Path(procurement_report.output_folder) / "final_data"
                generated_profile_path = Path(procurement_report.output_folder) / "prompt" / "generated_industry_profile.json"
                if generated_profile_path.exists():
                    runtime_generation_config = replace(runtime_generation_config, profile_file=generated_profile_path)
                continue

            if plugin.module_id == "production":
                upstream_path = self._resolve_upstream_path(plugin, module_input, upstream_paths, spec)
                production_result = plugin.run_pipeline(
                    metadata_path=module_input.metadata_path,
                    erd_path=module_input.erd_path,
                    scenario_path=module_input.scenario_path or "",
                    plan_path=module_input.plan_path or "",
                    output_folder=str(module_output_root),
                    seed=spec.seed,
                    upstream_data_path=str(upstream_path) if upstream_path is not None else None,
                    load_sql=spec.load_sql,
                    allow_unvalidated_sql_load=spec.allow_unvalidated_sql_load,
                    if_table_exists=spec.if_table_exists,
                    sql_loader_factory=self.sql_loader_factory,
                    allow_demo_fallback=runtime_generation_config.allow_demo_fallback,
                    operating_scope=spec.operating_scope or self.operating_scope,
                    generation_config=runtime_generation_config,
                )
                module_results["production"] = ModulePipelineRunResult(
                    module_id="production",
                    status=production_result.status,
                    output_folder=production_result.output_folders.get("run"),
                    tables_generated=production_result.generated_table_count,
                    total_rows_generated=sum(production_result.row_counts_by_table.values()),
                    data_quality_status=production_result.validation_status,
                    sql_load_status=production_result.sql_load_status,
                    report=production_result,
                )
                warnings.extend(production_result.warnings)
                errors.extend(production_result.errors)
                if production_result.status not in {"passed", "passed_with_warnings"}:
                    break
                production_run_folder = production_result.output_folders.get("run")
                if production_run_folder:
                    upstream_paths["production"] = Path(production_run_folder) / "final_data"
                continue

            if plugin.module_id == "sales":
                sales_upstream_paths = self._resolve_sales_upstream_paths(plugin, upstream_paths)
                sales_result = plugin.run_pipeline(
                    metadata_path=module_input.metadata_path,
                    output_folder=str(module_output_root),
                    seed=spec.seed,
                    upstream_data_paths={module_id: str(path) for module_id, path in sales_upstream_paths.items()},
                    load_sql=spec.load_sql,
                    allow_unvalidated_sql_load=spec.allow_unvalidated_sql_load,
                    if_table_exists=spec.if_table_exists,
                    sql_loader_factory=self.sql_loader_factory,
                    operating_scope=spec.operating_scope or self.operating_scope,
                    generation_config=runtime_generation_config,
                )
                module_results["sales"] = ModulePipelineRunResult(
                    module_id="sales",
                    status=sales_result.status,
                    output_folder=sales_result.output_folders.get("run"),
                    tables_generated=sales_result.generated_table_count,
                    total_rows_generated=sum(sales_result.row_counts_by_table.values()),
                    data_quality_status=sales_result.validation_status,
                    sql_load_status=sales_result.sql_load_status,
                    report=sales_result,
                )
                warnings.extend(sales_result.warnings)
                errors.extend(sales_result.errors)
                if sales_result.status not in {"passed", "passed_with_warnings"}:
                    break
                sales_run_folder = sales_result.output_folders.get("run")
                if sales_run_folder:
                    upstream_paths["sales"] = Path(sales_run_folder) / "final_data"
                self._write_combined_final_data(root_output, upstream_paths, sales_result)
                if spec.load_sql:
                    inventory_sql_status, inventory_sql_warnings, inventory_sql_errors = (
                        self._load_sales_adjusted_finished_goods_inventory_to_sql(spec, sales_result)
                    )
                    warnings.extend(inventory_sql_warnings)
                    errors.extend(inventory_sql_errors)
                    current_sales_result = module_results["sales"]
                    sales_status = current_sales_result.status
                    if inventory_sql_errors:
                        sales_status = "failed"
                    elif sales_status == "passed" and inventory_sql_warnings:
                        sales_status = "passed_with_warnings"
                    module_results["sales"] = ModulePipelineRunResult(
                        module_id=current_sales_result.module_id,
                        status=sales_status,
                        output_folder=current_sales_result.output_folder,
                        tables_generated=current_sales_result.tables_generated,
                        total_rows_generated=current_sales_result.total_rows_generated,
                        data_quality_status=current_sales_result.data_quality_status,
                        sql_load_status=_combined_sql_load_status(
                            current_sales_result.sql_load_status,
                            inventory_sql_status,
                        ),
                        report=current_sales_result.report,
                    )
                continue

            raise ModuleExecutionNotSupportedError(
                f"Module '{plugin.module_id}' is registered but generic execution is not implemented."
            )

        row_count_audit_paths = self._write_row_count_audit(root_output, spec, module_results, warnings)
        self._write_row_budget_report(root_output, row_budget_plan, module_results, warnings)
        status = _combined_status(module_results, errors, warnings)
        return GenericPipelineRunResult(
            status=status,
            module_ids=resolution.module_ids,
            output_folder=str(root_output),
            module_results=module_results,
            warnings=warnings,
            errors=errors,
            row_count_audit_paths=row_count_audit_paths,
        )

    def _plan_row_budget(
        self,
        spec: PipelineRunSpec,
        resolution: ModuleResolution,
        generation_config: GenerationConfig,
        warnings: list[str],
    ) -> RowBudgetPlan | None:
        schemas: dict[str, SchemaContract] = {}
        try:
            for module_id in resolution.module_ids:
                module_input = self._module_input(spec, module_id)
                schemas[module_id] = read_metadata_schema(module_input.metadata_path)
            return RowBudgetPlanner().plan_modules(schemas, generation_config)
        except Exception as exc:
            warnings.append(f"Row budget planning failed: {exc}")
            return None

    def _resolve_sales_upstream_paths(
        self,
        plugin: MESModulePlugin,
        upstream_paths: dict[str, Path],
    ) -> dict[str, Path]:
        resolved: dict[str, Path] = {}
        missing_modules: list[str] = []
        for requirement in plugin.get_upstream_requirements():
            upstream_path = upstream_paths.get(requirement.module_id)
            if upstream_path is None:
                if requirement.required:
                    missing_modules.append(requirement.module_id)
                continue
            self._check_requirement_tables(plugin.module_id, requirement, upstream_path)
            resolved[requirement.module_id] = upstream_path
        if missing_modules:
            raise ModuleDependencyError(SALES_REQUIRES_UPSTREAM_CHAIN)
        return resolved

    def _resolve_upstream_path(
        self,
        plugin: MESModulePlugin,
        module_input: ModulePipelineInput,
        upstream_paths: dict[str, Path],
        spec: PipelineRunSpec,
    ) -> Path | None:
        explicit = Path(module_input.upstream_data_path) if module_input.upstream_data_path else None
        if explicit is not None:
            self._check_required_upstream_tables(plugin, explicit)
            return explicit

        requirements = plugin.get_upstream_requirements()
        for requirement in requirements:
            upstream_path = upstream_paths.get(requirement.module_id)
            if upstream_path is None:
                if requirement.required and not (spec.generation_config or self.generation_config).allow_demo_fallback:
                    raise ModuleDependencyError(
                        "Production requires Procurement upstream data. Run modules=['procurement','production'] "
                        "or provide upstream_data / allow_demo_fallback=True."
                    )
                return None
            self._check_required_upstream_tables(plugin, upstream_path)
            return upstream_path
        return None

    def _check_required_upstream_tables(self, plugin: MESModulePlugin, upstream_path: Path) -> None:
        for requirement in plugin.get_upstream_requirements():
            self._check_requirement_tables(plugin.module_id, requirement, upstream_path)

    def _check_requirement_tables(
        self,
        module_id: str,
        requirement,
        upstream_path: Path,
    ) -> None:
        missing = [
            table_name
            for table_name in requirement.table_names
            if not (upstream_path / f"{table_name}.csv").exists()
        ]
        if missing:
            raise ModuleDependencyError(
                f"Module '{module_id}' is missing required upstream tables from {requirement.module_id}: "
                f"{', '.join(sorted(missing))}."
            )

    def _write_combined_final_data(
        self,
        root_output: Path,
        upstream_paths: dict[str, Path],
        sales_result,
    ) -> None:
        final_output = root_output / "final_data"
        final_output.mkdir(parents=True, exist_ok=True)
        for existing_csv in final_output.glob("*.csv"):
            existing_csv.unlink()

        for module_id in ("procurement", "production", "sales"):
            module_final = upstream_paths.get(module_id)
            if module_final is None:
                continue
            for csv_path in module_final.glob("*.csv"):
                shutil.copy2(csv_path, final_output / csv_path.name)

        adjusted_inventory_path = getattr(sales_result, "adjusted_finished_goods_inventory_path", None)
        if adjusted_inventory_path:
            shutil.copy2(Path(adjusted_inventory_path), final_output / "FinishedGoodsInventory.csv")

    def _load_sales_adjusted_finished_goods_inventory_to_sql(
        self,
        spec: PipelineRunSpec,
        sales_result,
    ) -> tuple[str, list[str], list[str]]:
        adjusted_inventory_path = getattr(sales_result, "adjusted_finished_goods_inventory_path", None)
        if not adjusted_inventory_path:
            return (
                "failed",
                [],
                ["Adjusted FinishedGoodsInventory SQL load requires the Sales-adjusted inventory artifact."],
            )
        inventory_path = Path(adjusted_inventory_path)
        if not inventory_path.exists():
            return (
                "failed",
                [],
                [f"Adjusted FinishedGoodsInventory SQL load artifact not found: {inventory_path}."],
            )

        production_input = self._module_input(spec, "production")
        try:
            production_schema = read_metadata_schema(production_input.metadata_path)
        except ValueError as exc:
            return (
                "failed",
                [],
                [f"Adjusted FinishedGoodsInventory SQL load metadata validation failed: {exc}"],
            )
        inventory_table = production_schema.tables.get("FinishedGoodsInventory")
        if inventory_table is None:
            return (
                "failed",
                [],
                ["Adjusted FinishedGoodsInventory SQL load requires Production metadata for FinishedGoodsInventory."],
            )

        adjusted_inventory = pd.read_csv(inventory_path)
        inventory_schema = SchemaContract(tables={"FinishedGoodsInventory": inventory_table})
        reports_folder_value = getattr(sales_result, "output_folders", {}).get("reports")
        reports_folder = Path(reports_folder_value) if reports_folder_value else None
        validation_report_path = (
            reports_folder / "data_quality_report.json"
            if reports_folder is not None and (reports_folder / "data_quality_report.json").exists()
            else None
        )
        config = DatabaseConfig.from_env(if_table_exists_override="replace")
        loader_factory = self.sql_loader_factory or (lambda loader_config: SQLServerLoader(loader_config))
        sql_report = loader_factory(config).load_dataset(
            {"FinishedGoodsInventory": adjusted_inventory},
            inventory_schema,
            validation_report_path=validation_report_path,
            allow_unvalidated_load=spec.allow_unvalidated_sql_load,
        )
        if reports_folder is not None:
            save_sql_load_report(sql_report, reports_folder / "adjusted_finished_goods_inventory_sql_load")

        warnings = [f"Adjusted FinishedGoodsInventory SQL load warning: {warning}" for warning in sql_report.warnings]
        errors = [f"Adjusted FinishedGoodsInventory SQL load error: {error}" for error in sql_report.errors]
        return sql_report.status, warnings, errors

    def _write_row_count_audit(
        self,
        root_output: Path,
        spec: PipelineRunSpec,
        module_results: dict[str, ModulePipelineRunResult],
        warnings: list[str],
    ) -> dict[str, str]:
        if not module_results:
            return {}
        audit_inputs: list[RowCountAuditInput] = []
        for module_id, module_result in module_results.items():
            data_folder = Path(module_result.output_folder) / "final_data" if module_result.output_folder else None
            module_input = self._module_input(spec, module_id)
            audit_inputs.append(
                RowCountAuditInput(
                    module_id=module_id,
                    metadata_path=module_input.metadata_path,
                    data_folder=data_folder,
                )
            )
        try:
            result = RowCountAuditBuilder().build_for_inputs(
                audit_inputs,
                root_output / "reports",
            )
        except Exception as exc:
            warnings.append(f"Row-count audit failed: {exc}")
            return {}
        return {
            "json": str(result.json_path),
            "markdown": str(result.markdown_path),
        }

    def _write_row_budget_report(
        self,
        root_output: Path,
        row_budget_plan: RowBudgetPlan | None,
        module_results: dict[str, ModulePipelineRunResult],
        warnings: list[str],
    ) -> str | None:
        if row_budget_plan is None or not module_results:
            return None
        try:
            report_path = row_budget_plan.write_report(
                root_output / "reports",
                {
                    module_id: _collect_module_actual_counts(module_result)
                    for module_id, module_result in module_results.items()
                },
            )
            return str(report_path)
        except Exception as exc:
            warnings.append(f"Row budget report failed: {exc}")
            return None

    def _validate_supported_execution_order(self, resolution: ModuleResolution) -> None:
        module_ids = resolution.module_ids
        if module_ids in {
            ("procurement",),
            ("production",),
            ("procurement", "production"),
            ("procurement", "production", "sales"),
        }:
            return
        if "sales" in module_ids:
            raise ModuleDependencyError(SALES_REQUIRES_UPSTREAM_CHAIN)
        if "production" in module_ids and "procurement" in module_ids:
            if module_ids.index("production") < module_ids.index("procurement"):
                raise ModuleDependencyError("Production requires Procurement to run before Production.")
        raise ModuleExecutionNotSupportedError(
            f"Generic execution is not implemented for modules={list(module_ids)}."
        )

    def _module_input(self, spec: PipelineRunSpec, module_id: str) -> ModulePipelineInput:
        raw = spec.module_inputs.get(module_id)
        if raw is None:
            return ModulePipelineInput(
                metadata_path=spec.metadata_path,
                erd_path=spec.erd_path,
                scenario_path=spec.scenario_path,
                plan_path=spec.plan_path,
                model_version=spec.model_version,
            )
        if isinstance(raw, ModulePipelineInput):
            return raw
        return ModulePipelineInput(**raw)

    def _with_module_output(self, spec: PipelineRunSpec, module_id: str, output_folder: Path) -> PipelineRunSpec:
        module_input = self._module_input(spec, module_id)
        return PipelineRunSpec(
            module_ids=(module_id,),
            metadata_path=module_input.metadata_path,
            erd_path=module_input.erd_path,
            scenario_path=module_input.scenario_path,
            plan_path=module_input.plan_path,
            output_folder=str(output_folder),
            seed=spec.seed,
            load_sql=spec.load_sql,
            allow_unvalidated_sql_load=spec.allow_unvalidated_sql_load,
            build_prompt=spec.build_prompt,
            generate_plan=spec.generate_plan,
            use_existing_plan=spec.use_existing_plan,
            if_table_exists=spec.if_table_exists,
            model_version=module_input.model_version or spec.model_version,
            operating_scope=spec.operating_scope,
            generation_config=spec.generation_config,
            module_inputs={module_id: module_input},
        )


def _normalize_module_id(module_id: str) -> str:
    normalized = module_id.strip().lower()
    if not normalized:
        raise PipelineConfigurationError("module_id values must not be empty.")
    return normalized


def _combined_status(
    module_results: dict[str, ModulePipelineRunResult],
    errors: list[str],
    warnings: list[str],
) -> str:
    if errors or any(result.status == "failed" for result in module_results.values()):
        return "failed"
    if warnings or any(result.status == "passed_with_warnings" for result in module_results.values()):
        return "passed_with_warnings"
    return "passed"


def _combined_sql_load_status(*statuses: str) -> str:
    normalized = tuple(status for status in statuses if status)
    if any(status == "failed" for status in normalized):
        return "failed"
    if any(status == "passed_with_warnings" for status in normalized):
        return "passed_with_warnings"
    if normalized and all(status == "not_run" for status in normalized):
        return "not_run"
    if any(status == "not_run" for status in normalized):
        return "passed_with_warnings"
    return "passed"


def _collect_module_actual_counts(module_result: ModulePipelineRunResult) -> dict[str, int]:
    if module_result.report is not None:
        row_counts = getattr(module_result.report, "row_counts_by_table", None)
        if isinstance(row_counts, dict):
            return {str(table_name): int(row_count) for table_name, row_count in row_counts.items()}
        summary = getattr(module_result.report, "generation_summary", None)
        if isinstance(summary, dict):
            by_table = summary.get("row_counts_by_table")
            if isinstance(by_table, dict):
                return {str(table_name): int(row_count) for table_name, row_count in by_table.items()}
    if not module_result.output_folder:
        return {}
    final_folder = Path(module_result.output_folder) / "final_data"
    if not final_folder.exists():
        return {}
    return {csv_path.stem: len(pd.read_csv(csv_path)) for csv_path in final_folder.glob("*.csv")}
