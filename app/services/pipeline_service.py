"""Web-facing orchestration service for Phase 15 pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import UploadFile

from app.services.upload_service import UploadValidationError, save_text_input, save_upload_file
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport
from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


PipelineRunnerFactory = Callable[[], ProcurementPipelineRunner]


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
    model_version: str = "v1"


class PipelineService:
    """Validate web inputs, save uploads, and call the backend pipeline."""

    def __init__(
        self,
        base_folder: str | Path = "output/web_runs",
        runner_factory: PipelineRunnerFactory | None = None,
    ) -> None:
        self.base_folder = Path(base_folder)
        self.runner_factory = runner_factory or ProcurementPipelineRunner

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
        if request.model_version not in {"v1", "v2"}:
            raise UploadValidationError("model_version must be v1 or v2.")
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
            "errors": report.errors,
            "downloads": downloads,
        }
