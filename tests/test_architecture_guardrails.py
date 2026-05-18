from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.modules.registry import create_default_module_registry
from procurement_data_generator.core.pipeline.generic_runner import ModuleDependencyError, PipelineRunSpec, SyntheticDataPipelineRunner


ROOT = Path(__file__).resolve().parents[1]


def test_generic_runner_does_not_import_concrete_generators() -> None:
    source = (ROOT / "procurement_data_generator" / "core" / "pipeline" / "generic_runner.py").read_text(encoding="utf-8")

    forbidden = [
        "ProcurementMasterDataGenerator",
        "ProcurementTransactionGenerator",
        "ProductionMasterDataGenerator",
        "ProductionTransactionGenerator",
        "SalesMasterDataGenerator",
        "SalesTransactionGenerator",
    ]
    for token in forbidden:
        assert token not in source


def test_core_prompt_builder_has_generic_mes_system_message() -> None:
    source = (ROOT / "procurement_data_generator" / "core" / "llm" / "prompt_builder.py").read_text(encoding="utf-8")

    assert "MES synthetic data planning assistant" in source
    assert "procurement data planning assistant" not in source.lower()


def test_default_registry_contains_registered_platform_modules() -> None:
    assert create_default_module_registry().list_modules() == ("procurement", "production", "sales")


def test_production_only_generic_run_without_fallback_fails_clearly(tmp_path: Path) -> None:
    spec = PipelineRunSpec(
        module_ids=("production",),
        metadata_path="input/production_v1_metadata.xlsx",
        erd_path="input/production_v1_erd.mmd",
        scenario_path="input/production_v1_business_scenario.txt",
        plan_path="input/sample_generation_plan_production_v1_valid.json",
        output_folder=str(tmp_path),
    )

    with pytest.raises(ModuleDependencyError, match="requires Procurement upstream data"):
        SyntheticDataPipelineRunner().run(spec)


def test_docs_include_phase9_run_and_test_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")

    assert "python scripts/run_pipeline.py --modules procurement,production" in readme
    assert 'pytest -m "not sql and not llm" -q' in testing
