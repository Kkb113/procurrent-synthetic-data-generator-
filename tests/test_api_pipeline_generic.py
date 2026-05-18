from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.routes import pipeline_routes
from app.services.pipeline_service import PipelineService
from procurement_data_generator.core.pipeline.generic_runner import GenericPipelineRunResult, ModulePipelineRunResult


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_generic_pipeline_api_passes_modules_to_service(monkeypatch) -> None:
    captured = {}

    class FakeService:
        async def run_generic_pipeline(self, request):
            captured["request"] = request
            return {
                "run_id": "web_run_generic",
                "status": "passed",
                "module_ids": list(request.modules),
                "module_results": {},
                "warnings": [],
                "errors": [],
            }

    monkeypatch.setattr(pipeline_routes, "pipeline_service", FakeService())

    response = client.post(
        "/api/pipeline/run-generic",
        json={"modules": ["procurement", "production"], "seed": 42, "allow_demo_fallback": False, "profile_id": "food_manufacturing"},
    )

    assert response.status_code == 200
    assert response.json()["module_ids"] == ["procurement", "production"]
    assert captured["request"].modules == ("procurement", "production")
    assert captured["request"].seed == 42
    assert captured["request"].profile_id == "food_manufacturing"


def test_generic_pipeline_api_rejects_bad_request(monkeypatch) -> None:
    from app.services.upload_service import UploadValidationError

    class FakeService:
        async def run_generic_pipeline(self, request):
            raise UploadValidationError("Unknown module(s): quality")

    monkeypatch.setattr(pipeline_routes, "pipeline_service", FakeService())

    response = client.post("/api/pipeline/run-generic", json={"modules": ["quality"]})

    assert response.status_code == 400
    assert "Unknown module" in response.json()["detail"]


def test_generic_pipeline_api_accepts_multipart_frontend_request(monkeypatch) -> None:
    captured = {}

    class FakeService:
        async def run_generic_pipeline(self, request):
            captured["request"] = request
            return {
                "run_id": "web_run_generic",
                "status": "passed",
                "module_ids": list(request.modules),
                "module_results": {
                    "procurement": {"status": "passed", "tables_generated": 25, "data_quality_status": "passed"},
                    "production": {"status": "passed", "tables_generated": 21, "data_quality_status": "passed"},
                },
                "warnings": [],
                "errors": [],
            }

    monkeypatch.setattr(pipeline_routes, "pipeline_service", FakeService())

    response = client.post(
        "/api/pipeline/run-generic",
        data={
            "modules": "procurement,production",
            "scenario_text": "Packaged food/snack manufacturing",
            "seed": "42",
            "profile_id": "food_manufacturing",
            "build_prompt": "true",
            "allow_demo_fallback": "false",
        },
    )

    assert response.status_code == 200
    assert captured["request"].modules == ("procurement", "production")
    assert captured["request"].scenario_text == "Packaged food/snack manufacturing"
    assert captured["request"].profile_id == "food_manufacturing"
    assert captured["request"].build_prompt is True


def test_generic_pipeline_api_splits_combined_metadata_and_erd_before_module_execution(tmp_path, monkeypatch) -> None:
    procurement_metadata = pd.read_excel(ROOT / "input" / "procurement_v2_metadata.xlsx", sheet_name="Metadata", engine="openpyxl", dtype=object)
    production_metadata = pd.read_excel(ROOT / "input" / "production_v1_metadata.xlsx", sheet_name="Metadata", engine="openpyxl", dtype=object)
    combined_metadata = pd.concat([procurement_metadata, production_metadata], ignore_index=True)
    combined_file = BytesIO()
    with pd.ExcelWriter(combined_file, engine="openpyxl") as writer:
        combined_metadata.to_excel(writer, sheet_name="Metadata", index=False)
    combined_file.seek(0)
    combined_erd = "\n".join(
        [
            (ROOT / "input" / "procurement_v2_erd.mmd").read_text(encoding="utf-8"),
            (ROOT / "input" / "production_v1_erd.mmd").read_text(encoding="utf-8").replace("erDiagram", "", 1),
        ]
    )
    captured = {}

    class FakeGenericRunner:
        def run(self, spec):
            captured["spec"] = spec
            proc_df = pd.read_excel(spec.module_inputs["procurement"].metadata_path, sheet_name="Metadata", engine="openpyxl", dtype=object)
            prod_df = pd.read_excel(spec.module_inputs["production"].metadata_path, sheet_name="Metadata", engine="openpyxl", dtype=object)
            captured["procurement_tables"] = proc_df["TableName"].nunique()
            captured["production_tables"] = prod_df["TableName"].nunique()
            captured["procurement_roles"] = set(proc_df["TableRole"].dropna())
            captured["production_roles"] = set(prod_df["TableRole"].dropna())
            captured["procurement_erd"] = Path(spec.module_inputs["procurement"].erd_path).read_text(encoding="utf-8")
            captured["production_erd"] = Path(spec.module_inputs["production"].erd_path).read_text(encoding="utf-8")
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
                },
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run-generic",
        data={
            "modules": "procurement,production",
            "scenario_text": "Packaged food/snack manufacturing",
            "profile_id": "food_manufacturing",
            "build_prompt": "true",
            "allow_demo_fallback": "false",
        },
        files={
            "metadata_file": (
                "food_manufacturing_procurement_production_metadata.xlsx",
                combined_file.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "erd_file": (
                "food_manufacturing_procurement_production_erd.mmd",
                combined_erd.encode("utf-8"),
                "text/plain",
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["module_ids"] == ["procurement", "production"]
    assert captured["spec"].module_ids == ("procurement", "production")
    assert captured["spec"].generation_config.profile_id == "food_manufacturing"
    assert captured["procurement_tables"] == 25
    assert captured["production_tables"] == 21
    assert "product_master" not in captured["procurement_roles"]
    assert "supplier_master" not in captured["production_roles"]
    assert "SupplierMaster ||--o{ SupplierComponent" in captured["procurement_erd"]
    assert "ProductMaster ||--o{ BOMHeader" not in captured["procurement_erd"]
    assert "ProductionOrderHdr ||--o{ ProductionOrderLine" in captured["production_erd"]
    assert "InventoryReceiptDetail ||--o{ MaterialIssueLine" in captured["production_erd"]
    assert "SupplierQuotation ||--o{ PurchaseOrderHdr" not in captured["production_erd"]


def test_generic_pipeline_service_rejects_production_only_without_fallback(tmp_path) -> None:
    service = PipelineService(base_folder=tmp_path)

    response = client.post("/api/pipeline/run-generic", json={"modules": ["production"]})

    assert response.status_code == 400
    assert "Production requires Procurement upstream data" in response.json()["detail"]


def test_generic_pipeline_service_allows_production_only_with_fallback(tmp_path, monkeypatch) -> None:
    class FakeGenericRunner:
        def run(self, spec):
            return GenericPipelineRunResult(
                status="passed_with_warnings",
                module_ids=spec.module_ids,
                output_folder=spec.output_folder,
                module_results={
                    "production": ModulePipelineRunResult(
                        module_id="production",
                        status="passed_with_warnings",
                        output_folder=spec.output_folder,
                        tables_generated=21,
                        data_quality_status="passed_with_warnings",
                    )
                },
                warnings=["Production used demo fallback upstream data."],
            )

    service = PipelineService(base_folder=tmp_path, generic_runner_factory=lambda: FakeGenericRunner())
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run-generic", json={"modules": ["production"], "allow_demo_fallback": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["module_ids"] == ["production"]
    assert payload["module_results"]["production"]["tables_generated"] == 21
    assert "fallback" in " ".join(payload["warnings"]).lower()
