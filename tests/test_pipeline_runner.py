from __future__ import annotations

import json
from pathlib import Path

from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"
SCENARIO = PROJECT_ROOT / "input" / "procurement_v2_business_scenario.txt"
PLAN = PROJECT_ROOT / "input" / "sample_generation_plan_v2_valid.json"
INVALID_PLAN = PROJECT_ROOT / "input" / "sample_generation_plan_v2_invalid.json"
CLI_SCRIPTS_WITH_MODEL_VERSION = [
    PROJECT_ROOT / "scripts" / "run_pipeline.py",
    PROJECT_ROOT / "scripts" / "build_llm_prompt.py",
    PROJECT_ROOT / "scripts" / "generate_llm_plan.py",
    PROJECT_ROOT / "scripts" / "generate_master_data.py",
    PROJECT_ROOT / "scripts" / "generate_transaction_data.py",
    PROJECT_ROOT / "scripts" / "execute_formulas.py",
    PROJECT_ROOT / "scripts" / "validate_generated_data.py",
    PROJECT_ROOT / "scripts" / "validate_generation_plan.py",
]


def test_pipeline_runner_uses_active_procurement_v2_inputs(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=True,
        model_version="v2",
    )

    assert report.status in {"passed", "passed_with_warnings"}
    assert report.model_version == "v2"
    assert report.tables_generated == 25

    final_data = Path(report.output_folder) / "final_data"
    csv_names = {path.name for path in final_data.glob("*.csv")}
    assert len(csv_names) == 25
    assert "InventoryReceiptDetail.csv" in csv_names
    assert "InventoryTransaction.csv" in csv_names
    assert "Inventory.csv" in csv_names
    assert "InventoryBalance.csv" not in csv_names


def test_pipeline_runner_default_model_version_is_v2(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=False,
    )

    assert report.model_version == "v2"
    assert report.tables_generated == 25


def test_cli_model_version_choices_are_v2_only() -> None:
    for script_path in CLI_SCRIPTS_WITH_MODEL_VERSION:
        text = script_path.read_text(encoding="utf-8")
        assert 'choices=["v2"]' in text
        deprecated_choice = 'choices=["' + "v" + '1", "v2"]'
        assert deprecated_choice not in text


def test_pipeline_runner_writes_v2_report_artifacts(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=True,
        model_version="v2",
    )
    reports = Path(report.output_folder) / "reports"
    payload = json.loads((reports / "pipeline_run_report.json").read_text(encoding="utf-8"))

    assert (reports / "audit_report.md").exists()
    assert (reports / "data_quality_report.json").exists()
    assert payload["model_version"] == "v2"
    assert payload["tables_generated"] == 25
    assert "InventoryBalance" not in payload["final_data_tables"]


def test_pipeline_runner_rejects_invalid_v2_plan(tmp_path: Path) -> None:
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
    assert any(stage.stage_name == "plan_semantic_validation" and stage.status == "failed" for stage in report.stages)
