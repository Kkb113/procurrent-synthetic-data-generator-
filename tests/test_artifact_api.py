from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes import artifact_routes
from app.services.artifact_service import ArtifactService


client = TestClient(app)


def _make_run(base: Path, run_id: str = "web_run_test") -> Path:
    pipeline = base / run_id / "pipeline_output" / "run_1"
    reports = pipeline / "reports"
    final_data = pipeline / "final_data"
    reports.mkdir(parents=True, exist_ok=True)
    final_data.mkdir(parents=True, exist_ok=True)
    (reports / "pipeline_run_report.json").write_text(json.dumps({"run_id": "run_1", "status": "passed"}), encoding="utf-8")
    (reports / "audit_report.md").write_text("# Audit Report", encoding="utf-8")
    (reports / "audit_report.json").write_text(json.dumps({"final_status": {"status": "passed"}}), encoding="utf-8")
    (final_data / "SupplierMaster.csv").write_text("SupplierID,SupplierName\n1,Apex Supplies\n", encoding="utf-8")
    return pipeline


def _make_generic_run(base: Path, run_id: str = "web_run_generic") -> Path:
    pipeline = base / run_id / "pipeline_output"
    reports = pipeline / "reports"
    final_data = pipeline / "final_data"
    reports.mkdir(parents=True, exist_ok=True)
    final_data.mkdir(parents=True, exist_ok=True)
    (reports / "row_budget_report.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    (reports / "row_count_audit.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    (pipeline / "procurement" / "run_1" / "reports").mkdir(parents=True, exist_ok=True)
    (pipeline / "procurement" / "run_1" / "reports" / "llm_planning_report.json").write_text("{}", encoding="utf-8")
    (final_data / "SupplierMaster.csv").write_text("SupplierID,SupplierName\n1,Apex Supplies\n", encoding="utf-8")
    return pipeline


def test_artifact_endpoint_returns_404_for_unknown_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get("/api/artifacts/web_run_missing/audit-md")

    assert response.status_code == 404


def test_artifact_endpoint_blocks_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get("/api/artifacts/..%2Fsecret/audit-md")

    assert response.status_code in {404, 422}


def test_artifact_endpoint_returns_audit_markdown(tmp_path: Path, monkeypatch) -> None:
    _make_run(tmp_path)
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get("/api/artifacts/web_run_test/audit-md")

    assert response.status_code == 200
    assert b"Audit Report" in response.content


def test_final_data_zip_endpoint_creates_zip(tmp_path: Path, monkeypatch) -> None:
    _make_run(tmp_path)
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get("/api/artifacts/web_run_test/final-data-zip")

    assert response.status_code == 200
    zip_path = tmp_path / "web_run_test" / "pipeline_output" / "run_1" / "reports" / "final_data.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        assert "SupplierMaster.csv" in archive.namelist()


def test_get_pipeline_run_summary(tmp_path: Path, monkeypatch) -> None:
    _make_run(tmp_path)
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get("/api/pipeline/runs/web_run_test")

    assert response.status_code == 200
    assert response.json()["status"] == "passed"


def test_generic_lifecycle_artifact_endpoints(tmp_path: Path, monkeypatch) -> None:
    _make_generic_run(tmp_path)
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    row_budget = client.get("/api/artifacts/web_run_generic/row-budget-report")
    row_count = client.get("/api/artifacts/web_run_generic/row-count-audit")
    llm_report = client.get("/api/artifacts/web_run_generic/llm-planning-report")
    zip_response = client.get("/api/artifacts/web_run_generic/final-data-zip")

    assert row_budget.status_code == 200
    assert row_count.status_code == 200
    assert llm_report.status_code == 200
    assert zip_response.status_code == 200
