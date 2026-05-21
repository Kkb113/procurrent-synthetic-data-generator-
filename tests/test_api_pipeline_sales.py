from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import pipeline_routes
from app.services.pipeline_service import PipelineService
from procurement_data_generator.core.metadata.metadata_reader import METADATA_SHEET_NAME, read_metadata_schema
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
                row_count_audit_paths={"json": str(tmp_path / "row_count_audit.json")},
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
    assert payload["row_count_audit_paths"]["json"] == str(tmp_path / "row_count_audit.json")


def test_generic_sales_metadata_split_normalizes_generation_type_aliases(tmp_path) -> None:
    metadata_path = tmp_path / "combined_metadata.xlsx"
    metadata = pd.DataFrame(
        [
            _metadata_row("CustomerID", "sequence_id", key_type="PK"),
            _metadata_row("CustomerCode", "business_key"),
            _metadata_row("CustomerName", "customer_name"),
            _metadata_row("CreditLimit", "numeric_range", data_type="decimal(18,2)"),
            _metadata_row("CreatedDate", "date", data_type="date"),
            _metadata_row("CalculatedValue", "formula", data_type="decimal(18,2)"),
        ]
    )
    with pd.ExcelWriter(metadata_path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name=METADATA_SHEET_NAME, index=False)

    service = PipelineService(base_folder=tmp_path)
    split = service._split_combined_metadata_by_module(metadata_path, tmp_path, ("procurement", "production", "sales"))

    schema = read_metadata_schema(split["sales"])
    generation_types = {
        column.column_name: column.generation_type
        for column in schema.tables["CustomerMaster"].columns
    }
    assert generation_types["CustomerCode"] == "category"
    assert generation_types["CustomerName"] == "faker_company"
    assert generation_types["CreditLimit"] == "decimal_range"
    assert generation_types["CreatedDate"] == "date_range"
    assert generation_types["CalculatedValue"] == "calculated"


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


def _metadata_row(
    column_name: str,
    generation_type: str,
    *,
    data_type: str = "nvarchar(100)",
    key_type: str | None = None,
) -> dict[str, object]:
    return {
        "TableName": "CustomerMaster",
        "ProcessOrder": 1,
        "Area": "Sales",
        "TableRole": "customer_master",
        "TargetRows": 10,
        "ColumnName": column_name,
        "DataType": data_type,
        "KeyType": key_type,
        "RelatedTable": None,
        "RelatedColumn": None,
        "Nullable": "No",
        "GenerationType": generation_type,
        "AllowedValues": None,
        "MinValue": None,
        "MaxValue": None,
        "Formula": None,
    }
