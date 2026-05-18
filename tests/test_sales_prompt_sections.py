from __future__ import annotations

import pytest

from procurement_data_generator.modules.sales.prompt_sections import get_sales_prompt_sections


@pytest.mark.unit
def test_sales_prompt_sections_include_order_to_cash_and_finished_goods_guidance() -> None:
    text = _prompt_text()

    assert "Order-to-Cash" in text
    assert "FinishedGoodsInventory" in text
    assert "SalesShipmentTraceability" in text
    assert "SalesCreditMemo is excluded from Sales v1" in text
    assert "must not directly consume raw Procurement Inventory" in text


@pytest.mark.unit
def test_sales_prompt_sections_include_profile_driven_customer_channel_guidance() -> None:
    text = _prompt_text()

    assert "Customer and channel vocabulary should be industry-profile-driven" in text
    assert "Grocery Retailer" in text
    assert "Distributor" in text
    assert "Foodservice" in text
    assert "Convenience Store" in text
    assert "E-commerce" in text
    assert "Regional Wholesaler" in text


@pytest.mark.unit
def test_sales_prompt_sections_do_not_force_ev_automotive_vocabulary() -> None:
    text = _prompt_text()

    assert "Do not hardcode EV, automotive, dealer, or fleet vocabulary as generic Sales behavior." in text
    assert "EV dealer" not in text
    assert "automotive dealer" not in text
    assert "fleet customer" not in text


def _prompt_text() -> str:
    return "\n".join(section.title + "\n" + section.content for section in get_sales_prompt_sections())

