"""Pipeline API routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.services.pipeline_service import GenericPipelineWebRequest, PipelineService, PipelineWebRequest
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


@router.post("/run-generic")
async def run_generic_pipeline(request: Request) -> dict:
    try:
        payload = await _generic_payload(request)
        raw_modules = payload.get("modules", ["procurement"])
        if isinstance(raw_modules, str):
            modules = tuple(module.strip().lower() for module in raw_modules.split(",") if module.strip())
        else:
            modules = tuple(str(module).strip().lower() for module in raw_modules if str(module).strip())
        request = GenericPipelineWebRequest(
            modules=modules,
            output_dir=payload.get("output_dir"),
            seed=_optional_int(payload.get("seed")),
            allow_demo_fallback=_as_bool(payload.get("allow_demo_fallback", False)),
            upstream_data=payload.get("upstream_data"),
            use_azure_openai=_as_bool(payload.get("use_azure_openai", False)),
            build_prompt=_as_bool(payload.get("build_prompt", False)),
            load_sql=_as_bool(payload.get("load_sql", False)),
            if_table_exists=payload.get("if_table_exists") or "replace",
            profile_id=payload.get("profile_id"),
            metadata_file=_upload(payload.get("metadata_file")),
            erd_file=_upload(payload.get("erd_file")),
            plan_file=_upload(payload.get("plan_file")),
            erd_text=payload.get("erd_text"),
            scenario_text=payload.get("scenario_text"),
            production_metadata_file=_upload(payload.get("production_metadata_file")),
            production_erd_file=_upload(payload.get("production_erd_file")),
            production_plan_file=_upload(payload.get("production_plan_file")),
            production_erd_text=payload.get("production_erd_text"),
            production_scenario_text=payload.get("production_scenario_text"),
        )
        return await pipeline_service.run_generic_pipeline(request)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generic pipeline request failed: {exc}") from exc


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    from app.routes.artifact_routes import artifact_service

    try:
        return artifact_service.get_pipeline_summary(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _generic_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        return dict(form)
    return await request.json()


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _upload(value):
    return value if isinstance(value, StarletteUploadFile) else None
