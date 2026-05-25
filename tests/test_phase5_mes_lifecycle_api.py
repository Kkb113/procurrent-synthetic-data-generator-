from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.routes import pipeline_routes
from app.services.pipeline_service import PipelineService
from procurement_data_generator.core.pipeline.generic_runner import GenericPipelineRunResult, ModulePipelineRunResult


client = TestClient(app)


def test_run_mes_requires_metadata_xlsx(monkeypatch) -> None:
    monkeypatch.setattr(pipeline_routes, "pipeline_service", PipelineService())

    response = client.post(
        "/api/pipeline/run-mes",
        data={
            "mermaid_erd": "erDiagram",
            "business_scenario": "Food manufacturing",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Please upload metadata XLSX."


def test_run_mes_requires_mermaid_erd(monkeypatch) -> None:
    monkeypatch.setattr(pipeline_routes, "pipeline_service", PipelineService())

    response = client.post(
        "/api/pipeline/run-mes",
        data={"business_scenario": "Food manufacturing"},
        files={"metadata_xlsx": ("metadata.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Please provide Mermaid ERD."


def test_run_mes_requires_business_scenario(monkeypatch) -> None:
    monkeypatch.setattr(pipeline_routes, "pipeline_service", PipelineService())

    response = client.post(
        "/api/pipeline/run-mes",
        data={"mermaid_erd": "erDiagram"},
        files={"metadata_xlsx": ("metadata.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Please enter a business scenario."


def test_run_mes_rejects_invalid_row_settings() -> None:
    response = client.post(
        "/api/pipeline/run-mes",
        data={
            "mermaid_erd": "erDiagram",
            "business_scenario": "Food manufacturing",
            "target_total_rows": "0",
        },
        files={"metadata_xlsx": ("metadata.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "target_total_rows must be a positive integer."


def test_run_mes_rejects_invalid_row_scale_factor() -> None:
    response = client.post(
        "/api/pipeline/run-mes",
        data={
            "mermaid_erd": "erDiagram",
            "business_scenario": "Food manufacturing",
            "row_scale_factor": "-1",
        },
        files={"metadata_xlsx": ("metadata.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "row_scale_factor must be a positive number."


def test_run_mes_success_uses_full_lifecycle_and_returns_artifacts(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    class FakeGenericRunner:
        def run(self, spec):
            captured["spec"] = spec
            root = Path(spec.output_folder)
            (root / "final_data").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "procurement" / "run_1" / "prompt").mkdir(parents=True, exist_ok=True)
            (root / "production" / "run_1" / "reports").mkdir(parents=True, exist_ok=True)
            (root / "reports" / "row_budget_report.json").write_text("{}", encoding="utf-8")
            (root / "reports" / "row_count_audit.json").write_text("{}", encoding="utf-8")
            (root / "procurement" / "run_1" / "prompt" / "generated_industry_profile.json").write_text("{}", encoding="utf-8")
            (root / "production" / "run_1" / "reports" / "performance_profile_phase4.json").write_text("{}", encoding="utf-8")
            return GenericPipelineRunResult(
                status="passed",
                module_ids=spec.module_ids,
                output_folder=spec.output_folder,
                module_results={
                    "procurement": ModulePipelineRunResult(
                        module_id="procurement",
                        status="passed",
                        output_folder=str(root / "procurement" / "run_1"),
                        tables_generated=25,
                        total_rows_generated=100,
                        data_quality_status="passed",
                    ),
                    "production": ModulePipelineRunResult(
                        module_id="production",
                        status="passed",
                        output_folder=str(root / "production" / "run_1"),
                        tables_generated=21,
                        total_rows_generated=80,
                        data_quality_status="passed",
                    ),
                    "sales": ModulePipelineRunResult(
                        module_id="sales",
                        status="passed",
                        output_folder=str(root / "sales" / "run_1"),
                        tables_generated=18,
                        total_rows_generated=60,
                        data_quality_status="passed",
                        report=SimpleNamespace(adjusted_finished_goods_inventory_path=None),
                    ),
                },
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run-mes",
        data={
            "mermaid_erd": "erDiagram",
            "business_scenario": "Electronics manufacturing with IoT devices",
            "use_azure_openai": "false",
            "build_prompt": "true",
            "load_sql": "false",
            "target_total_rows": "50000",
            "row_scale_factor": "2.0",
            "seed": "7",
            "sql_if_table_exists": "replace",
        },
        files={"metadata_xlsx": ("metadata.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["spec"].module_ids == ("procurement", "production", "sales")
    assert captured["spec"].generate_plan is True
    assert captured["spec"].build_prompt is True
    assert captured["spec"].load_sql is False
    assert captured["spec"].generation_config.target_total_rows == 50000
    assert captured["spec"].generation_config.row_scale_factor == 2.0
    assert captured["spec"].generation_config.use_local_scenario_planner is True
    assert captured["spec"].seed == 7
    assert payload["status"] == "passed"
    assert payload["total_rows"] == 240
    assert payload["per_module_row_counts"] == {"procurement": 100, "production": 80, "sales": 60}
    assert payload["validation_status"] == "passed"
    assert payload["sql_status"] == "not_run"
    assert "row_budget_report" in payload["artifact_paths"]
    assert "row_count_audit" in payload["artifact_paths"]
    assert "performance_profile_phase4" in payload["artifact_paths"]
    assert "final_data_zip" in payload["downloads"]


def test_run_mes_azure_flag_uses_live_planning_path(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    class FakeGenericRunner:
        def run(self, spec):
            captured["spec"] = spec
            return GenericPipelineRunResult(
                status="passed",
                module_ids=spec.module_ids,
                output_folder=spec.output_folder,
                module_results={},
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run-mes",
        data={
            "mermaid_erd": "erDiagram",
            "business_scenario": "EV manufacturing",
            "use_azure_openai": "true",
        },
        files={"metadata_xlsx": ("metadata.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    assert captured["spec"].generate_plan is True
    assert captured["spec"].generation_config.use_local_scenario_planner is False
    assert captured["spec"].module_inputs["procurement"].plan_path is None
