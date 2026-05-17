"""Generic pipeline runner foundation for registered MES modules.

Phase 2 intentionally keeps orchestration conservative. The runner resolves
modules through the registry and delegates currently supported execution paths
without moving module business logic into core.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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

    def run(self, spec: PipelineRunSpec) -> PipelineRunReport:
        resolution = self.resolve_modules(spec.module_ids)
        if len(resolution.plugins) != 1:
            raise ModuleExecutionNotSupportedError(
                "Multi-module generic pipeline execution is scheduled for a later phase."
            )

        plugin = resolution.plugins[0]
        if plugin.module_id == "procurement":
            return self._run_procurement(spec, plugin)

        raise ModuleExecutionNotSupportedError(
            f"Module '{plugin.module_id}' is registered but full generic pipeline execution is scheduled for a later phase."
        )

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
        # TODO Phase 8: move the legacy Procurement orchestration body into this
        # runner once Production is ready for the same execution shape.
        from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner

        runner = ProcurementPipelineRunner(
            sql_loader_factory=self.sql_loader_factory,
            llm_client_factory=self.llm_client_factory,
            module_plugin=plugin,
            operating_scope=spec.operating_scope or self.operating_scope,
            generation_config=spec.generation_config or self.generation_config,
        )
        return runner.run_pipeline(
            metadata_path=spec.metadata_path,
            erd_path=spec.erd_path,
            scenario_path=spec.scenario_path,
            plan_path=spec.plan_path,
            output_folder=str(Path(spec.output_folder)),
            seed=spec.seed,
            load_sql=spec.load_sql,
            allow_unvalidated_sql_load=spec.allow_unvalidated_sql_load,
            build_prompt=spec.build_prompt,
            generate_plan=spec.generate_plan,
            use_existing_plan=spec.use_existing_plan,
            if_table_exists=spec.if_table_exists,
            model_version=spec.model_version or plugin.module_version,
        )


def _normalize_module_id(module_id: str) -> str:
    normalized = module_id.strip().lower()
    if not normalized:
        raise PipelineConfigurationError("module_id values must not be empty.")
    return normalized
