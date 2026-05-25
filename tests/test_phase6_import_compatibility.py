from __future__ import annotations


def test_public_generator_imports_remain_available() -> None:
    from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator
    from procurement_data_generator.modules.sales.transaction_generator import SalesTransactionGenerator
    from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator

    assert ProductionTransactionGenerator.__name__ == "ProductionTransactionGenerator"
    assert SalesTransactionGenerator.__name__ == "SalesTransactionGenerator"
    assert ProcurementTransactionGenerator.__name__ == "ProcurementTransactionGenerator"


def test_public_plugin_and_runner_imports_remain_available() -> None:
    from procurement_data_generator.core.pipeline.generic_runner import SyntheticDataPipelineRunner
    from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner
    from procurement_data_generator.modules.procurement.plugin import ProcurementModulePlugin
    from procurement_data_generator.modules.production.plugin import ProductionModulePlugin
    from procurement_data_generator.modules.sales.plugin import SalesModulePlugin

    assert SyntheticDataPipelineRunner.__name__ == "SyntheticDataPipelineRunner"
    assert ProcurementPipelineRunner.__name__ == "ProcurementPipelineRunner"
    assert ProcurementModulePlugin.__name__ == "ProcurementModulePlugin"
    assert ProductionModulePlugin.__name__ == "ProductionModulePlugin"
    assert SalesModulePlugin.__name__ == "SalesModulePlugin"


def test_public_llm_validation_imports_remain_available() -> None:
    from procurement_data_generator.core.llm.plan_validator import PlanValidationResult, PlanValidationSummary, validate_generation_plan

    assert PlanValidationResult.__name__ == "PlanValidationResult"
    assert PlanValidationSummary.__name__ == "PlanValidationSummary"
    assert callable(validate_generation_plan)
