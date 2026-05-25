from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_frontend_is_generic_mes_ui() -> None:
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "MES Synthetic Data Generator" in text
    assert "Generate lifecycle-valid Procurement &rarr; Production &rarr; Sales synthetic data" in text
    assert "Run MES Lifecycle" in text
    assert 'name="metadata_xlsx"' in text
    assert 'name="mermaid_erd"' in text
    assert 'name="business_scenario"' in text
    assert "Sales - Coming soon" not in text
    assert "Production v1 runs from the dedicated command-line pipeline" not in text


def test_frontend_posts_to_mes_lifecycle_route_and_hides_dependency_controls() -> None:
    text = client.get("/").text

    assert 'action="/api/pipeline/run-mes"' in text
    assert 'data-endpoint="/api/pipeline/run-mes"' in text
    assert 'id="modules-field"' not in text
    assert "allow_demo_fallback" not in text
    assert "Sales requires Production finished goods and Procurement/Production lineage" not in text
    assert "Production consumes Procurement output" not in text
    assert "module_sales" not in text
    assert "Model Version" not in text
    assert "LLM Plan JSON" not in text
    assert "Production-specific inputs" not in text


def test_frontend_javascript_uses_mes_lifecycle_route() -> None:
    response = client.get("/static/js/app.js?v=phase5-mes-lifecycle")

    assert response.status_code == 200
    assert "/api/pipeline/run-mes" in response.text
    assert "Generating MES lifecycle data" in response.text
    assert 'fetch("/api/pipeline/run"' not in response.text


def test_frontend_allows_business_scenario_input() -> None:
    text = client.get("/").text

    assert "Business Scenario" in text
    assert "Describe the industry, products, suppliers" in text


def test_frontend_advanced_settings_are_collapsed() -> None:
    text = client.get("/").text

    assert "<summary>Advanced settings</summary>" in text
    assert 'name="target_total_rows"' in text
    assert 'name="row_scale_factor"' in text
    assert 'name="seed"' in text
    assert 'name="sql_if_table_exists"' in text
    assert 'select name="profile_id"' not in text
