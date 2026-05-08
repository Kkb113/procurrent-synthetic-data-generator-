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
    (final_data / "Vendor.csv").write_text("VendorID,VendorName\n1,Apex Supplies\n", encoding="utf-8")
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
        assert "Vendor.csv" in archive.namelist()


def test_get_pipeline_run_summary(tmp_path: Path, monkeypatch) -> None:
    _make_run(tmp_path)
    monkeypatch.setattr(artifact_routes, "artifact_service", ArtifactService(tmp_path))

    response = client.get("/api/pipeline/runs/web_run_test")

    assert response.status_code == 200
    assert response.json()["status"] == "passed"
