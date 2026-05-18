from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.contracts.sql_load_report import SQLLoadReport
from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.pipeline.generic_runner import (
    ModuleDependencyError,
    ModuleExecutionNotSupportedError,
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
def test_generic_runner_loads_procurement_and_production_to_sql_when_enabled(tmp_path: Path) -> None:
    loaded_tables: list[set[str]] = []

    class RecordingSQLLoader:
        def __init__(self, _config) -> None:
            pass

        def load_dataset(self, dataframes, schema, validation_report_path=None, allow_unvalidated_load=False):
            report = SQLLoadReport()
            report.tables_loaded = [table.table_name for table in schema.ordered_tables]
            report.rows_inserted_by_table = {
                table_name: len(dataframe)
                for table_name, dataframe in dataframes.items()
            }
            report.complete()
            loaded_tables.append(set(report.tables_loaded))
            return report

    result = SyntheticDataPipelineRunner(sql_loader_factory=RecordingSQLLoader).run(
        _multi_module_spec(tmp_path, load_sql=True)
    )

    assert result.status in {"passed", "passed_with_warnings"}
    assert len(loaded_tables) == 2
    assert len(loaded_tables[0]) == 25
    assert len(loaded_tables[1]) == 21
    assert "SupplierMaster" in loaded_tables[0]
    assert "ProductionOrderHdr" in loaded_tables[1]
    assert result.module_results["procurement"].sql_load_status == "passed"
    assert result.module_results["production"].sql_load_status == "passed"


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


def test_generic_runner_rejects_sales_in_multimodule_flow(tmp_path: Path) -> None:
    spec = _multi_module_spec(tmp_path)
    spec = PipelineRunSpec(
        module_ids=("procurement", "production", "sales"),
        metadata_path=spec.metadata_path,
        erd_path=spec.erd_path,
        scenario_path=spec.scenario_path,
        plan_path=spec.plan_path,
        output_folder=spec.output_folder,
        seed=spec.seed,
        load_sql=spec.load_sql,
        build_prompt=spec.build_prompt,
        model_version=spec.model_version,
        module_inputs=spec.module_inputs,
    )

    with pytest.raises(ModuleExecutionNotSupportedError, match="Sales module is registered but execution is not implemented yet"):
        SyntheticDataPipelineRunner().run(spec)


def _multi_module_spec(tmp_path: Path, load_sql: bool = False) -> PipelineRunSpec:
    return PipelineRunSpec(
        module_ids=("procurement", "production"),
        metadata_path=str(PROC_METADATA),
        erd_path=str(PROC_ERD),
        scenario_path=str(PROC_SCENARIO),
        plan_path=str(PROC_PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=load_sql,
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
