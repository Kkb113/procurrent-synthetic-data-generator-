from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_get_root_returns_200() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "MES Synthetic Data Generator" in response.text
    assert 'name="model_version"' in response.text
    assert "Procurement v2" in response.text
    assert 'name="module_production"' in response.text


def test_static_files_are_mounted() -> None:
    response = client.get("/static/css/style.css")

    assert response.status_code == 200
    assert "Procurement Data Generator" not in response.text
    assert "body" in response.text
