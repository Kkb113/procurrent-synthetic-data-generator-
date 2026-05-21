from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.llm.llm_client_base import LLMResponse
from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"
SCENARIO = PROJECT_ROOT / "input" / "procurement_v2_business_scenario.txt"
PLAN = PROJECT_ROOT / "input" / "sample_generation_plan_v2_valid.json"
INVALID_PLAN = PROJECT_ROOT / "input" / "sample_generation_plan_v2_invalid.json"

EXPECTED_FINAL_TABLES = {
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
}


@pytest.fixture(scope="module")
def v2_pipeline_run(tmp_path_factory):
    output = tmp_path_factory.mktemp("v2_pipeline_runs")
    return ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(output),
        seed=42,
        load_sql=False,
        build_prompt=True,
        model_version="v2",
    )


def test_v2_pipeline_runs_with_manual_plan_and_inventory(v2_pipeline_run) -> None:
    assert v2_pipeline_run.status in {"passed", "passed_with_warnings"}


def test_phase0_procurement_only_smoke_guardrail(v2_pipeline_run) -> None:
    assert v2_pipeline_run.tables_generated == 25
    assert v2_pipeline_run.total_rows_generated > 0
    assert Path(v2_pipeline_run.output_folder, "reports", "row_count_audit.json").exists()


def test_v2_pipeline_creates_run_and_data_folders(v2_pipeline_run) -> None:
    run_folder = Path(v2_pipeline_run.output_folder)
    assert run_folder.exists()
    for folder in ("master_data", "transaction_data", "formula_data", "final_data"):
        assert (run_folder / folder).exists()


def test_v2_final_data_contains_inventory_and_expected_tables(v2_pipeline_run) -> None:
    final_data = Path(v2_pipeline_run.output_folder) / "final_data"
    csv_names = {path.stem for path in final_data.glob("*.csv")}

    assert csv_names == EXPECTED_FINAL_TABLES
    assert "Inventory" in csv_names
    assert "InventoryBalance" not in csv_names
    assert (final_data / "SupplierInvoice.csv").exists()
    assert (final_data / "PaymentTransaction.csv").exists()


def test_v2_data_quality_and_audit_stages_complete_with_inventory(v2_pipeline_run) -> None:
    stages = {stage.stage_name: stage for stage in v2_pipeline_run.stages}

    assert stages["data_quality_validation"].status in {"passed", "passed_with_warnings"}
    assert stages["audit_report"].status == "passed"
    assert stages["sql_load"].status == "skipped"


def test_v2_pipeline_report_includes_model_version_and_final_tables(v2_pipeline_run) -> None:
    report_path = Path(v2_pipeline_run.output_folder) / "reports" / "pipeline_run_report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["model_version"] == "v2"
    assert payload["tables_generated"] == 25
    assert payload["data_quality_status"] in {"passed", "passed_with_warnings"}
    assert payload["sql_load_status"] == "skipped"
    assert set(payload["final_data_tables"]) == EXPECTED_FINAL_TABLES
    assert "Inventory" in payload["final_data_tables"]
    assert "InventoryBalance" not in payload["final_data_tables"]
    assert payload["audit_report_path"]


def test_v2_pipeline_report_artifacts_exist(v2_pipeline_run) -> None:
    reports = Path(v2_pipeline_run.output_folder) / "reports"

    assert (reports / "data_quality_report.json").exists()
    assert (reports / "audit_report.md").exists()
    assert (reports / "audit_report.json").exists()
    assert (reports / "row_count_audit.md").exists()
    assert (reports / "row_count_audit.json").exists()
    assert (reports / "pipeline_run_report.json").exists()


def test_v2_audit_report_lists_inventory(v2_pipeline_run) -> None:
    reports = Path(v2_pipeline_run.output_folder) / "reports"
    payload = json.loads((reports / "audit_report.json").read_text(encoding="utf-8"))
    markdown = (reports / "audit_report.md").read_text(encoding="utf-8")
    table_names = {table["table_name"] for table in payload["schema_summary"]["tables"]}

    assert payload["report_metadata"]["model_version"] == "v2"
    assert payload["generation_summary"]["tables_generated"] == 25
    assert payload["generation_summary"]["row_counts_by_table"]["Inventory"] > 0
    assert payload["generation_summary"]["row_counts_by_table"]["InventoryReceiptDetail"] > 0
    assert "Inventory" in table_names
    assert "InventoryReceiptDetail" in table_names
    assert "InventoryBalance" not in table_names
    assert "Procurement v2: 25 generated tables" in markdown
    assert "InventoryReceiptDetail: receipt-level traceability" in markdown
    assert "InventoryTransaction: inbound StockIn ledger sourced from InventoryReceiptDetail." in markdown
    assert "| Inventory | inventory | Inventory |" in markdown


def test_v2_final_data_uses_formula_data_over_transaction_data(v2_pipeline_run) -> None:
    run_folder = Path(v2_pipeline_run.output_folder)
    formula_df = pd.read_csv(run_folder / "formula_data" / "SupplierInvoice.csv")
    final_df = pd.read_csv(run_folder / "final_data" / "SupplierInvoice.csv")

    pd.testing.assert_frame_equal(formula_df, final_df)


def test_v2_pipeline_blocks_if_plan_validation_fails(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(INVALID_PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=False,
        model_version="v2",
    )

    assert report.status == "failed"
    assert report.current_stage in {"plan_shape_validation", "plan_semantic_validation"}


def test_v2_final_row_counts_match_expected_targets(v2_pipeline_run) -> None:
    final_data = Path(v2_pipeline_run.output_folder) / "final_data"
    row_counts = {path.stem: len(pd.read_csv(path)) for path in final_data.glob("*.csv")}

    assert sum(row_counts.values()) == v2_pipeline_run.total_rows_generated
    assert row_counts["SupplierMaster"] == 80
    assert row_counts["InventoryReceiptDetail"] > 0
    assert row_counts["Inventory"] > 0
    assert row_counts["SupplierQuotationLn"] == 10500
    assert row_counts["PaymentTransaction"] == 1700


def test_v2_generate_plan_mode_uses_industry_scenario_path_and_saves_artifacts(tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    scenario_payload = {
        "industry_id": "ev_manufacturing",
        "industry_name": "EV Manufacturing",
        "business_summary": "Electric vehicle component manufacturing with OEM customers.",
        "supported_domains": ["procurement", "production", "sales"],
        "procurement": {"supplier_types": ["battery supplier"], "component_categories": ["battery cells"]},
        "production": {"product_families": ["battery packs"]},
        "sales": {"customer_types": ["OEM"]},
        "shared": {"geography_terms": ["USA"], "currency": "USD"},
    }
    raw_plan = json.dumps(scenario_payload)

    class FakeLLMClient:
        def generate_plan(self, prompt: str):
            calls["prompt"] = prompt
            response = LLMResponse(
                provider="Azure OpenAI",
                deployment="mock-v2",
                status="passed",
                raw_text=raw_plan,
                extracted_json_text=raw_plan,
                parsed_json=scenario_payload,
            )
            response.complete()
            return response

    report = ProcurementPipelineRunner(llm_client_factory=lambda: FakeLLMClient()).run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=None,
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=True,
        generate_plan=True,
        model_version="v2",
    )

    run_folder = Path(report.output_folder)
    original_plan = json.loads((run_folder / "prompt" / "generated_llm_plan.json").read_text(encoding="utf-8"))
    normalized_plan = json.loads((run_folder / "prompt" / "generated_llm_plan_normalized.json").read_text(encoding="utf-8"))
    planning_report = json.loads((run_folder / "reports" / "llm_planning_report.json").read_text(encoding="utf-8"))

    assert report.status in {"passed", "passed_with_warnings"}
    assert "You are not generating data rows." in calls["prompt"]
    assert "You are not generating an executable plan." in calls["prompt"]
    assert (run_folder / "prompt" / "industry_scenario_prompt.txt").exists()
    assert (run_folder / "prompt" / "industry_scenario_raw_response.json").exists()
    assert (run_folder / "prompt" / "industry_scenario_validated.json").exists()
    assert (run_folder / "prompt" / "generated_industry_profile.json").exists()
    assert (run_folder / "prompt" / "synthesized_execution_plan.json").exists()
    assert (run_folder / "prompt" / "azure_openai_raw_response.txt").exists()
    assert (run_folder / "prompt" / "generated_llm_plan.json").exists()
    assert (run_folder / "prompt" / "generated_llm_plan_normalized.json").exists()
    assert (run_folder / "metadata" / "plan_normalization_report.json").exists()
    assert (run_folder / "reports" / "llm_response_report.json").exists()
    assert original_plan["module"] == "procurement"
    assert normalized_plan["module"] == "procurement"
    assert planning_report["validation_passed"] is True
    assert planning_report["final_industry_id"] == "ev_manufacturing"
    assert planning_report["generated_profile_path"].endswith("generated_industry_profile.json")
    assert any(stage.stage_name == "industry_scenario_planning" and stage.status == "passed" for stage in report.stages)


def test_v2_generate_plan_mode_falls_back_when_scenario_validation_fails(tmp_path: Path) -> None:
    class FakeLLMClient:
        def generate_plan(self, prompt: str):
            response = LLMResponse(
                provider="Azure OpenAI",
                deployment="mock-v2",
                status="passed",
                raw_text="{not json",
                extracted_json_text="{not json",
                parsed_json=None,
            )
            response.complete()
            return response

    report = ProcurementPipelineRunner(llm_client_factory=lambda: FakeLLMClient()).run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=None,
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        generate_plan=True,
        model_version="v2",
    )

    planning_report = json.loads((Path(report.output_folder) / "reports" / "llm_planning_report.json").read_text(encoding="utf-8"))
    scenario_plan = json.loads((Path(report.output_folder) / "prompt" / "industry_scenario_validated.json").read_text(encoding="utf-8"))

    assert report.status in {"passed", "passed_with_warnings"}
    assert planning_report["fallback_used"] is True
    assert planning_report["reason"]
    assert planning_report["final_industry_id"] == "general_manufacturing"
    assert scenario_plan["industry_id"] == "general_manufacturing"
