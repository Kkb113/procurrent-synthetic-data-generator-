from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.contracts.data_quality_report import DataQualityReport
from procurement_data_generator.core.contracts.sql_load_report import SQLLoadReport
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.llm.llm_client_base import LLMResponse
from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "sample_procurement_metadata_phase9.xlsx"
ERD = PROJECT_ROOT / "input" / "procurement_erd_phase9.mmd"
SCENARIO = PROJECT_ROOT / "input" / "sample_business_scenario.txt"
PLAN = PROJECT_ROOT / "input" / "sample_formula_plan_phase10.json"


@pytest.fixture(scope="module")
def pipeline_run(tmp_path_factory):
    output = tmp_path_factory.mktemp("pipeline_runs")
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(output),
        seed=42,
        load_sql=False,
        build_prompt=True,
    )
    return report


def test_pipeline_creates_run_folder(pipeline_run) -> None:
    assert Path(pipeline_run.output_folder).exists()


def test_pipeline_runs_all_required_stages_with_valid_sample_inputs(pipeline_run) -> None:
    stage_names = [stage.stage_name for stage in pipeline_run.stages]

    assert "metadata_validation" in stage_names
    assert "audit_report" in stage_names
    assert pipeline_run.status in {"passed", "passed_with_warnings"}


def test_pipeline_creates_master_data_folder(pipeline_run) -> None:
    assert (Path(pipeline_run.output_folder) / "master_data").exists()


def test_pipeline_creates_transaction_data_folder(pipeline_run) -> None:
    assert (Path(pipeline_run.output_folder) / "transaction_data").exists()


def test_pipeline_creates_formula_data_folder(pipeline_run) -> None:
    assert (Path(pipeline_run.output_folder) / "formula_data").exists()


def test_pipeline_creates_final_data_folder_with_16_tables(pipeline_run) -> None:
    final_data = Path(pipeline_run.output_folder) / "final_data"

    assert final_data.exists()
    assert len(list(final_data.glob("*.csv"))) == 16


def test_pipeline_creates_reports_folder(pipeline_run) -> None:
    assert (Path(pipeline_run.output_folder) / "reports").exists()


def test_pipeline_creates_audit_reports(pipeline_run) -> None:
    reports = Path(pipeline_run.output_folder) / "reports"

    assert (reports / "audit_report.json").exists()
    assert (reports / "audit_report.md").exists()


def test_pipeline_stops_when_metadata_validation_fails(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(PROJECT_ROOT / "input" / "phase1_invalid_metadata.xlsx"),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
    )

    assert report.status == "failed"
    assert report.current_stage == "metadata_validation"


def test_pipeline_stops_when_plan_validation_fails(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PROJECT_ROOT / "input" / "sample_llm_plan_invalid.json"),
        output_folder=str(tmp_path),
        seed=42,
    )

    assert report.status == "failed"
    assert report.current_stage == "plan_shape_validation"


def test_pipeline_skips_sql_when_load_sql_false(pipeline_run) -> None:
    sql_stage = next(stage for stage in pipeline_run.stages if stage.stage_name == "sql_load")

    assert sql_stage.status == "skipped"


def test_pipeline_calls_sql_loader_when_load_sql_true(tmp_path: Path) -> None:
    calls = {"count": 0}

    class FakeLoader:
        def __init__(self, config):
            self.config = config

        def load_dataset(self, dataframes, schema, validation_report_path=None, allow_unvalidated_load=False):
            calls["count"] += 1
            report = SQLLoadReport()
            report.tables_created = list(dataframes)
            report.tables_loaded = list(dataframes)
            report.rows_inserted_by_table = {table: len(df) for table, df in dataframes.items()}
            report.complete()
            return report

    report = ProcurementPipelineRunner(sql_loader_factory=FakeLoader).run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=True,
    )

    assert calls["count"] == 1
    assert any(stage.stage_name == "sql_load" and stage.status == "passed" for stage in report.stages)


def test_pipeline_blocks_sql_load_when_data_quality_failed(tmp_path: Path, monkeypatch) -> None:
    calls = {"sql": 0}

    class FakeQualityEngine:
        def validate_and_reconcile(self, dataframes, schema, plan=None):
            report = DataQualityReport()
            report.record_check(False)
            report.add_issue(
                "error",
                "TEST_FAILURE",
                "Synthetic failure.",
                "Fix test data.",
                table_name="PurchaseOrderLine",
                column_name="LineAmount",
            )
            return report

    class FakeLoader:
        def __init__(self, config):
            self.config = config

        def load_dataset(self, *args, **kwargs):
            calls["sql"] += 1
            report = SQLLoadReport()
            report.complete()
            return report

    monkeypatch.setattr("procurement_data_generator.core.pipeline.pipeline_runner.ProcurementDataQualityEngine", FakeQualityEngine)
    report = ProcurementPipelineRunner(sql_loader_factory=FakeLoader).run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=True,
    )

    assert report.status == "failed"
    assert calls["sql"] == 0
    assert not any(stage.stage_name == "sql_load" for stage in report.stages)
    error_text = "\n".join(report.errors)
    assert "Check: TEST_FAILURE" in error_text
    assert "Table: PurchaseOrderLine" in error_text
    assert "Column: LineAmount" in error_text
    assert "Message: Synthetic failure." in error_text
    assert "Suggested fix: Fix test data." in error_text
    payload = json.loads((Path(report.output_folder) / "reports" / "pipeline_run_report.json").read_text(encoding="utf-8"))
    persisted_error_text = "\n".join(payload["errors"])
    assert "Check: TEST_FAILURE" in persisted_error_text
    assert "Table: PurchaseOrderLine" in persisted_error_text
    assert "Column: LineAmount" in persisted_error_text


def test_pipeline_reports_master_generation_validation_issue_details(tmp_path: Path, monkeypatch) -> None:
    class FakeMasterGenerator:
        def generate_master_data(self, schema, plan, seed=None):
            report = ValidationReport()
            report.add_error(
                table_name="Vendor",
                column_name="PaymentTerms",
                message="Generated name contains an artificial numeric suffix.",
                suggested_fix="Use meaningful unique name combinations instead of numeric suffixes.",
            )
            return {}, report

    monkeypatch.setattr("procurement_data_generator.core.pipeline.pipeline_runner.ProcurementMasterDataGenerator", FakeMasterGenerator)

    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
    )

    assert report.status == "failed"
    assert report.current_stage == "master_generation"
    error_text = "\n".join(report.errors)
    assert "Table: Vendor" in error_text
    assert "Column: PaymentTerms" in error_text
    assert "Message: Generated name contains an artificial numeric suffix." in error_text
    assert "Suggested fix: Use meaningful unique name combinations instead of numeric suffixes." in error_text


def test_pipeline_final_status_passed_or_passed_with_warnings_for_valid_data(pipeline_run) -> None:
    assert pipeline_run.status in {"passed", "passed_with_warnings"}


def test_later_formula_data_overrides_transaction_data_in_final_data(pipeline_run) -> None:
    run_folder = Path(pipeline_run.output_folder)
    formula_df = pd.read_csv(run_folder / "formula_data" / "PurchaseOrderLine.csv")
    final_df = pd.read_csv(run_folder / "final_data" / "PurchaseOrderLine.csv")

    pd.testing.assert_frame_equal(formula_df, final_df)


def test_final_data_merge_uses_formula_table_when_transaction_table_is_stale(tmp_path: Path) -> None:
    runner = ProcurementPipelineRunner()
    report = _pipeline_report(tmp_path)
    master_data = {"Vendor": pd.DataFrame({"VendorID": [1], "VendorName": ["Apex Supplies"]})}
    transaction_data = {
        "PurchaseOrderLine": pd.DataFrame(
            {"PurchaseOrderLineID": [1], "OrderedQuantity": [2], "UnitPrice": [10.0], "LineAmount": [999.0]}
        )
    }
    formula_data = {
        "PurchaseOrderLine": pd.DataFrame(
            {"PurchaseOrderLineID": [1], "OrderedQuantity": [2], "UnitPrice": [10.0], "LineAmount": [20.0]}
        )
    }

    final_data = runner._run_final_data_merge(report, master_data, transaction_data, formula_data, tmp_path)

    assert final_data["PurchaseOrderLine"].loc[0, "LineAmount"] == 20.0
    final_df = pd.read_csv(tmp_path / "final_data" / "PurchaseOrderLine.csv")
    assert final_df.loc[0, "LineAmount"] == 20.0


def test_pipeline_report_includes_stages_and_timings(pipeline_run) -> None:
    report_path = Path(pipeline_run.output_folder) / "reports" / "pipeline_run_report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["stages"]
    assert all("duration_seconds" in stage for stage in payload["stages"])


def test_pipeline_generate_plan_mode_calls_mocked_azure_client(tmp_path: Path) -> None:
    calls = {"count": 0}
    plan_payload = json.loads(PLAN.read_text(encoding="utf-8"))
    plan_payload["column_generation_rules"].append(
        {
            "table_name": "Vendor",
            "column_name": "VendorName",
            "generation_type": "vendor_name",
            "strategy": "Generate vendor names.",
            "allowed_values": [],
            "min_value": None,
            "max_value": None,
            "nullable_strategy": "never_null",
            "depends_on_columns": ["InvalidCrossTableColumn"],
            "notes": None,
        }
    )
    raw_plan = json.dumps(plan_payload)

    class FakeLLMClient:
        def generate_plan(self, prompt: str):
            calls["count"] += 1
            assert "Return only valid JSON" in prompt
            response = LLMResponse(
                provider="Azure OpenAI",
                deployment="mock-deployment",
                status="passed",
                raw_text=raw_plan,
                extracted_json_text=raw_plan,
                parsed_json=plan_payload,
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
    )

    run_folder = Path(report.output_folder)

    assert calls["count"] == 1
    assert report.status in {"passed", "passed_with_warnings"}
    assert (run_folder / "prompt" / "azure_openai_raw_response.txt").exists()
    assert (run_folder / "prompt" / "generated_llm_plan.json").exists()
    assert (run_folder / "prompt" / "generated_llm_plan_normalized.json").exists()
    assert (run_folder / "reports" / "llm_response_report.json").exists()
    original_plan = json.loads((run_folder / "prompt" / "generated_llm_plan.json").read_text(encoding="utf-8"))
    normalized_plan = json.loads((run_folder / "prompt" / "generated_llm_plan_normalized.json").read_text(encoding="utf-8"))
    assert original_plan["column_generation_rules"][-1]["depends_on_columns"] == ["InvalidCrossTableColumn"]
    assert normalized_plan["column_generation_rules"][-1]["depends_on_columns"] == []
    normalization_stage = next(stage for stage in report.stages if stage.stage_name == "plan_normalization")
    assert normalization_stage.status == "passed_with_warnings"


def test_pipeline_stops_if_generated_plan_fails_validation(tmp_path: Path) -> None:
    class FakeLLMClient:
        def generate_plan(self, prompt: str):
            response = LLMResponse(
                provider="Azure OpenAI",
                deployment="mock-deployment",
                status="passed",
                raw_text='{"module": "not_procurement"}',
                extracted_json_text='{"module": "not_procurement"}',
                parsed_json={"module": "not_procurement"},
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
    )

    assert report.status == "failed"
    assert report.current_stage == "plan_shape_validation"


def test_pipeline_rejects_ambiguous_manual_and_generated_plan_sources(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        generate_plan=True,
    )

    assert report.status == "failed"
    assert report.current_stage == "plan_source"


def _pipeline_report(tmp_path: Path):
    from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport, utc_now_iso

    return PipelineRunReport(
        run_id="test_run",
        started_at=utc_now_iso(),
        input_files={},
        output_folder=str(tmp_path),
    )
