from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes import artifact_routes, pipeline_routes
from app.services.artifact_service import ArtifactService
from app.services.pipeline_service import PipelineService
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport, PipelineStageReport, utc_now_iso


client = TestClient(app)


V2_TABLES = [
    "SupplierMaster",
    "SupplierComponent",
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "PurchaseRequisition",
    "PurchaseReqLine",
    "RFQHeader",
    "RFQLine",
    "SupplierQuotation",
    "SupplierQuotationLn",
    "PurchaseOrderHdr",
    "PurchaseOrderLine",
    "POSchedule",
    "ShipmentHdr",
    "ShipmentLine",
    "GoodsReceiptHeader",
    "GoodsReceiptLine",
    "IncomingInspection",
    "InspectionResult",
    "InventoryReceiptDetail",
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
]


def _files(include_metadata: bool = True, include_erd: bool = True, include_plan: bool = True):
    files = {}
    if include_metadata:
        files["metadata_file"] = ("metadata.xlsx", b"xlsx-bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if include_erd:
        files["erd_file"] = ("procurement_v2_erd.mmd", b"erDiagram\nSupplierMaster ||--o{ SupplierComponent : supplies", "text/plain")
    if include_plan:
        files["plan_file"] = ("plan.json", b'{"module": "procurement", "model_version": "v2"}', "application/json")
    return files


def _form(**overrides):
    data = {
        "scenario_text": "Generate Procurement v2 data.",
        "use_azure_openai": "false",
        "build_prompt": "true",
        "load_sql": "false",
        "if_table_exists": "replace",
        "seed": "42",
    }
    data.update(overrides)
    return data


def _fake_report(model_version: str, output_folder: str) -> PipelineRunReport:
    report = PipelineRunReport(
        run_id="run_mock",
        started_at=utc_now_iso(),
        input_files={},
        output_folder=output_folder,
        model_version=model_version,
    )
    for name in ["metadata_validation", "data_quality_validation", "audit_report", "sql_load"]:
        stage = PipelineStageReport(name)
        stage.start()
        status = "skipped" if name == "sql_load" else "passed"
        stage.finish(status, "ok")
        report.add_stage(stage)
    report.tables_generated = 25
    report.total_rows_generated = 82273
    report.data_quality_status = "passed"
    report.sql_load_status = "skipped"
    report.final_data_tables = V2_TABLES
    report.complete("passed")
    return report


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run_pipeline(self, **kwargs):
        self.calls.append(kwargs)
        output_folder = Path(kwargs["output_folder"])
        (output_folder / "reports").mkdir(parents=True, exist_ok=True)
        if kwargs["generate_plan"]:
            prompt_folder = output_folder / "prompt"
            prompt_folder.mkdir(parents=True, exist_ok=True)
            (prompt_folder / "generated_llm_plan.json").write_text("{}", encoding="utf-8")
            (prompt_folder / "azure_openai_raw_response.txt").write_text("{}", encoding="utf-8")
        return _fake_report(kwargs["model_version"], str(output_folder))


def test_ui_contains_productized_mes_lifecycle_workflow() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "MES Synthetic Data Generator" in response.text
    assert "Procurement &rarr; Production &rarr; Sales" in response.text
    assert 'action="/api/pipeline/run-mes"' in response.text
    assert 'name="metadata_xlsx"' in response.text
    assert 'name="mermaid_erd"' in response.text
    assert 'name="business_scenario"' in response.text
    assert "Run MES Lifecycle" in response.text
    assert "module_procurement" not in response.text
    assert "module_production" not in response.text
    assert "module_sales" not in response.text
    assert "Sales - Coming soon" not in response.text
    assert 'name="model_version"' not in response.text
    assert 'option value="v1"' not in response.text
    assert "LLM Plan JSON" not in response.text


def test_run_defaults_model_version_to_v2(tmp_path: Path, monkeypatch) -> None:
    fake_runner = FakeRunner()
    service = PipelineService(base_folder=tmp_path, runner_factory=lambda: fake_runner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run", data=_form(), files=_files())

    assert response.status_code == 200
    assert fake_runner.calls[0]["model_version"] == "v2"
    assert response.json()["model_version"] == "v2"


def test_run_accepts_model_version_v2_and_returns_v2_summary(tmp_path: Path, monkeypatch) -> None:
    fake_runner = FakeRunner()
    service = PipelineService(base_folder=tmp_path, runner_factory=lambda: fake_runner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run", data=_form(model_version="v2"), files=_files())

    assert response.status_code == 200
    payload = response.json()
    assert fake_runner.calls[0]["model_version"] == "v2"
    assert payload["model_version"] == "v2"
    assert payload["tables_generated"] == 25
    assert payload["total_rows_generated"] == 82273
    assert payload["data_quality_status"] == "passed"
    assert payload["sql_load_status"] == "skipped"


def test_run_rejects_invalid_model_version(tmp_path: Path, monkeypatch) -> None:
    service = PipelineService(base_folder=tmp_path, runner_factory=FakeRunner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run", data=_form(model_version="v3"), files=_files())

    assert response.status_code == 400
    assert "model_version must be v2" in response.json()["detail"]


def test_run_rejects_procurement_v1_model_version(tmp_path: Path, monkeypatch) -> None:
    service = PipelineService(base_folder=tmp_path, runner_factory=FakeRunner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post("/api/pipeline/run", data=_form(model_version="v1"), files=_files())

    assert response.status_code == 400
    assert "Procurement V1 is deprecated and no longer supported. Use Procurement V2." in response.json()["detail"]


def test_v2_azure_mode_can_submit_without_plan_file(tmp_path: Path, monkeypatch) -> None:
    fake_runner = FakeRunner()
    service = PipelineService(base_folder=tmp_path, runner_factory=lambda: fake_runner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run",
        data=_form(model_version="v2", use_azure_openai="true"),
        files=_files(include_plan=False),
    )

    assert response.status_code == 200
    assert fake_runner.calls[0]["model_version"] == "v2"
    assert fake_runner.calls[0]["generate_plan"] is True
    assert fake_runner.calls[0]["plan_path"] is None
    assert "generated_plan" in response.json()["downloads"]
    assert "raw_llm_response" in response.json()["downloads"]


def test_v2_manual_mode_requires_plan_file(tmp_path: Path, monkeypatch) -> None:
    service = PipelineService(base_folder=tmp_path, runner_factory=FakeRunner)
    monkeypatch.setattr(pipeline_routes, "pipeline_service", service)

    response = client.post(
        "/api/pipeline/run",
        data=_form(model_version="v2", use_azure_openai="false"),
        files=_files(include_plan=False),
    )

    assert response.status_code == 400
    assert "plan_file" in response.json()["detail"]


def test_v2_final_data_zip_contains_25_csv_files(tmp_path: Path, monkeypatch) -> None:
    run_id = "web_run_v2"
    pipeline = tmp_path / run_id / "pipeline_output" / "run_1"
    reports = pipeline / "reports"
    final_data = pipeline / "final_data"
    reports.mkdir(parents=True)
    final_data.mkdir(parents=True)
    (reports / "pipeline_run_report.json").write_text(json.dumps({"run_id": "run_1", "model_version": "v2", "status": "passed"}), encoding="utf-8")
    (reports / "audit_report.md").write_text("# Audit Report", encoding="utf-8")
    (reports / "audit_report.json").write_text("{}", encoding="utf-8")
    for table in V2_TABLES:
        (final_data / f"{table}.csv").write_text("ID\n1\n", encoding="utf-8")
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get(f"/api/artifacts/{run_id}/final-data-zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    zip_path = reports / "final_data.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert names == {f"{table}.csv" for table in V2_TABLES}
    assert "Inventory.csv" in names
    assert "InventoryBalance.csv" not in names
