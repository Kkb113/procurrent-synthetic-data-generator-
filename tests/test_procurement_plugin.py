from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.core.validation.reconciler import ProcurementDataQualityEngine
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.plugin import ProcurementModulePlugin
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"


def test_procurement_plugin_exposes_identity_and_roles() -> None:
    plugin = ProcurementModulePlugin()

    assert plugin.module_id == "procurement"
    assert plugin.module_name == "Procurement"
    assert plugin.module_version == "v2"
    assert "supplier_master" in plugin.supported_table_roles
    assert "inventory_receipt_detail" in plugin.get_role_catalog()


def test_procurement_plugin_creates_existing_implementations() -> None:
    plugin = ProcurementModulePlugin()

    assert isinstance(plugin.create_master_generator(), ProcurementMasterDataGenerator)
    assert isinstance(plugin.create_transaction_generator(), ProcurementTransactionGenerator)
    assert isinstance(plugin.create_data_quality_engine(), ProcurementDataQualityEngine)


def test_procurement_plugin_has_no_upstream_requirements() -> None:
    assert ProcurementModulePlugin().get_upstream_requirements() == ()


def test_procurement_plugin_exposes_prompt_sections() -> None:
    sections = ProcurementModulePlugin().get_prompt_sections()

    assert len(sections) >= 2
    assert sections[0].section_id == "procurement.v2.model"
    assert any("InventoryReceiptDetail" in section.content for section in sections)


@pytest.mark.integration
def test_procurement_plugin_validates_existing_metadata_roles() -> None:
    schema_result = load_metadata_schema(METADATA)
    assert schema_result.schema is not None

    result = ProcurementModulePlugin().validate_roles(schema_result.schema)

    assert result.report.is_valid
