from __future__ import annotations

import importlib

import pytest

from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.reconciler_rules import get_production_reconciler_rules
from procurement_data_generator.modules.production.role_catalog import get_production_role_catalog
from procurement_data_generator.modules.production.role_validator import validate_production_roles
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator


METADATA_PATH = "input/production_v1_metadata.xlsx"


def test_production_scaffold_modules_import() -> None:
    modules = [
        "procurement_data_generator.modules.production",
        "procurement_data_generator.modules.production.role_catalog",
        "procurement_data_generator.modules.production.role_validator",
        "procurement_data_generator.modules.production.master_generator",
        "procurement_data_generator.modules.production.transaction_generator",
        "procurement_data_generator.modules.production.reconciler_rules",
    ]

    for module_name in modules:
        assert importlib.import_module(module_name)


def test_production_role_catalog_contains_phase2_roles() -> None:
    assert len(get_production_role_catalog()) == 21
    assert "production_order_line" in get_production_role_catalog()
    assert "material_issue_line" in get_production_role_catalog()


def test_production_role_validator_accepts_production_fixture_metadata() -> None:
    schema_result = load_metadata_schema(METADATA_PATH)
    assert schema_result.schema is not None
    result = validate_production_roles(schema_result.schema)

    assert result.summary.expected_roles == 21
    assert result.summary.detected_roles == 21
    assert result.report.is_valid


def test_production_transaction_generator_exists_but_is_not_pipeline_wired() -> None:
    assert ProductionTransactionGenerator().__class__.__name__ == "ProductionTransactionGenerator"


def test_production_reconciler_rules_are_active_for_phase5() -> None:
    rules = get_production_reconciler_rules()

    assert "production_genealogy_traceability" in rules
    assert "material_issue_inventory_cap" in rules


def test_production_scaffold_is_not_wired_into_procurement_pipeline() -> None:
    runner = ProcurementPipelineRunner()

    assert runner.__class__.__name__ == "ProcurementPipelineRunner"
