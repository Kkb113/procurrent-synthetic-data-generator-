from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_sales_frontend_is_active_and_default_selected() -> None:
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "MES Synthetic Data Generator" in text
    assert "Generate validated Procurement &rarr; Production &rarr; Sales synthetic MES data" in text
    assert 'name="module_procurement" value="procurement" checked' in text
    assert 'name="module_production" value="production" checked' in text
    assert 'name="module_sales" value="sales" checked' in text
    assert "Sales - Coming soon" not in text
    assert 'name="module_sales" value="sales" disabled' not in text
    assert 'id="modules-field" value="procurement,production,sales"' in text


def test_sales_frontend_dependency_copy_and_profile_options() -> None:
    text = client.get("/").text

    assert "Default team flow: Procurement &rarr; Production &rarr; Sales." in text
    assert "Sales requires Production finished goods and Procurement/Production lineage" in text
    assert "Production consumes Procurement output. Procurement will run first." in text
    assert "Leave unchecked for local deterministic runs" in text
    assert "Azure OpenAI environment variables" in text
    assert 'select name="profile_id"' in text
    assert 'option value="food_manufacturing" selected' in text
    assert 'option value="ev_manufacturing"' in text
    assert 'option value="generic_mes"' in text


def test_sales_frontend_javascript_enforces_sales_dependencies() -> None:
    response = client.get("/static/js/app.js?v=phase11-azure-hint")

    assert response.status_code == 200
    script = response.text
    assert "/api/pipeline/run-generic" in script
    assert 'modules.join(",") !== "procurement,production,sales"' in script
    assert "salesCheckbox.checked" in script
    assert "productionCheckbox.checked = true" in script
    assert "procurementCheckbox.checked = true" in script
    assert "azureOpenAICheckbox.checked = false" in script
    assert "AZURE_OPENAI_ENDPOINT" in script
    assert "adjusted_finished_goods_inventory" in script
