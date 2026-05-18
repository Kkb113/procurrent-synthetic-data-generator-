from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.pipeline.generic_runner import (
    ModuleDependencyError,
    ModulePipelineInput,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)


ROOT = Path(__file__).resolve().parents[1]
PROC_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROC_ERD = ROOT / "input" / "procurement_v2_erd.mmd"
PROC_SCENARIO = ROOT / "input" / "procurement_v2_business_scenario.txt"
PROC_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PROD_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PROD_ERD = ROOT / "input" / "production_v1_erd.mmd"
PROD_SCENARIO = ROOT / "input" / "production_v1_business_scenario.txt"
PROD_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"


@pytest.mark.pipeline
def test_generic_runner_executes_procurement_then_production(tmp_path: Path) -> None:
    result = SyntheticDataPipelineRunner().run(_multi_module_spec(tmp_path))

    assert result.status in {"passed", "passed_with_warnings"}
    assert result.module_ids == ("procurement", "production")
    assert tuple(result.module_results) == ("procurement", "production")

    procurement = result.module_results["procurement"]
    production = result.module_results["production"]
    assert procurement.tables_generated == 25
    assert production.tables_generated == 21
    assert production.data_quality_status in {"passed", "passed_with_warnings"}

    procurement_final = Path(procurement.output_folder) / "final_data"
    production_final = Path(production.output_folder) / "final_data"
    assert len(list(procurement_final.glob("*.csv"))) == 25
    assert len(list(production_final.glob("*.csv"))) == 21
    assert len(pd.read_csv(production_final / "ProductionGenealogy.csv")) > 0


@pytest.mark.pipeline
def test_generic_runner_rejects_production_only_without_upstream(tmp_path: Path) -> None:
    spec = PipelineRunSpec(
        module_ids=("production",),
        metadata_path=str(PROD_METADATA),
        erd_path=str(PROD_ERD),
        scenario_path=str(PROD_SCENARIO),
        plan_path=str(PROD_PLAN),
        output_folder=str(tmp_path),
        seed=42,
        generation_config=GenerationConfig(seed=42, allow_demo_fallback=False),
    )

    with pytest.raises(ModuleDependencyError, match="requires Procurement upstream data"):
        SyntheticDataPipelineRunner().run(spec)


@pytest.mark.pipeline
def test_generic_runner_allows_production_only_with_explicit_demo_fallback(tmp_path: Path) -> None:
    spec = PipelineRunSpec(
        module_ids=("production",),
        metadata_path=str(PROD_METADATA),
        erd_path=str(PROD_ERD),
        scenario_path=str(PROD_SCENARIO),
        plan_path=str(PROD_PLAN),
        output_folder=str(tmp_path),
        seed=42,
        generation_config=GenerationConfig(seed=42, allow_demo_fallback=True),
    )

    result = SyntheticDataPipelineRunner().run(spec)

    assert result.status in {"passed", "passed_with_warnings"}
    assert result.module_results["production"].tables_generated == 21
    assert any("demo fallback upstream" in warning for warning in result.warnings)


def test_generic_runner_uses_production_plugin_upstream_requirements() -> None:
    plugin = SyntheticDataPipelineRunner().module_registry.get("production")
    requirements = plugin.get_upstream_requirements()

    assert requirements[0].module_id == "procurement"
    assert "InventoryReceiptDetail" in requirements[0].table_names
    assert "InventoryTransaction" in requirements[0].table_names


def _multi_module_spec(tmp_path: Path) -> PipelineRunSpec:
    return PipelineRunSpec(
        module_ids=("procurement", "production"),
        metadata_path=str(PROC_METADATA),
        erd_path=str(PROC_ERD),
        scenario_path=str(PROC_SCENARIO),
        plan_path=str(PROC_PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=False,
        model_version="v2",
        module_inputs={
            "procurement": ModulePipelineInput(
                metadata_path=str(PROC_METADATA),
                erd_path=str(PROC_ERD),
                scenario_path=str(PROC_SCENARIO),
                plan_path=str(PROC_PLAN),
                model_version="v2",
            ),
            "production": ModulePipelineInput(
                metadata_path=str(PROD_METADATA),
                erd_path=str(PROD_ERD),
                scenario_path=str(PROD_SCENARIO),
                plan_path=str(PROD_PLAN),
                model_version="production_v1",
            ),
        },
    )
