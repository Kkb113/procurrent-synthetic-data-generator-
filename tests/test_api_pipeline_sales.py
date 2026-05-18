from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import pipeline_routes
from app.services.pipeline_service import PipelineService
from procurement_data_generator.core.pipeline.generic_runner import GenericPipelineRunResult, ModulePipelineRunResult


client = TestClient(app)


@pytest.mark.parametrize(
    ("modules", "expected"),
    [
        (["procurement"], ("procurement",)),
        (["procurement", "production"], ("procurement", "production")),
        (["procurement", "production", "sales"], ("procurement", "production", "sales")),
    ],
)
def test_generic_sales_api_accepts_supported_module_flows(tmp_path, monkeypatch, modules, expected) -> None:
    captured = {}

    class FakeGenericRunner:
        def run(self, spec):
            captured["spec"] = spec
            module_results = {}
            if "procurement" in spec.module_ids:
                module_results["procurement"] = ModulePipelineRunResult(
                    module_id="procurement",
                    status="passed",
                    output_folder=spec.output_folder,
                    tables_generated=25,
                    data_quality_status="passed",
                )
            if "production" in spec.module_ids:
                module_results["production"] = ModulePipelineRunResult(
                    module_id="production",
                    status="passed",
                    output_folder=spec.output_folder,
                    tables_generated=21,
                    data_quality_status="passed",
                )
            if "sales" in spec.module_ids:
                module_results["sales"] = ModulePipelineRunResult(
                    module_id="sales",
                    status="passed",
                    output_folder=spec.output_folder,
                    tables_generated=18,
                    data_quality_status="passed",
                    report=SimpleNamespace(adjusted_finished_goods_inventory_path=str(tmp_path / "FinishedGoodsInventory.csv")),
                )
            return GenericPipelineRunResult(
                status="passed",
                module_ids=spec.module_ids,
                output_folder=spec.output_folder,
                module_results=module_results,
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run-generic",
        json={"modules": modules, "seed": 42, "profile_id": "food_manufacturing"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert tuple(payload["module_ids"]) == expected
    assert captured["spec"].module_ids == expected
    assert captured["spec"].generation_config.profile_id == "food_manufacturing"


def test_generic_sales_api_response_includes_sales_counts_validation_and_adjusted_inventory(tmp_path, monkeypatch) -> None:
    adjusted_path = tmp_path / "FinishedGoodsInventory.csv"

    class FakeGenericRunner:
        def run(self, spec):
            return GenericPipelineRunResult(
                status="passed",
                module_ids=spec.module_ids,
                output_folder=spec.output_folder,
                module_results={
                    "procurement": ModulePipelineRunResult(
                        module_id="procurement",
                        status="passed",
                        output_folder=spec.output_folder,
                        tables_generated=25,
                        data_quality_status="passed",
                    ),
                    "production": ModulePipelineRunResult(
                        module_id="production",
                        status="passed",
                        output_folder=spec.output_folder,
                        tables_generated=21,
                        data_quality_status="passed",
                    ),
                    "sales": ModulePipelineRunResult(
                        module_id="sales",
                        status="passed",
                        output_folder=spec.output_folder,
                        tables_generated=18,
                        data_quality_status="passed",
                        report=SimpleNamespace(adjusted_finished_goods_inventory_path=str(adjusted_path)),
                    ),
                },
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run-generic",
        data={
            "modules": "procurement,production,sales",
            "seed": "42",
            "profile_id": "food_manufacturing",
            "build_prompt": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["module_ids"] == ["procurement", "production", "sales"]
    assert payload["table_counts"] == {"procurement": 25, "production": 21, "sales": 18}
    assert payload["validation_summary"]["sales"] == "passed"
    assert payload["module_results"]["sales"]["tables_generated"] == 18
    assert payload["adjusted_finished_goods_inventory"]["available"] is True
    assert payload["adjusted_finished_goods_inventory"]["path"] == str(adjusted_path)


def test_generic_sales_api_enriches_azure_openai_plan_failure(tmp_path, monkeypatch) -> None:
    class FakeGenericRunner:
        def run(self, spec):
            return GenericPipelineRunResult(
                status="failed",
                module_ids=spec.module_ids,
                output_folder=spec.output_folder,
                module_results={
                    "procurement": ModulePipelineRunResult(
                        module_id="procurement",
                        status="failed",
                        output_folder=spec.output_folder,
                        tables_generated=0,
                        data_quality_status="not_run",
                    )
                },
                errors=["Azure OpenAI plan generation failed."],
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run-generic",
        data={
            "modules": "procurement,production,sales",
            "use_azure_openai": "true",
            "build_prompt": "true",
            "profile_id": "food_manufacturing",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Pipeline failed."
    assert "leave 'Generate plan using Azure OpenAI' unchecked" in payload["errors"][0]
    assert "AZURE_OPENAI_ENDPOINT" in payload["errors"][0]


@pytest.mark.parametrize(
    "modules",
    [
        ["sales"],
        ["procurement", "sales"],
        ["production", "sales"],
        ["sales", "production"],
        ["procurement", "sales", "production"],
    ],
)
def test_generic_sales_api_rejects_invalid_sales_flows(monkeypatch, modules) -> None:
    class UnexpectedRunner:
        def run(self, spec):
            raise AssertionError("Invalid Sales flow should fail before runner execution.")

    service = PipelineService(generic_runner_factory=lambda: UnexpectedRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run-generic", json={"modules": modules})

    assert response.status_code == 400
    assert "Sales requires Production finished goods" in response.json()["detail"]


def test_legacy_pipeline_run_route_remains_available(monkeypatch) -> None:
    class FakeService:
        async def run_pipeline(self, request):
            return {"status": "passed", "model_version": request.model_version, "tables_generated": 25}

    monkeypatch.setattr(pipeline_routes, "pipeline_service", FakeService())

    response = client.post(
        "/api/pipeline/run",
        data={
            "scenario_text": "Generate Procurement v2 data.",
            "use_azure_openai": "true",
            "build_prompt": "true",
            "load_sql": "false",
            "if_table_exists": "replace",
            "seed": "42",
            "model_version": "v2",
        },
    )

    assert response.status_code == 200
    assert response.json()["tables_generated"] == 25
