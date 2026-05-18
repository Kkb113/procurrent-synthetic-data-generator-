from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.pipeline.generic_runner import (
    ModuleDependencyError,
    PipelineConfigurationError,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)
from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = ROOT / "input" / "procurement_v2_erd.mmd"
SCENARIO = ROOT / "input" / "procurement_v2_business_scenario.txt"
PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
GENERIC_RUNNER = ROOT / "procurement_data_generator" / "core" / "pipeline" / "generic_runner.py"


def test_generic_runner_constructs_with_default_registry() -> None:
    runner = SyntheticDataPipelineRunner()

    assert runner.module_registry.list_modules() == ("procurement", "production", "sales")


def test_generic_runner_resolves_procurement_plugin() -> None:
    resolution = SyntheticDataPipelineRunner().resolve_modules(("procurement",))

    assert resolution.module_ids == ("procurement",)
    assert resolution.plugins[0].module_id == "procurement"
    assert resolution.plugins[0].module_version == "v2"


def test_generic_runner_resolves_production_plugin() -> None:
    resolution = SyntheticDataPipelineRunner().resolve_modules(("production",))

    assert resolution.module_ids == ("production",)
    assert resolution.plugins[0].module_id == "production"
    assert resolution.plugins[0].module_version == "v1"


def test_generic_runner_resolves_sales_plugin() -> None:
    resolution = SyntheticDataPipelineRunner().resolve_modules(("sales",))

    assert resolution.module_ids == ("sales",)
    assert resolution.plugins[0].module_id == "sales"
    assert resolution.plugins[0].module_version == "v1"


def test_generic_runner_unknown_module_raises_clear_error() -> None:
    with pytest.raises(KeyError, match="Unknown module plugin 'quality'"):
        SyntheticDataPipelineRunner().resolve_modules(("quality",))


def test_generic_runner_empty_module_list_fails_clearly() -> None:
    with pytest.raises(PipelineConfigurationError, match="At least one module_id is required"):
        SyntheticDataPipelineRunner().resolve_modules(())


def test_generic_runner_duplicate_modules_fail_clearly() -> None:
    with pytest.raises(PipelineConfigurationError, match="Duplicate module_id values"):
        SyntheticDataPipelineRunner().resolve_modules(("procurement", "Procurement"))


def test_generic_runner_rejects_production_without_upstream_by_default(tmp_path: Path) -> None:
    spec = PipelineRunSpec(
        module_ids=("production",),
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
    )

    with pytest.raises(ModuleDependencyError, match="requires Procurement upstream data"):
        SyntheticDataPipelineRunner().run(spec)


def test_generic_runner_rejects_wrong_dependency_order(tmp_path: Path) -> None:
    spec = PipelineRunSpec(
        module_ids=("production", "procurement"),
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
    )

    with pytest.raises(ModuleDependencyError, match="before Production"):
        SyntheticDataPipelineRunner().run(spec)


def test_generic_runner_rejects_sales_without_full_upstream_chain(tmp_path: Path) -> None:
    spec = PipelineRunSpec(
        module_ids=("sales",),
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
    )

    with pytest.raises(ModuleDependencyError, match="Sales requires upstream Procurement and Production data"):
        SyntheticDataPipelineRunner().run(spec)


def test_generic_runner_has_no_concrete_generator_imports() -> None:
    text = GENERIC_RUNNER.read_text(encoding="utf-8")

    assert "ProcurementMasterDataGenerator" not in text
    assert "ProcurementTransactionGenerator" not in text
    assert "ProductionMasterDataGenerator" not in text
    assert "ProductionTransactionGenerator" not in text


@pytest.mark.pipeline
def test_generic_runner_can_execute_procurement_pipeline(tmp_path: Path) -> None:
    report = SyntheticDataPipelineRunner().run_pipeline(
        module_id="procurement",
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=False,
        model_version="v2",
    )

    assert report.status in {"passed", "passed_with_warnings"}
    assert report.model_version == "v2"
    assert report.tables_generated == 25


@pytest.mark.pipeline
def test_procurement_pipeline_runner_public_interface_still_works(tmp_path: Path) -> None:
    report = ProcurementPipelineRunner().run(
        metadata_path=str(METADATA),
        erd_path=str(ERD),
        scenario_path=str(SCENARIO),
        plan_path=str(PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=False,
        build_prompt=False,
        model_version="v2",
    )

    assert report.status in {"passed", "passed_with_warnings"}
    assert report.tables_generated == 25
