"""Artifact download API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.artifact_service import ArtifactNotFoundError, ArtifactService, UnsafeRunIdError


router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
artifact_service = ArtifactService()


@router.get("/{run_id}/audit-md")
async def audit_markdown(run_id: str) -> FileResponse:
    return _file_response(run_id, "audit_md", "audit_report.md", "text/markdown")


@router.get("/{run_id}/audit-json")
async def audit_json(run_id: str) -> FileResponse:
    return _file_response(run_id, "audit_json", "audit_report.json", "application/json")


@router.get("/{run_id}/pipeline-json")
async def pipeline_json(run_id: str) -> FileResponse:
    return _file_response(run_id, "pipeline_json", "pipeline_run_report.json", "application/json")


@router.get("/{run_id}/final-data-zip")
async def final_data_zip(run_id: str) -> FileResponse:
    try:
        path = artifact_service.get_final_data_zip(run_id)
        return FileResponse(path, media_type="application/zip", filename="final_data.zip")
    except (ArtifactNotFoundError, UnsafeRunIdError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/generated-plan")
async def generated_plan(run_id: str) -> FileResponse:
    return _file_response(run_id, "generated_plan", "generated_llm_plan.json", "application/json")


@router.get("/{run_id}/raw-llm-response")
async def raw_llm_response(run_id: str) -> FileResponse:
    return _file_response(run_id, "raw_llm_response", "azure_openai_raw_response.txt", "text/plain")


def _file_response(run_id: str, artifact_name: str, filename: str, media_type: str) -> FileResponse:
    try:
        path = artifact_service.get_artifact_path(run_id, artifact_name)
        return FileResponse(path, media_type=media_type, filename=filename)
    except (ArtifactNotFoundError, UnsafeRunIdError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
