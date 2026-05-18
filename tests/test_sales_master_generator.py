from __future__ import annotations

import re

import pandas as pd
import pytest

from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.modules.sales.master_generator import SALES_MASTER_TABLES, SalesMasterDataGenerator
from procurement_data_generator.modules.sales.plugin import SalesModulePlugin
from procurement_data_generator.modules.shared.industry_profiles import FOOD_MANUFACTURING_PROFILE


pytestmark = pytest.mark.unit


def test_sales_master_generator_creates_only_approved_master_tables() -> None:
    dataframes = _generate_food_sales_master()

    assert tuple(dataframes) == SALES_MASTER_TABLES
    assert set(dataframes) == {
        "CustomerMaster",
        "CustomerLocation",
        "SalesChannel",
        "SalesPriceListHeader",
        "SalesPriceListLine",
    }
    assert "SalesOrderHdr" not in dataframes
    assert "SalesShipmentTraceability" not in dataframes


def test_customer_master_uses_food_profile_vocabulary_without_ev_leakage() -> None:
    customer_master = _generate_food_sales_master()["CustomerMaster"]

    assert list(customer_master.columns) == [
        "CustomerID",
        "CustomerCode",
        "CustomerName",
        "CustomerType",
        "Industry",
        "Country",
        "Region",
        "CreditLimit",
        "PaymentTerms",
        "CustomerStatus",
    ]
    assert customer_master["CustomerID"].is_unique
    assert customer_master["CustomerCode"].is_unique
    assert len(customer_master) > 0
    assert set(customer_master["CustomerType"]).issubset(set(FOOD_MANUFACTURING_PROFILE.sales.customer_types))
    assert set(customer_master["PaymentTerms"]).issubset(set(FOOD_MANUFACTURING_PROFILE.sales.payment_terms))
    assert set(customer_master["Country"]) == {"India"}
    assert _context_row_count(customer_master, ["CustomerName", "CustomerType"], ("FreshMart", "SnackHub", "Grocery Retailer")) > 0
    _assert_ev_terms_absent(customer_master, ["CustomerName", "CustomerType", "Industry"])


def test_customer_location_references_customer_master_and_has_default_location() -> None:
    dataframes = _generate_food_sales_master()
    customer_master = dataframes["CustomerMaster"]
    customer_location = dataframes["CustomerLocation"]

    assert list(customer_location.columns) == [
        "CustomerLocationID",
        "CustomerID",
        "LocationType",
        "AddressLine1",
        "City",
        "State",
        "Country",
        "PostalCode",
        "IsDefault",
    ]
    assert customer_location["CustomerLocationID"].is_unique
    assert set(customer_location["CustomerID"]).issubset(set(customer_master["CustomerID"]))
    assert set(customer_location["LocationType"]).issubset({"Billing", "Shipping", "Both"})
    default_counts = customer_location[customer_location["IsDefault"] == 1].groupby("CustomerID").size()
    assert set(customer_master["CustomerID"]).issubset(set(default_counts.index))


def test_sales_channel_uses_food_profile_channels_without_generic_ev_leakage() -> None:
    sales_channel = _generate_food_sales_master()["SalesChannel"]

    assert sales_channel["ChannelCode"].is_unique
    assert set(sales_channel["ChannelCode"]) == set(FOOD_MANUFACTURING_PROFILE.sales.sales_channels)
    assert set(sales_channel["ChannelStatus"]).issubset({"Active", "Inactive"})
    _assert_ev_terms_absent(sales_channel, ["ChannelCode", "ChannelName", "ChannelType"])


def test_price_list_header_uses_operating_scope_year_and_profile_currency() -> None:
    price_list_header = _generate_food_sales_master()["SalesPriceListHeader"]

    active = price_list_header[price_list_header["PriceListStatus"] == "Active"]
    assert not active.empty
    assert set(price_list_header["CurrencyCode"]) == {"INR"}
    assert str(active.iloc[0]["EffectiveFromDate"]) == "2025-01-01"
    assert str(active.iloc[0]["EffectiveToDate"]) == "2025-12-31"


def test_price_list_lines_reference_product_master_and_price_above_cost() -> None:
    dataframes = _generate_food_sales_master()
    price_list_header = dataframes["SalesPriceListHeader"]
    price_list_line = dataframes["SalesPriceListLine"]
    upstream = _upstream_data()
    cost_by_product = upstream["FinishedGoodsReceipt"].set_index("ProductID")["UnitCost"].to_dict()

    assert set(price_list_line["ProductID"]).issubset(set(upstream["ProductMaster"]["ProductID"]))
    assert set(price_list_line["PriceListID"]).issubset(set(price_list_header["PriceListID"]))
    assert (price_list_line["UnitPrice"] > 0).all()
    assert (price_list_line["MinimumOrderQuantity"] >= 0).all()
    assert ((price_list_line["DiscountPct"] >= 0) & (price_list_line["DiscountPct"] <= 15)).all()
    for row in price_list_line.itertuples(index=False):
        assert row.UnitPrice > cost_by_product[row.ProductID]


def test_sales_master_generation_is_deterministic_for_same_seed_profile_and_upstream() -> None:
    generator = _food_generator()

    first = generator.generate_master_data(upstream_data=_upstream_data())
    second = generator.generate_master_data(upstream_data=_upstream_data())

    for table_name in SALES_MASTER_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])


def test_sales_master_generation_requires_upstream_product_master() -> None:
    generator = _food_generator()

    with pytest.raises(ValueError, match="Sales master generation requires upstream ProductMaster"):
        generator.generate_master_data(upstream_data={})

    with pytest.raises(ValueError, match="ProductID"):
        generator.generate_master_data(upstream_data={"ProductMaster": pd.DataFrame({"ProductName": ["Snack"]})})


def test_sales_plugin_can_create_master_generator_and_requires_upstream_for_execution(tmp_path) -> None:
    plugin = SalesModulePlugin()
    generator = plugin.create_master_generator(generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"))

    dataframes = generator.generate_master_data(upstream_data=_upstream_data())
    assert set(dataframes) == set(SALES_MASTER_TABLES)
    with pytest.raises(ValueError, match="Sales requires upstream Procurement and Production data"):
        plugin.run_pipeline(output_folder=str(tmp_path))


def _food_generator() -> SalesMasterDataGenerator:
    return SalesMasterDataGenerator(
        industry_profile=FOOD_MANUFACTURING_PROFILE,
        operating_scope=OperatingScope(calendar_year=2025),
        generation_config=GenerationConfig(seed=42, profile_id="food_manufacturing"),
    )


def _generate_food_sales_master() -> dict[str, pd.DataFrame]:
    return _food_generator().generate_master_data(upstream_data=_upstream_data())


def _upstream_data() -> dict[str, pd.DataFrame]:
    return {
        "ProductMaster": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "ProductName": ["Potato Chips", "Corn Snacks", "Seasoned Snack Mix"],
                "ProductCategory": ["Potato Chips", "Corn Snacks", "Seasoned Snack Mix"],
            }
        ),
        "FinishedGoodsReceipt": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "UnitCost": [12.0, 10.5, 13.25],
            }
        ),
        "ProductionCostSummary": pd.DataFrame(
            {
                "ProductID": [101, 102, 103],
                "UnitProductionCost": [12.25, 10.75, 13.5],
            }
        ),
    }


def _context_row_count(dataframe: pd.DataFrame, columns: list[str], terms: tuple[str, ...]) -> int:
    lowered_terms = tuple(term.lower() for term in terms)
    count = 0
    for _, row in dataframe.iterrows():
        row_text = " ".join(str(row[column]) for column in columns if column in dataframe.columns).lower()
        if any(term in row_text for term in lowered_terms):
            count += 1
    return count


def _assert_ev_terms_absent(dataframe: pd.DataFrame, columns: list[str]) -> None:
    text = " ".join(str(value) for column in columns for value in dataframe[column].dropna().tolist())
    for term in ("Battery", "Automotive", "Chassis", "Drive Unit", "Power Electronics", "Dealer", "Fleet"):
        assert term.lower() not in text.lower()
    assert re.search(r"(?<![A-Za-z])EV(?![A-Za-z])", text, flags=re.IGNORECASE) is None
