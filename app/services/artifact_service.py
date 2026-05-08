"""Artifact lookup and download helpers for web pipeline runs."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any


class ArtifactNotFoundError(FileNotFoundError):
    """Raised when a requested run or artifact is not available."""


class UnsafeRunIdError(ValueError):
    """Raised when a run id attempts path traversal or invalid lookup."""


class ArtifactService:
    """Locate and package artifacts from known web run folders."""

    def __init__(self, base_folder: str | Path = "output/web_runs") -> None:
        self.base_folder = Path(base_folder)

    def get_pipeline_summary(self, run_id: str) -> dict[str, Any]:
        report_path = self.get_artifact_path(run_id, "pipeline_json")
        return json.loads(report_path.read_text(encoding="utf-8"))

    def get_artifact_path(self, run_id: str, artifact_name: str) -> Path:
        pipeline_folder = self._pipeline_output_folder(run_id)
        artifact_map = {
            "audit_md": pipeline_folder / "reports" / "audit_report.md",
            "audit_json": pipeline_folder / "reports" / "audit_report.json",
            "pipeline_json": pipeline_folder / "reports" / "pipeline_run_report.json",
            "generated_plan": pipeline_folder / "prompt" / "generated_llm_plan.json",
            "raw_llm_response": pipeline_folder / "prompt" / "azure_openai_raw_response.txt",
        }
        path = artifact_map.get(artifact_name)
        if path is None or not path.exists():
            raise ArtifactNotFoundError(f"Artifact {artifact_name} is not available for run {run_id}.")
        return self._safe_child(path)

    def get_final_data_zip(self, run_id: str) -> Path:
        pipeline_folder = self._pipeline_output_folder(run_id)
        final_data_folder = pipeline_folder / "final_data"
        if not final_data_folder.exists():
            raise ArtifactNotFoundError(f"Final data folder is not available for run {run_id}.")

        zip_path = pipeline_folder / "reports" / "final_data.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for csv_path in sorted(final_data_folder.glob("*.csv")):
                archive.write(csv_path, arcname=csv_path.name)
        return self._safe_child(zip_path)

    def _pipeline_output_folder(self, run_id: str) -> Path:
        workspace = self._run_workspace(run_id)
        output_root = workspace / "pipeline_output"
        direct_report = output_root / "reports" / "pipeline_run_report.json"
        if direct_report.exists():
            return self._safe_child(output_root)

        candidates = sorted(
            output_root.glob("run_*/reports/pipeline_run_report.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise ArtifactNotFoundError(f"Pipeline output is not available for run {run_id}.")
        return self._safe_child(candidates[0].parents[1])

    def _run_workspace(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id) or ".." in run_id:
            raise UnsafeRunIdError("Invalid run id.")
        path = self.base_folder / run_id
        if not path.exists():
            raise ArtifactNotFoundError(f"Run {run_id} was not found.")
        return self._safe_child(path)

    def _safe_child(self, path: Path) -> Path:
        base = self.base_folder.resolve()
        resolved = path.resolve()
        if resolved != base and base not in resolved.parents:
            raise UnsafeRunIdError("Requested path is outside the web runs folder.")
        return resolved
