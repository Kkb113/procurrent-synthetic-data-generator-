from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.plugin import ProductionModulePlugin
from procurement_data_generator.modules.production.reconciler_rules import UPSTREAM_TABLES
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "production_v1_metadata.xlsx"


def test_production_plugin_exposes_identity_and_roles() -> None:
    plugin = ProductionModulePlugin()

    assert plugin.module_id == "production"
    assert plugin.module_name == "Production"
    assert plugin.module_version == "v1"
    assert "product_master" in plugin.supported_table_roles
    assert "production_genealogy" in plugin.get_role_catalog()


def test_production_plugin_creates_existing_implementations() -> None:
    plugin = ProductionModulePlugin()

    assert isinstance(plugin.create_master_generator(), ProductionMasterDataGenerator)
    assert isinstance(plugin.create_transaction_generator(), ProductionTransactionGenerator)


def test_production_plugin_reports_procurement_upstream_requirements() -> None:
    requirements = ProductionModulePlugin().get_upstream_requirements()

    assert len(requirements) == 1
    assert requirements[0].module_id == "procurement"
    assert requirements[0].table_names == UPSTREAM_TABLES
    assert requirements[0].required is True


def test_production_plugin_data_quality_engine_is_explicitly_unsupported() -> None:
    with pytest.raises(NotImplementedError, match="validate_production_generated_data"):
        ProductionModulePlugin().create_data_quality_engine()


def test_production_plugin_exposes_prompt_sections() -> None:
    sections = ProductionModulePlugin().get_prompt_sections()

    assert len(sections) >= 2
    assert sections[0].section_id == "production.v1.lifecycle"
    assert any("ProductionGenealogy" in section.content for section in sections)


@pytest.mark.integration
def test_production_plugin_validates_existing_metadata_roles() -> None:
    schema_result = load_metadata_schema(METADATA)
    assert schema_result.schema is not None

    result = ProductionModulePlugin().validate_roles(schema_result.schema)

    assert result.report.is_valid
