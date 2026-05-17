from __future__ import annotations

from procurement_data_generator.modules.procurement.prompt_sections import get_procurement_prompt_sections


def test_procurement_prompt_sections_include_lifecycle_terms() -> None:
    text = _section_text()

    assert "Procurement v2 Exact Model" in text
    assert "PurchaseRequisition -> PurchaseReqLine -> RFQHeader -> RFQLine" in text
    assert "InventoryReceiptDetail must be planned between InspectionResult and InventoryTransaction." in text
    assert "InventoryTransaction.TransactionType must be StockIn" in text
    assert "SupplierInvoice should be generated after GoodsReceiptHeader." in text


def test_procurement_prompt_sections_include_quality_location_currency_rules() -> None:
    text = _section_text()

    assert "Rejection Reason Realism" in text
    assert "PlantCountry = USA." in text
    assert "CurrencyCode must be USD where the column exists." in text
    assert "POStatus = Received only" in text


def test_procurement_prompt_section_ids_are_stable() -> None:
    sections = get_procurement_prompt_sections()

    assert [section.section_id for section in sections] == [
        "procurement.v2.model",
        "procurement.v2.lifecycle",
        "procurement.v2.status_quality_location",
        "procurement.v2.formulas_quantities_validation",
    ]


def _section_text() -> str:
    return "\n".join(section.title + "\n" + section.content for section in get_procurement_prompt_sections())
