"""Web-facing orchestration service for Phase 15 pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
from fastapi import UploadFile

from app.services.upload_service import UploadValidationError, save_text_input, save_upload_file
from app.services.mes_lifecycle_response import enrich_mes_lifecycle_summary
from procurement_data_generator.core.metadata.metadata_reader import METADATA_SHEET_NAME
from procurement_data_generator.core.modules.registry import create_default_module_registry
from procurement_data_generator.core.erd.mermaid_parser import RELATIONSHIP_PATTERN
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport
from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.pipeline.generic_runner import GenericPipelineRunResult, ModulePipelineInput, PipelineRunSpec, SyntheticDataPipelineRunner
from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


PipelineRunnerFactory = Callable[[], ProcurementPipelineRunner]
GenericPipelineRunnerFactory = Callable[[], SyntheticDataPipelineRunner]


DEFAULT_GENERIC_INPUTS = {
    "procurement": ModulePipelineInput(
        metadata_path="input/procurement_v2_metadata.xlsx",
        erd_path="input/procurement_v2_erd.mmd",
        scenario_path="input/procurement_v2_business_scenario.txt",
        plan_path="input/sample_generation_plan_v2_valid.json",
        model_version="v2",
    ),
    "production": ModulePipelineInput(
        metadata_path="input/production_v1_metadata.xlsx",
        erd_path="input/production_v1_erd.mmd",
        scenario_path="input/production_v1_business_scenario.txt",
        plan_path="input/sample_generation_plan_production_v1_valid.json",
        model_version="production_v1",
    ),
    "sales": ModulePipelineInput(
        metadata_path="input/sales_v1_metadata.xlsx",
        erd_path="input/sales_v1_erd.mmd",
        scenario_path=None,
        plan_path=None,
        model_version="v1",
    ),
}

GENERATION_TYPE_ALIASES = {
    "address": "category",
    "boolean": "category",
    "business_key": "category",
    "business_name": "faker_company",
    "customer_name": "faker_company",
    "date": "date_range",
    "formula": "calculated",
    "numeric_range": "decimal_range",
    "postal_code": "category",
}

AZURE_OPENAI_PLAN_HINT = (
    "For local deterministic runs, leave 'Generate plan using Azure OpenAI' unchecked. "
    "To use live planning, configure AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT."
)


@dataclass(frozen=True)
class PipelineWebRequest:
    metadata_file: UploadFile | None
    erd_file: UploadFile | None
    plan_file: UploadFile | None
    erd_text: str | None
    scenario_text: str | None
    use_azure_openai: bool
    build_prompt: bool
    load_sql: bool
    if_table_exists: str
    seed: int | None
    model_version: str = "v2"


@dataclass(frozen=True)
class GenericPipelineWebRequest:
    modules: tuple[str, ...]
    output_dir: str | None = None
    seed: int | None = None
    allow_demo_fallback: bool = False
    upstream_data: str | None = None
    use_azure_openai: bool = False
    build_prompt: bool = False
    load_sql: bool = False
    if_table_exists: str = "replace"
    profile_id: str | None = None
    target_total_rows: int | None = None
    row_scale_factor: float | None = None
    max_rows_per_table: int | None = None
    use_local_scenario_planner: bool = False
    metadata_file: UploadFile | None = None
    erd_file: UploadFile | None = None
    plan_file: UploadFile | None = None
    erd_text: str | None = None
    scenario_text: str | None = None
    production_metadata_file: UploadFile | None = None
    production_erd_file: UploadFile | None = None
    production_plan_file: UploadFile | None = None
    production_erd_text: str | None = None
    production_scenario_text: str | None = None


@dataclass(frozen=True)
class MESLifecycleWebRequest:
    """Productized web request for the full MES lifecycle workflow."""

    metadata_file: UploadFile | None
    erd_text: str | None
    scenario_text: str | None
    use_azure_openai: bool = False
    build_prompt: bool = False
    load_sql: bool = False
    target_total_rows: int | None = None
    row_scale_factor: float | None = None
    seed: int | None = None
    if_table_exists: str = "replace"
    max_rows_per_table: int | None = None
    profile_id: str | None = None


class PipelineService:
    """Validate web inputs, save uploads, and call the backend pipeline."""

    def __init__(
        self,
        base_folder: str | Path = "output/web_runs",
        runner_factory: PipelineRunnerFactory | None = None,
        generic_runner_factory: GenericPipelineRunnerFactory | None = None,
    ) -> None:
        self.base_folder = Path(base_folder)
        self.runner_factory = runner_factory or ProcurementPipelineRunner
        self.generic_runner_factory = generic_runner_factory or SyntheticDataPipelineRunner

    async def run_pipeline(self, request: PipelineWebRequest) -> dict:
        self._validate_switches(request)
        run_id = self._new_run_id()
        workspace = self.base_folder / run_id
        uploads = workspace / "uploads"
        pipeline_output = workspace / "pipeline_output"
        uploads.mkdir(parents=True, exist_ok=False)
        pipeline_output.mkdir(parents=True, exist_ok=True)

        metadata_path = await save_upload_file(
            request.metadata_file,
            uploads / "metadata.xlsx",
            {".xlsx"},
            "metadata_file",
            required=True,
        )
        erd_path = await self._save_erd(request, uploads)
        scenario_path = save_text_input(request.scenario_text, uploads / "scenario.txt", "scenario_text", required=True)
        plan_path = None
        if not request.use_azure_openai:
            plan_path = await save_upload_file(
                request.plan_file,
                uploads / "plan.json",
                {".json"},
                "plan_file",
                required=True,
            )

        runner = self.runner_factory()
        report = runner.run_pipeline(
            metadata_path=str(metadata_path),
            erd_path=str(erd_path),
            scenario_path=str(scenario_path),
            plan_path=str(plan_path) if plan_path else None,
            output_folder=str(pipeline_output),
            seed=request.seed,
            load_sql=request.load_sql,
            build_prompt=request.build_prompt,
            generate_plan=request.use_azure_openai,
            if_table_exists=request.if_table_exists,
            model_version=request.model_version,
        )
        return self._summary(run_id, report)

    async def run_mes_lifecycle(self, request: MESLifecycleWebRequest) -> dict:
        """Run the productized Procurement -> Production -> Sales workflow.

        Developer routes still support individual modules and explicit plan
        files. This method is intentionally narrower for the main UI.
        """

        self._validate_mes_lifecycle_request(request)
        generic_request = GenericPipelineWebRequest(
            modules=("procurement", "production", "sales"),
            seed=request.seed,
            use_azure_openai=True,
            build_prompt=request.build_prompt,
            load_sql=request.load_sql,
            if_table_exists=request.if_table_exists,
            profile_id=request.profile_id,
            target_total_rows=request.target_total_rows,
            row_scale_factor=request.row_scale_factor,
            max_rows_per_table=request.max_rows_per_table,
            use_local_scenario_planner=not request.use_azure_openai,
            metadata_file=request.metadata_file,
            erd_text=request.erd_text,
            scenario_text=request.scenario_text,
        )
        summary = await self.run_generic_pipeline(generic_request)
        return enrich_mes_lifecycle_summary(summary)

    async def run_generic_pipeline(self, request: GenericPipelineWebRequest) -> dict:
        self._validate_generic_request(request)
        run_id = self._new_run_id()
        workspace = self.base_folder / run_id
        uploads = workspace / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        output_root = Path(request.output_dir) if request.output_dir else workspace / "pipeline_output"
        generation_config = GenerationConfig(
            seed=request.seed if request.seed is not None else 42,
            allow_demo_fallback=request.allow_demo_fallback,
            profile_id=request.profile_id,
            target_total_rows=request.target_total_rows,
            row_scale_factor=request.row_scale_factor if request.row_scale_factor is not None else 1.0,
            max_rows_per_table=request.max_rows_per_table,
            use_local_scenario_planner=request.use_local_scenario_planner,
        )
        runner = self.generic_runner_factory()
        module_inputs = await self._generic_module_inputs(request, uploads)
        first_input = module_inputs[request.modules[0]]
        result = runner.run(
            PipelineRunSpec(
                module_ids=request.modules,
                metadata_path=first_input.metadata_path,
                erd_path=first_input.erd_path,
                scenario_path=first_input.scenario_path,
                plan_path=first_input.plan_path,
                output_folder=str(output_root),
                seed=request.seed,
                load_sql=request.load_sql,
                build_prompt=request.build_prompt,
                generate_plan=request.use_azure_openai,
                if_table_exists=request.if_table_exists,
                model_version=first_input.model_version,
                generation_config=generation_config,
                module_inputs={module_id: module_inputs[module_id] for module_id in request.modules},
            )
        )
        return self._generic_summary(run_id, result)

    async def _generic_module_inputs(self, request: GenericPipelineWebRequest, uploads: Path) -> dict[str, ModulePipelineInput]:
        procurement = DEFAULT_GENERIC_INPUTS["procurement"]
        production = DEFAULT_GENERIC_INPUTS["production"]
        sales = DEFAULT_GENERIC_INPUTS["sales"]

        shared_metadata = await self._optional_upload(request.metadata_file, uploads / "combined_metadata.xlsx", {".xlsx"})
        metadata_by_module = self._split_combined_metadata_by_module(shared_metadata, uploads, request.modules) if shared_metadata else {}
        procurement_metadata = metadata_by_module.get("procurement") or shared_metadata or procurement.metadata_path
        shared_erd = await self._optional_upload(request.erd_file, uploads / "combined_erd.mmd", {".mmd", ".txt"})
        if shared_erd is None and request.erd_text and request.erd_text.strip():
            shared_erd = save_text_input(request.erd_text, uploads / "combined_erd.mmd", "erd_text", required=True)
        erd_by_module = self._split_combined_erd_by_module(shared_erd, metadata_by_module, uploads, request.modules) if shared_erd else {}
        procurement_erd = erd_by_module.get("procurement") or shared_erd
        procurement_plan = await self._optional_upload(request.plan_file, uploads / "procurement_plan.json", {".json"}) or procurement.plan_path
        procurement_scenario = save_text_input(request.scenario_text, uploads / "procurement_scenario.txt", "scenario_text", required=False) if request.scenario_text and request.scenario_text.strip() else None

        production_metadata_upload = await self._optional_upload(request.production_metadata_file, uploads / "production_metadata.xlsx", {".xlsx"})
        production_metadata = production_metadata_upload or metadata_by_module.get("production") or production.metadata_path
        production_erd = await self._optional_upload(request.production_erd_file, uploads / "production_erd.mmd", {".mmd", ".txt"})
        if production_erd is None and request.production_erd_text and request.production_erd_text.strip():
            production_erd = save_text_input(request.production_erd_text, uploads / "production_erd.mmd", "production_erd_text", required=True)
        if production_erd is None:
            production_erd = erd_by_module.get("production")
        production_plan = await self._optional_upload(request.production_plan_file, uploads / "production_plan.json", {".json"}) or production.plan_path
        production_scenario = save_text_input(request.production_scenario_text, uploads / "production_scenario.txt", "production_scenario_text", required=False) if request.production_scenario_text and request.production_scenario_text.strip() else None
        if production_scenario is None and procurement_scenario is not None:
            production_scenario = procurement_scenario
        sales_metadata = metadata_by_module.get("sales") or sales.metadata_path
        sales_erd = erd_by_module.get("sales") or sales.erd_path

        module_inputs: dict[str, ModulePipelineInput] = {}
        if "procurement" in request.modules:
            module_inputs["procurement"] = ModulePipelineInput(
                metadata_path=str(procurement_metadata),
                erd_path=str(procurement_erd or procurement.erd_path),
                scenario_path=str(procurement_scenario or procurement.scenario_path),
                plan_path=None if request.use_azure_openai else str(procurement_plan),
                model_version="v2",
            )
        if "production" in request.modules:
            module_inputs["production"] = ModulePipelineInput(
                metadata_path=str(production_metadata),
                erd_path=str(production_erd or production.erd_path),
                scenario_path=str(production_scenario or production.scenario_path),
                plan_path=str(production_plan),
                model_version="production_v1",
                upstream_data_path=request.upstream_data,
            )
        if "sales" in request.modules:
            module_inputs["sales"] = ModulePipelineInput(
                metadata_path=str(sales_metadata),
                erd_path=str(sales_erd),
                scenario_path=str(procurement_scenario or sales.scenario_path or ""),
                plan_path=str(sales.plan_path) if sales.plan_path else None,
                model_version="v1",
            )
        return module_inputs

    def _split_combined_metadata_by_module(
        self,
        metadata_path: Path,
        uploads: Path,
        module_ids: tuple[str, ...],
    ) -> dict[str, Path]:
        """Write module-specific metadata files from a combined workbook.

        The browser can upload one Procurement + Production workbook. Existing
        module runners still validate module-specific metadata, so this adapter
        filters by the registered role catalogs before orchestration.
        """

        if len(module_ids) < 2:
            return {}
        try:
            metadata = pd.read_excel(metadata_path, sheet_name=METADATA_SHEET_NAME, engine="openpyxl", dtype=object)
        except Exception:
            return {}
        if "TableRole" not in metadata.columns:
            return {}

        registry = create_default_module_registry()
        normalized_roles = metadata["TableRole"].astype(str).str.strip().str.lower()
        split_paths: dict[str, Path] = {}
        for module_id in module_ids:
            plugin = registry.get(module_id)
            supported_roles = {role.strip().lower() for role in plugin.supported_table_roles}
            subset = metadata.loc[normalized_roles.isin(supported_roles)].copy()
            if subset.empty:
                continue
            subset = self._normalize_metadata_generation_type_aliases(subset)
            target = uploads / f"{module_id}_metadata.xlsx"
            with pd.ExcelWriter(target, engine="openpyxl") as writer:
                subset.to_excel(writer, sheet_name=METADATA_SHEET_NAME, index=False)
            split_paths[module_id] = target
        return split_paths

    def _normalize_metadata_generation_type_aliases(self, metadata: pd.DataFrame) -> pd.DataFrame:
        if "GenerationType" not in metadata.columns:
            return metadata
        normalized = metadata.copy()
        normalized["GenerationType"] = normalized["GenerationType"].map(_metadata_generation_type_alias)
        return normalized

    def _split_combined_erd_by_module(
        self,
        erd_path: Path,
        metadata_by_module: dict[str, Path],
        uploads: Path,
        module_ids: tuple[str, ...],
    ) -> dict[str, Path]:
        if len(module_ids) < 2:
            return {}

        registry = create_default_module_registry()
        split_paths: dict[str, Path] = {}
        for module_id in module_ids:
            metadata_path = metadata_by_module.get(module_id)
            if metadata_path is None:
                continue
            table_names = self._metadata_table_names(metadata_path)
            if not table_names:
                continue
            plugin = registry.get(module_id)
            for requirement in plugin.get_upstream_requirements():
                table_names.update(requirement.table_names)
            filtered_text = self._filter_mermaid_erd_for_tables(erd_path.read_text(encoding="utf-8"), table_names)
            target = uploads / f"{module_id}_erd.mmd"
            target.write_text(filtered_text, encoding="utf-8")
            split_paths[module_id] = target
        return split_paths

    def _metadata_table_names(self, metadata_path: Path) -> set[str]:
        try:
            metadata = pd.read_excel(metadata_path, sheet_name=METADATA_SHEET_NAME, engine="openpyxl", dtype=object)
        except Exception:
            return set()
        if "TableName" not in metadata.columns:
            return set()
        return {str(table_name).strip() for table_name in metadata["TableName"].dropna() if str(table_name).strip()}

    def _filter_mermaid_erd_for_tables(self, erd_text: str, allowed_tables: set[str]) -> str:
        allowed = {table.strip() for table in allowed_tables if table.strip()}
        lines = ["erDiagram"]
        seen_header = False
        for raw_line in erd_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped == "erDiagram":
                seen_header = True
                continue
            match = RELATIONSHIP_PATTERN.match(stripped)
            if not match:
                continue
            left_table = match.group("left")
            right_table = match.group("right")
            if left_table in allowed and right_table in allowed:
                lines.append(f"    {stripped}")
        if not seen_header and erd_text.strip():
            lines.insert(0, "%% Filtered from combined Mermaid ERD")
        return "\n".join(lines) + "\n"

    async def _optional_upload(self, upload: UploadFile | None, target: Path, allowed_extensions: set[str]) -> Path | None:
        if upload is None or not upload.filename:
            return None
        return await save_upload_file(upload, target, allowed_extensions, upload.filename, required=True)

    async def _save_erd(self, request: PipelineWebRequest, uploads: Path) -> Path:
        if request.erd_file and request.erd_file.filename:
            saved = await save_upload_file(
                request.erd_file,
                uploads / "procurement_erd.mmd",
                {".mmd", ".txt"},
                "erd_file",
                required=True,
            )
            if saved:
                return saved
        saved_text = save_text_input(request.erd_text, uploads / "procurement_erd.mmd", "erd_file or erd_text", required=True)
        if saved_text is None:
            raise UploadValidationError("Either erd_file or erd_text is required.")
        return saved_text

    def _validate_switches(self, request: PipelineWebRequest) -> None:
        if request.model_version == "v1":
            raise UploadValidationError("Procurement V1 is deprecated and no longer supported. Use Procurement V2.")
        if request.model_version != "v2":
            raise UploadValidationError("model_version must be v2.")
        if request.if_table_exists not in {"replace", "append", "fail"}:
            raise UploadValidationError("if_table_exists must be replace, append, or fail.")
        if not request.scenario_text or not request.scenario_text.strip():
            raise UploadValidationError("scenario_text is required.")
        has_erd_file = bool(request.erd_file and request.erd_file.filename)
        has_erd_text = bool(request.erd_text and request.erd_text.strip())
        if not has_erd_file and not has_erd_text:
            raise UploadValidationError("Either erd_file or erd_text is required.")
        if not request.use_azure_openai and (request.plan_file is None or not request.plan_file.filename):
            raise UploadValidationError("plan_file is required when Azure OpenAI generation is disabled.")

    def _validate_mes_lifecycle_request(self, request: MESLifecycleWebRequest) -> None:
        if request.metadata_file is None or not request.metadata_file.filename:
            raise UploadValidationError("Please upload metadata XLSX.")
        if not request.erd_text or not request.erd_text.strip():
            raise UploadValidationError("Please provide Mermaid ERD.")
        if not request.scenario_text or not request.scenario_text.strip():
            raise UploadValidationError("Please enter a business scenario.")
        if request.if_table_exists not in {"replace", "append", "fail"}:
            raise UploadValidationError("sql_if_table_exists must be replace, append, or fail.")
        if request.target_total_rows is not None and request.target_total_rows <= 0:
            raise UploadValidationError("target_total_rows must be a positive integer.")
        if request.row_scale_factor is not None and request.row_scale_factor <= 0:
            raise UploadValidationError("row_scale_factor must be a positive number.")
        if request.max_rows_per_table is not None and request.max_rows_per_table <= 0:
            raise UploadValidationError("max_rows_per_table must be a positive integer.")

    def _validate_generic_request(self, request: GenericPipelineWebRequest) -> None:
        if not request.modules:
            raise UploadValidationError("modules must include at least one module.")
        unknown = [module_id for module_id in request.modules if module_id not in DEFAULT_GENERIC_INPUTS]
        if unknown:
            raise UploadValidationError(f"Unknown module(s): {', '.join(unknown)}")
        duplicates = sorted({module_id for module_id in request.modules if request.modules.count(module_id) > 1})
        if duplicates:
            raise UploadValidationError(f"Duplicate module(s): {', '.join(duplicates)}")
        if request.if_table_exists not in {"replace", "append", "fail"}:
            raise UploadValidationError("if_table_exists must be replace, append, or fail.")
        if request.modules == ("production",) and not request.allow_demo_fallback and not request.upstream_data:
            raise UploadValidationError("Production requires Procurement upstream data. Select Procurement + Production or enable demo fallback.")
        if "sales" in request.modules and request.modules != ("procurement", "production", "sales"):
            raise UploadValidationError(
                "Sales requires Production finished goods and Procurement/Production lineage. "
                "Select Procurement + Production + Sales."
            )

    def _new_run_id(self) -> str:
        return "web_run_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    def _summary(self, web_run_id: str, report: PipelineRunReport) -> dict:
        data_quality_stage = next((stage for stage in report.stages if stage.stage_name == "data_quality_validation"), None)
        sql_stage = next((stage for stage in report.stages if stage.stage_name == "sql_load"), None)
        stage_summary = [
            {
                "stage_name": stage.stage_name,
                "status": stage.status,
                "errors_count": stage.errors_count,
                "warnings_count": stage.warnings_count,
                "message": stage.message,
            }
            for stage in report.stages
        ]
        downloads = {
            "audit_md": f"/api/artifacts/{web_run_id}/audit-md",
            "audit_json": f"/api/artifacts/{web_run_id}/audit-json",
            "pipeline_json": f"/api/artifacts/{web_run_id}/pipeline-json",
            "final_data_zip": f"/api/artifacts/{web_run_id}/final-data-zip",
        }
        output_folder = Path(report.output_folder)
        if (output_folder / "prompt" / "generated_llm_plan.json").exists():
            downloads["generated_plan"] = f"/api/artifacts/{web_run_id}/generated-plan"
        if (output_folder / "prompt" / "azure_openai_raw_response.txt").exists():
            downloads["raw_llm_response"] = f"/api/artifacts/{web_run_id}/raw-llm-response"
        return {
            "run_id": web_run_id,
            "model_version": report.model_version,
            "status": report.status,
            "message": "Pipeline completed." if report.status in {"passed", "passed_with_warnings"} else "Pipeline failed.",
            "output_folder": report.output_folder,
            "stage_summary": stage_summary,
            "tables_generated": report.tables_generated,
            "total_rows_generated": report.total_rows_generated,
            "data_quality_status": data_quality_stage.status if data_quality_stage else "not_run",
            "sql_load_status": sql_stage.status if sql_stage else "not_run",
            "warnings": report.warnings,
            "errors": self._errors_with_hints(report.errors),
            "downloads": downloads,
        }

    def _generic_summary(self, web_run_id: str, result: PipelineRunReport | GenericPipelineRunResult) -> dict:
        if isinstance(result, PipelineRunReport):
            summary = self._summary(web_run_id, result)
            summary["module_ids"] = ["procurement"]
            summary["module_results"] = {
                "procurement": {
                    "status": result.status,
                    "tables_generated": result.tables_generated,
                    "data_quality_status": result.data_quality_status,
                    "sql_load_status": result.sql_load_status,
                    "output_folder": result.output_folder,
                }
            }
            summary["output_dir"] = result.output_folder
            summary["table_counts"] = {"procurement": result.tables_generated}
            summary["validation_summary"] = {"procurement": result.data_quality_status}
            summary["adjusted_finished_goods_inventory"] = {"available": False, "path": None}
            summary["sql_load_status"] = result.sql_load_status
            return summary
        module_sql_statuses = [
            module_result.sql_load_status
            for module_result in result.module_results.values()
            if module_result.sql_load_status and module_result.sql_load_status != "not_run"
        ]
        return {
            "run_id": web_run_id,
            "status": result.status,
            "message": "Pipeline completed." if result.status in {"passed", "passed_with_warnings"} else "Pipeline failed.",
            "module_ids": list(result.module_ids),
            "output_folder": result.output_folder,
            "output_dir": result.output_folder,
            "tables_generated": sum(module_result.tables_generated for module_result in result.module_results.values()),
            "total_rows_generated": sum(module_result.total_rows_generated for module_result in result.module_results.values()),
            "sql_load_status": self._combined_status(module_sql_statuses, empty="not_run"),
            "table_counts": {
                module_id: module_result.tables_generated
                for module_id, module_result in result.module_results.items()
            },
            "validation_summary": {
                module_id: module_result.data_quality_status
                for module_id, module_result in result.module_results.items()
            },
            "module_results": {
                module_id: {
                    "status": module_result.status,
                    "tables_generated": module_result.tables_generated,
                    "total_rows_generated": module_result.total_rows_generated,
                    "data_quality_status": module_result.data_quality_status,
                    "sql_load_status": module_result.sql_load_status,
                    "output_folder": module_result.output_folder,
                }
                for module_id, module_result in result.module_results.items()
            },
            "adjusted_finished_goods_inventory": self._adjusted_inventory_summary(result),
            "row_count_audit_paths": result.row_count_audit_paths,
            "warnings": result.warnings,
            "errors": self._errors_with_hints(result.errors),
        }

    def _adjusted_inventory_summary(self, result: GenericPipelineRunResult) -> dict:
        sales_result = result.module_results.get("sales")
        sales_report = sales_result.report if sales_result is not None else None
        adjusted_path = getattr(sales_report, "adjusted_finished_goods_inventory_path", None)
        return {
            "available": bool(adjusted_path),
            "path": adjusted_path,
        }

    def _combined_status(self, statuses: list[str], empty: str = "-") -> str:
        if not statuses:
            return empty
        if any(status == "failed" for status in statuses):
            return "failed"
        if any(status == "passed_with_warnings" for status in statuses):
            return "passed_with_warnings"
        if all(status == "skipped" for status in statuses):
            return "skipped"
        if any(status == "passed" for status in statuses):
            return "passed"
        return statuses[0]

    def _errors_with_hints(self, errors: list[str]) -> list[str]:
        enhanced: list[str] = []
        for error in errors:
            message = str(error)
            if "Azure OpenAI plan generation failed" in message and AZURE_OPENAI_PLAN_HINT not in message:
                message = f"{message} {AZURE_OPENAI_PLAN_HINT}"
            enhanced.append(message)
        return enhanced


def _metadata_generation_type_alias(value):
    if value is None:
        return value
    text = str(value).strip()
    return GENERATION_TYPE_ALIASES.get(text.lower(), value)
