from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes import pipeline_routes
from app.services.pipeline_service import PipelineService
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport, PipelineStageReport, utc_now_iso


client = TestClient(app)


def _files(include_metadata=True, include_erd=True, include_plan=True):
    files = {}
    if include_metadata:
        files["metadata_file"] = ("metadata.xlsx", b"xlsx-bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if include_erd:
        files["erd_file"] = ("procurement_erd.mmd", b"erDiagram\nVendor ||--o{ PurchaseOrderHeader : supplies", "text/plain")
    if include_plan:
        files["plan_file"] = ("plan.json", b'{"module": "procurement"}', "application/json")
    return files


def _form(**overrides):
    data = {
        "scenario_text": "Generate procurement data.",
        "use_azure_openai": "false",
        "build_prompt": "true",
        "load_sql": "false",
        "if_table_exists": "replace",
        "seed": "42",
    }
    data.update(overrides)
    return data


def _fake_report() -> PipelineRunReport:
    report = PipelineRunReport(
        run_id="run_mock",
        started_at=utc_now_iso(),
        input_files={},
        output_folder="output/web_runs/web_run_mock/pipeline_output/run_mock",
    )
    stage = PipelineStageReport("metadata_validation")
    stage.start()
    stage.finish("passed", "ok")
    report.add_stage(stage)
    report.tables_generated = 16
    report.total_rows_generated = 1917
    report.complete("passed_with_warnings")
    return report


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run_pipeline(self, **kwargs):
        self.calls.append(kwargs)
        return _fake_report()


def test_run_fails_if_metadata_missing() -> None:
    response = client.post("/api/pipeline/run", data=_form(), files=_files(include_metadata=False))

    assert response.status_code == 400
    assert "metadata_file" in response.json()["detail"]


def test_run_fails_if_scenario_missing() -> None:
    response = client.post("/api/pipeline/run", data=_form(scenario_text=""), files=_files())

    assert response.status_code == 400
    assert "scenario_text" in response.json()["detail"]


def test_run_fails_if_erd_missing() -> None:
    response = client.post("/api/pipeline/run", data=_form(), files=_files(include_erd=False))

    assert response.status_code == 400
    assert "erd" in response.json()["detail"].lower()


def test_run_fails_if_plan_missing_and_azure_disabled() -> None:
    response = client.post("/api/pipeline/run", data=_form(use_azure_openai="false"), files=_files(include_plan=False))

    assert response.status_code == 400
    assert "plan_file" in response.json()["detail"]


def test_run_accepts_azure_mode_without_plan_file(tmp_path: Path, monkeypatch) -> None:
    fake_runner = FakeRunner()
    service = PipelineService(base_folder=tmp_path, runner_factory=lambda: fake_runner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run",
        data=_form(use_azure_openai="true"),
        files=_files(include_plan=False),
    )

    assert response.status_code == 200
    assert fake_runner.calls[0]["generate_plan"] is True
    assert fake_runner.calls[0]["plan_path"] is None


def test_run_calls_pipeline_service_with_correct_arguments(monkeypatch) -> None:
    captured = {}

    class FakeService:
        async def run_pipeline(self, request):
            captured["request"] = request
            return {
                "run_id": "web_run_mock",
                "status": "passed",
                "message": "Pipeline completed.",
                "stage_summary": [],
                "tables_generated": 16,
                "total_rows_generated": 1917,
                "data_quality_status": "passed",
                "sql_load_status": "skipped",
                "warnings": [],
                "errors": [],
                "downloads": {"pipeline_json": "/api/artifacts/web_run_mock/pipeline-json"},
            }

    monkeypatch.setattr(pipeline_routes, "pipeline_service", FakeService())
    response = client.post("/api/pipeline/run", data=_form(load_sql="true", if_table_exists="append"), files=_files())

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "web_run_mock"
    assert payload["stage_summary"] == []
    assert captured["request"].load_sql is True
    assert captured["request"].if_table_exists == "append"
    assert captured["request"].model_version == "v1"


def test_successful_pipeline_response_includes_downloads(tmp_path: Path, monkeypatch) -> None:
    fake_runner = FakeRunner()
    service = PipelineService(base_folder=tmp_path, runner_factory=lambda: fake_runner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run", data=_form(), files=_files())

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"].startswith("web_run_")
    assert payload["model_version"] == "v1"
    assert payload["status"] == "passed_with_warnings"
    assert payload["stage_summary"]
    assert "audit_md" in payload["downloads"]
