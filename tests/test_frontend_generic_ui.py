from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_frontend_is_generic_mes_ui() -> None:
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "MES Synthetic Data Generator" in text
    assert "Run validated MES synthetic data pipelines" in text
    assert "Procurement" in text
    assert "Production" in text
    assert "Sales - Coming soon" in text
    assert "Production v1 runs from the dedicated command-line pipeline" not in text


def test_frontend_posts_to_generic_pipeline_route_and_exposes_dependency_controls() -> None:
    text = client.get("/").text

    assert 'action="/api/pipeline/run-generic"' in text
    assert 'data-endpoint="/api/pipeline/run-generic"' in text
    assert 'id="modules-field"' in text
    assert "allow_demo_fallback" in text
    assert "Production requires Procurement upstream data" in text
    assert "Production consumes Procurement output" in text
    assert "module_sales" in text
    assert "disabled" in text


def test_frontend_javascript_uses_generic_pipeline_route() -> None:
    response = client.get("/static/js/app.js?v=phase10-generic-route")

    assert response.status_code == 200
    assert "/api/pipeline/run-generic" in response.text
    assert 'fetch("/api/pipeline/run"' not in response.text


def test_frontend_allows_food_manufacturing_scenario_input() -> None:
    text = client.get("/").text

    assert "food_manufacturing" in text
    assert "packaged food/snack manufacturing" in text


def test_frontend_profile_selector_is_enabled_for_generic_runs() -> None:
    text = client.get("/").text

    assert 'select name="profile_id"' in text
    assert 'option value="ev_manufacturing" selected' in text
    assert 'option value="generic_mes"' in text
    assert 'option value="food_manufacturing"' in text
    assert 'select name="profile_id" disabled' not in text
