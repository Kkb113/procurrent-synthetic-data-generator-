from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_sales_frontend_is_active_and_default_selected() -> None:
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "MES Synthetic Data Generator" in text
    assert "Generate lifecycle-valid Procurement &rarr; Production &rarr; Sales synthetic data" in text
    assert 'name="metadata_xlsx"' in text
    assert 'name="mermaid_erd"' in text
    assert 'name="business_scenario"' in text
    assert "Sales - Coming soon" not in text
    assert 'name="module_sales" value="sales" disabled' not in text
    assert 'id="modules-field" value="procurement,production,sales"' not in text


def test_sales_frontend_hides_dependency_copy_and_profile_options() -> None:
    text = client.get("/").text

    assert "Default team flow" not in text
    assert "Sales requires Production finished goods and Procurement/Production lineage" not in text
    assert "Production consumes Procurement output" not in text
    assert 'select name="profile_id"' not in text
    assert "Azure OpenAI" in text
    assert "Build Prompt" in text
    assert "Load SQL" in text


def test_sales_frontend_javascript_runs_full_lifecycle_endpoint() -> None:
    response = client.get("/static/js/app.js?v=phase5-mes-lifecycle")

    assert response.status_code == 200
    script = response.text
    assert "/api/pipeline/run-mes" in script
    assert "module_sales" not in script
    assert "modules.join" not in script
    assert "per_module_row_counts" in script
    assert "row_budget_report" in script
