from __future__ import annotations

from procurement_data_generator.modules.production.prompt_sections import get_production_prompt_sections


def test_production_prompt_sections_include_lifecycle_terms() -> None:
    text = _section_text()

    assert "Production v1 Lifecycle Guidance" in text
    assert "ProductionOrderHdr" in text
    assert "ProductionMaterialRequirement" in text
    assert "OperationExecution" in text
    assert "FinishedGoodsReceipt" in text
    assert "ProductionCostSummary" in text


def test_production_prompt_sections_include_traceability_terms() -> None:
    text = _section_text()

    assert "upstream Procurement data" in text
    assert "MaterialIssueLine should reference Inventory" in text
    assert "ProductionGenealogy traces finished goods" in text
    assert "InventoryReceiptDetail" in text
    assert "SupplierMaster" in text


def test_production_prompt_section_ids_are_stable() -> None:
    sections = get_production_prompt_sections()

    assert [section.section_id for section in sections] == [
        "production.v1.lifecycle",
        "production.v1.traceability",
    ]


def _section_text() -> str:
    return "\n".join(section.title + "\n" + section.content for section in get_production_prompt_sections())
