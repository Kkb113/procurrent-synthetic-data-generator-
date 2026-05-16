"""Pipeline API routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.pipeline_service import PipelineService, PipelineWebRequest
from app.services.upload_service import UploadValidationError


router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])
pipeline_service = PipelineService()


@router.post("/run")
async def run_pipeline(
    metadata_file: UploadFile | None = File(default=None),
    erd_file: UploadFile | None = File(default=None),
    plan_file: UploadFile | None = File(default=None),
    erd_text: str | None = Form(default=None),
    scenario_text: str | None = Form(default=None),
    use_azure_openai: bool = Form(default=False),
    build_prompt: bool = Form(default=False),
    load_sql: bool = Form(default=False),
    if_table_exists: str = Form(default="replace"),
    seed: int | None = Form(default=None),
    model_version: str = Form(default="v2"),
) -> dict:
    try:
        request = PipelineWebRequest(
            metadata_file=metadata_file,
            erd_file=erd_file,
            plan_file=plan_file,
            erd_text=erd_text,
            scenario_text=scenario_text,
            use_azure_openai=use_azure_openai,
            build_prompt=build_prompt,
            load_sql=load_sql,
            if_table_exists=if_table_exists,
            seed=seed,
            model_version=model_version,
        )
        return await pipeline_service.run_pipeline(request)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline request failed: {exc}") from exc


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    from app.routes.artifact_routes import artifact_service

    try:
        return artifact_service.get_pipeline_summary(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
