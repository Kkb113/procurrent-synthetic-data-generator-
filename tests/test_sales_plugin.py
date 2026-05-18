from __future__ import annotations

import pandas as pd
import pytest

from procurement_data_generator.core.pipeline.generic_runner import (
    ModuleExecutionNotSupportedError,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)
from procurement_data_generator.core.metadata.metadata_reader import read_metadata_schema
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.plugin import SALES_EXECUTION_NOT_IMPLEMENTED, SalesModulePlugin
from procurement_data_generator.modules.sales.transaction_generator import SalesTransactionGenerator


@pytest.mark.unit
def test_sales_plugin_identity_and_catalog() -> None:
    plugin = SalesModulePlugin()

    assert plugin.module_id == "sales"
    assert plugin.module_name == "Sales"
    assert plugin.module_version == "v1"
    assert len(plugin.get_role_catalog()) == 18
    assert "sales_shipment_traceability" in plugin.supported_table_roles


@pytest.mark.unit
def test_sales_plugin_declares_production_and_procurement_upstream_requirements() -> None:
    requirements = SalesModulePlugin().get_upstream_requirements()
    by_module = {requirement.module_id: requirement for requirement in requirements}

    assert set(by_module) == {"production", "procurement"}
    for table_name in (
        "ProductMaster",
        "FinishedGoodsInventory",
        "FinishedGoodsReceipt",
        "ProductionBatch",
        "ProductionGenealogy",
        "ProductionCostSummary",
        "MaterialIssueLine",
    ):
        assert table_name in by_module["production"].table_names
    for table_name in (
        "SupplierMaster",
        "ComponentMaster",
        "InventoryReceiptDetail",
        "InventoryTransaction",
    ):
        assert table_name in by_module["procurement"].table_names


@pytest.mark.unit
def test_sales_plugin_returns_prompt_sections_and_planned_validation_rules() -> None:
    plugin = SalesModulePlugin()

    assert plugin.get_prompt_sections()
    assert "sales_traceability_links_complete" in plugin.get_validation_rules()


@pytest.mark.unit
def test_sales_plugin_role_validation_passes_for_sales_metadata() -> None:
    schema = read_metadata_schema("input/sales_v1_metadata.xlsx")
    result = SalesModulePlugin().validate_roles(schema)

    assert result.report.is_valid
    assert result.summary.detected_roles == 18


@pytest.mark.unit
def test_sales_generator_factories_return_master_generator_and_transaction_skeleton() -> None:
    plugin = SalesModulePlugin()
    master = plugin.create_master_generator()
    transaction = plugin.create_transaction_generator()

    assert isinstance(master, SalesMasterDataGenerator)
    assert isinstance(transaction, SalesTransactionGenerator)
    dataframes = master.generate_master_data(
        upstream_data={"ProductMaster": pd.DataFrame({"ProductID": [1], "ProductName": ["Finished Product"]})}
    )
    assert set(dataframes) == {
        "CustomerMaster",
        "CustomerLocation",
        "SalesChannel",
        "SalesPriceListHeader",
        "SalesPriceListLine",
    }
    with pytest.raises(NotImplementedError, match="Sales transaction data generation is not implemented yet"):
        transaction.generate_transaction_data()


@pytest.mark.unit
def test_sales_plugin_run_pipeline_fails_clearly() -> None:
    with pytest.raises(NotImplementedError, match="Sales module is registered but execution is not implemented yet"):
        SalesModulePlugin().run_pipeline()


@pytest.mark.unit
def test_generic_runner_rejects_sales_execution_clearly(tmp_path) -> None:
    spec = PipelineRunSpec(
        module_ids=("sales",),
        metadata_path="input/production_v1_metadata.xlsx",
        erd_path="input/production_v1_erd.mmd",
        scenario_path="input/production_v1_business_scenario.txt",
        plan_path="input/sample_generation_plan_production_v1_valid.json",
        output_folder=str(tmp_path),
    )

    with pytest.raises(ModuleExecutionNotSupportedError, match=SALES_EXECUTION_NOT_IMPLEMENTED):
        SyntheticDataPipelineRunner().run(spec)
