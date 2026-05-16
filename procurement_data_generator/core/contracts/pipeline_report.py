"""Contracts for end-to-end pipeline run reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineStageReport:
    """Status and timing for one pipeline stage."""

    stage_name: str
    status: str = "skipped"
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    message: str = ""
    errors_count: int = 0
    warnings_count: int = 0
    output_paths: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.started_at = utc_now_iso()
        self.status = "running"

    def finish(
        self,
        status: str,
        message: str = "",
        errors_count: int = 0,
        warnings_count: int = 0,
        output_paths: list[str] | None = None,
    ) -> None:
        self.completed_at = utc_now_iso()
        self.status = status
        self.message = message
        self.errors_count = errors_count
        self.warnings_count = warnings_count
        if output_paths is not None:
            self.output_paths = output_paths
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = round((end - start).total_seconds(), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
            "errors_count": self.errors_count,
            "warnings_count": self.warnings_count,
            "output_paths": self.output_paths,
        }


@dataclass
class PipelineRunReport:
    """Top-level pipeline run report."""

    run_id: str
    started_at: str
    input_files: dict[str, Any]
    output_folder: str
    status: str = "running"
    completed_at: str | None = None
    duration_seconds: float | None = None
    current_stage: str | None = None
    stages: list[PipelineStageReport] = field(default_factory=list)
    tables_generated: int = 0
    total_rows_generated: int = 0
    model_version: str = "v2"
    expected_tables: list[str] = field(default_factory=list)
    final_data_tables: list[str] = field(default_factory=list)
    data_quality_status: str = "not_run"
    sql_load_status: str = "not_run"
    audit_report_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_stage(self, stage: PipelineStageReport) -> None:
        self.stages.append(stage)
        self.current_stage = stage.stage_name

    def complete(self, status: str) -> None:
        self.status = status
        self.completed_at = utc_now_iso()
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.completed_at)
        self.duration_seconds = round((end - start).total_seconds(), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "current_stage": self.current_stage,
            "stages": [stage.to_dict() for stage in self.stages],
            "input_files": self.input_files,
            "output_folder": self.output_folder,
            "tables_generated": self.tables_generated,
            "total_rows_generated": self.total_rows_generated,
            "model_version": self.model_version,
            "expected_tables": self.expected_tables,
            "final_data_tables": self.final_data_tables,
            "data_quality_status": self.data_quality_status,
            "sql_load_status": self.sql_load_status,
            "audit_report_path": self.audit_report_path,
            "errors": self.errors,
            "warnings": self.warnings,
        }
