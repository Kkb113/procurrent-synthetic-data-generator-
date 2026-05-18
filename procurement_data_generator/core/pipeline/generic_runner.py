"""Generic pipeline runner foundation for registered MES modules.

Phase 2 intentionally keeps orchestration conservative. The runner resolves
modules through the registry and delegates currently supported execution paths
without moving module business logic into core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport
from procurement_data_generator.core.llm.llm_client_base import LLMClientBase
from procurement_data_generator.core.modules.contracts import MESModulePlugin
from procurement_data_generator.core.modules.registry import ModuleRegistry, create_default_module_registry
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import SQLServerLoader


SQLLoaderFactory = Callable[[DatabaseConfig], SQLServerLoader]
LLMClientFactory = Callable[[], LLMClientBase]


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
                }
                for module_id, result in self.module_results.items()
            },
            "warnings": self.warnings,
            "errors": self.errors,
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

        for plugin in resolution.plugins:
            module_input = self._module_input(spec, plugin.module_id)
            module_output_root = root_output / plugin.module_id

            if plugin.module_id == "procurement":
                procurement_spec = self._with_module_output(spec, plugin.module_id, module_output_root)
                procurement_report = self._run_procurement(procurement_spec, plugin)
                module_results["procurement"] = ModulePipelineRunResult(
                    module_id="procurement",
                    status=procurement_report.status,
                    output_folder=procurement_report.output_folder,
                    tables_generated=procurement_report.tables_generated,
                    total_rows_generated=procurement_report.total_rows_generated,
                    data_quality_status=procurement_report.data_quality_status,
                    report=procurement_report,
                )
                if procurement_report.status not in {"passed", "passed_with_warnings"}:
                    errors.extend(procurement_report.errors)
                    break
                upstream_paths["procurement"] = Path(procurement_report.output_folder) / "final_data"
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
                    allow_demo_fallback=(spec.generation_config or self.generation_config).allow_demo_fallback,
                    operating_scope=spec.operating_scope or self.operating_scope,
                    generation_config=spec.generation_config or self.generation_config,
                )
                module_results["production"] = ModulePipelineRunResult(
                    module_id="production",
                    status=production_result.status,
                    output_folder=production_result.output_folders.get("run"),
                    tables_generated=production_result.generated_table_count,
                    total_rows_generated=sum(production_result.row_counts_by_table.values()),
                    data_quality_status=production_result.validation_status,
                    report=production_result,
                )
                warnings.extend(production_result.warnings)
                errors.extend(production_result.errors)
                if production_result.status not in {"passed", "passed_with_warnings"}:
                    break
                continue

            raise ModuleExecutionNotSupportedError(
                f"Module '{plugin.module_id}' is registered but generic execution is not implemented."
            )

        status = _combined_status(module_results, errors, warnings)
        return GenericPipelineRunResult(
            status=status,
            module_ids=resolution.module_ids,
            output_folder=str(root_output),
            module_results=module_results,
            warnings=warnings,
            errors=errors,
        )

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
        missing = []
        for requirement in plugin.get_upstream_requirements():
            missing.extend(
                table_name
                for table_name in requirement.table_names
                if not (upstream_path / f"{table_name}.csv").exists()
            )
        if missing:
            raise ModuleDependencyError(
                f"Module '{plugin.module_id}' is missing required upstream tables: {', '.join(sorted(missing))}."
            )

    def _validate_supported_execution_order(self, resolution: ModuleResolution) -> None:
        module_ids = resolution.module_ids
        if module_ids in {("procurement",), ("production",), ("procurement", "production")}:
            return
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
