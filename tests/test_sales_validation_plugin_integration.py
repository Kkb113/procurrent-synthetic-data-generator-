from __future__ import annotations

import pytest

from procurement_data_generator.core.pipeline.generic_runner import (
    ModuleDependencyError,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)
from procurement_data_generator.core.modules.registry import create_default_module_registry
from procurement_data_generator.modules.sales.plugin import SalesModulePlugin
from procurement_data_generator.modules.sales.validation_rules import SalesDataQualityEngine


pytestmark = pytest.mark.unit


def test_sales_plugin_exposes_validation_engine() -> None:
    plugin = SalesModulePlugin()

    assert isinstance(plugin.create_data_quality_engine(), SalesDataQualityEngine)
    assert "sales_finished_goods_inventory_rollup" in plugin.get_validation_rules()
    assert "sales_traceability_links_complete" in plugin.get_validation_rules()


def test_default_registry_exposes_sales_validation_capability() -> None:
    plugin = create_default_module_registry().get("sales")

    assert isinstance(plugin.create_data_quality_engine(), SalesDataQualityEngine)
    assert "sales_invoice_totals" in plugin.get_validation_rules()


def test_sales_generic_runner_still_rejects_sales_without_upstream_chain(tmp_path) -> None:
    spec = PipelineRunSpec(
        module_ids=("sales",),
        metadata_path="input/production_v1_metadata.xlsx",
        erd_path="input/production_v1_erd.mmd",
        scenario_path="input/production_v1_business_scenario.txt",
        plan_path="input/sample_generation_plan_production_v1_valid.json",
        output_folder=str(tmp_path),
    )

    with pytest.raises(ModuleDependencyError, match="Sales requires upstream Procurement and Production data"):
        SyntheticDataPipelineRunner().run(spec)
