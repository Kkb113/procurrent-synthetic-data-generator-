from __future__ import annotations

import json
from pathlib import Path

import pytest

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.pipeline.generic_runner import (
    ModulePipelineInput,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)


pytestmark = [pytest.mark.pipeline, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[1]


def test_phase4_small_analytics_lifecycle_completes_with_budget_artifacts(tmp_path: Path) -> None:
    result = SyntheticDataPipelineRunner().run(_full_chain_spec(tmp_path, target_total_rows=50_000))

    assert result.status in {"passed", "passed_with_warnings"}
    assert set(result.module_results) == {"procurement", "production", "sales"}
    assert sum(module.total_rows_generated for module in result.module_results.values()) >= 50_000

    for module_id in ("procurement", "production", "sales"):
        final_data = Path(result.module_results[module_id].output_folder) / "final_data"
        assert final_data.exists()
        assert list(final_data.glob("*.csv"))

    row_budget_path = Path(result.output_folder) / "reports" / "row_budget_report.json"
    row_count_audit_path = Path(result.output_folder) / "reports" / "row_count_audit.json"
    performance_profile_path = Path(result.module_results["production"].output_folder) / "reports" / "performance_profile_phase4.json"

    assert row_budget_path.exists()
    assert row_count_audit_path.exists()
    assert performance_profile_path.exists()

    row_budget = json.loads(row_budget_path.read_text(encoding="utf-8"))
    assert row_budget["actual_total_rows"] >= 50_000
    assert row_budget["tables"]["ProductionOrderHdr"]["actual_rows"] > 0
    assert row_budget["tables"]["SalesOrderHdr"]["actual_rows"] > 12

    performance_profile = json.loads(performance_profile_path.read_text(encoding="utf-8"))
    assert performance_profile["total_elapsed_seconds"] > 0
    assert performance_profile["top_suspected_bottleneck"]


def _full_chain_spec(tmp_path: Path, target_total_rows: int) -> PipelineRunSpec:
    return PipelineRunSpec(
        module_ids=("procurement", "production", "sales"),
        metadata_path=str(ROOT / "input" / "procurement_v2_metadata.xlsx"),
        erd_path=str(ROOT / "input" / "procurement_v2_erd.mmd"),
        scenario_path=str(ROOT / "input" / "procurement_v2_business_scenario.txt"),
        plan_path=str(ROOT / "input" / "sample_generation_plan_v2_valid.json"),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=False,
        model_version="v2",
        generation_config=GenerationConfig(
            seed=42,
            profile_id="food_manufacturing",
            target_total_rows=target_total_rows,
        ),
        module_inputs={
            "procurement": ModulePipelineInput(
                metadata_path=str(ROOT / "input" / "procurement_v2_metadata.xlsx"),
                erd_path=str(ROOT / "input" / "procurement_v2_erd.mmd"),
                scenario_path=str(ROOT / "input" / "procurement_v2_business_scenario.txt"),
                plan_path=str(ROOT / "input" / "sample_generation_plan_v2_valid.json"),
                model_version="v2",
            ),
            "production": ModulePipelineInput(
                metadata_path=str(ROOT / "input" / "production_v1_metadata.xlsx"),
                erd_path=str(ROOT / "input" / "production_v1_erd.mmd"),
                scenario_path=str(ROOT / "input" / "production_v1_business_scenario.txt"),
                plan_path=str(ROOT / "input" / "sample_generation_plan_production_v1_valid.json"),
                model_version="production_v1",
            ),
            "sales": ModulePipelineInput(
                metadata_path=str(ROOT / "input" / "sales_v1_metadata.xlsx"),
                erd_path=str(ROOT / "input" / "sales_v1_erd.mmd"),
                scenario_path=None,
                plan_path=None,
                model_version="v1",
            ),
        },
    )
