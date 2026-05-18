"""Sales / Order-to-Cash v1 master/reference data generator."""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_industry_profile_or_default
from procurement_data_generator.modules.shared.industry_profiles.profile_value_provider import IndustryProfileValueProvider


SALES_MASTER_TABLES = (
    "CustomerMaster",
    "CustomerLocation",
    "SalesChannel",
    "SalesPriceListHeader",
    "SalesPriceListLine",
)


class SalesMasterDataGenerator:
    """Generate Sales master/reference tables from profile values and upstream products."""

    def __init__(
        self,
        industry_profile: IndustryProfile | None = None,
        profile_id: str | None = None,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self.operating_scope = operating_scope or DEFAULT_OPERATING_SCOPE
        self.generation_config = generation_config or GenerationConfig()
        effective_profile_id = profile_id or self.generation_config.profile_id
        self.industry_profile = industry_profile or get_industry_profile_or_default(effective_profile_id)
        self.profile_values = IndustryProfileValueProvider(self.industry_profile)

    def generate_master_data(
        self,
        schema: SchemaContract | None = None,
        plan: Any | None = None,
        seed: int | None = None,
        upstream_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        **kwargs: Any,
    ) -> dict[str, pd.DataFrame]:
        """Generate the five Sales v1 master/reference tables only."""

        upstream = self._load_upstream_data(upstream_data or kwargs.get("upstream_dataframes"))
        product_master = self._require_product_master(upstream)
        rng = random.Random(self.generation_config.seed if seed is None else seed)

        customer_master = self._generate_customer_master(schema, rng)
        customer_location = self._generate_customer_location(schema, customer_master)
        sales_channel = self._generate_sales_channel(schema)
        price_list_header = self._generate_price_list_header(schema)
        price_list_line = self._generate_price_list_line(
            schema,
            product_master,
            price_list_header,
            self._unit_costs_by_product(upstream),
            rng,
        )

        return {
            "CustomerMaster": customer_master,
            "CustomerLocation": customer_location,
            "SalesChannel": sales_channel,
            "SalesPriceListHeader": price_list_header,
            "SalesPriceListLine": price_list_line,
        }

    def _generate_customer_master(self, schema: SchemaContract | None, rng: random.Random) -> pd.DataFrame:
        count = max(1, self._target_rows(schema, "CustomerMaster", 100))
        customer_types = self.profile_values.sales_customer_types()
        industries = self.profile_values.sales_customer_industries()
        name_terms = self.profile_values.sales_customer_name_terms()
        regions = self.profile_values.sales_regions()
        payment_terms = self.profile_values.sales_payment_terms()
        country = self.profile_values.default_country

        rows: list[dict[str, Any]] = []
        for index in range(1, count + 1):
            customer_type = customer_types[(index - 1) % len(customer_types)]
            region = regions[(index - 1) % len(regions)]
            term = name_terms[(index - 1) % len(name_terms)]
            rows.append(
                {
                    "CustomerID": index,
                    "CustomerCode": f"CUST-{index:05d}",
                    "CustomerName": f"{term} {region} {customer_type} {index:03d}",
                    "CustomerType": customer_type,
                    "Industry": industries[(index - 1) % len(industries)],
                    "Country": country,
                    "Region": region,
                    "CreditLimit": round(rng.uniform(25_000.0, 750_000.0), 2),
                    "PaymentTerms": payment_terms[(index - 1) % len(payment_terms)],
                    "CustomerStatus": self._customer_status(index),
                }
            )
        return pd.DataFrame(rows)

    def _generate_customer_location(
        self,
        schema: SchemaContract | None,
        customer_master: pd.DataFrame,
    ) -> pd.DataFrame:
        target = max(len(customer_master), self._target_rows(schema, "CustomerLocation", 150))
        locations = self.profile_values.location_catalog()
        rows: list[dict[str, Any]] = []
        location_id = 1

        for row in customer_master.itertuples(index=False):
            location = locations[(location_id - 1) % len(locations)]
            rows.append(self._customer_location_row(location_id, int(row.CustomerID), "Both", location, 1))
            location_id += 1

        customer_ids = list(customer_master["CustomerID"])
        while len(rows) < target:
            customer_id = int(customer_ids[(location_id - 1) % len(customer_ids)])
            location = locations[(location_id - 1) % len(locations)]
            rows.append(self._customer_location_row(location_id, customer_id, "Shipping", location, 0))
            location_id += 1

        return pd.DataFrame(rows)

    def _generate_sales_channel(self, schema: SchemaContract | None) -> pd.DataFrame:
        channels = self.profile_values.sales_channels()
        target = min(max(1, self._target_rows(schema, "SalesChannel", len(channels))), len(channels))
        rows: list[dict[str, Any]] = []
        for index, channel_code in enumerate(channels[:target], start=1):
            rows.append(
                {
                    "SalesChannelID": index,
                    "ChannelCode": channel_code,
                    "ChannelName": _channel_name(channel_code),
                    "ChannelType": _channel_type(channel_code),
                    "ChannelStatus": "Inactive" if index == target and target > 5 else "Active",
                }
            )
        return pd.DataFrame(rows)

    def _generate_price_list_header(self, schema: SchemaContract | None) -> pd.DataFrame:
        target = max(1, self._target_rows(schema, "SalesPriceListHeader", 2))
        year = self.operating_scope.calendar_year
        rows = [
            {
                "PriceListID": 1,
                "PriceListName": f"{year} Standard Sales Price List",
                "CurrencyCode": self.profile_values.default_currency,
                "EffectiveFromDate": date(year, 1, 1),
                "EffectiveToDate": date(year, 12, 31),
                "PriceListStatus": "Active",
            }
        ]
        if target > 1:
            rows.append(
                {
                    "PriceListID": 2,
                    "PriceListName": f"{year - 1} Standard Sales Price List",
                    "CurrencyCode": self.profile_values.default_currency,
                    "EffectiveFromDate": date(year - 1, 1, 1),
                    "EffectiveToDate": date(year - 1, 12, 31),
                    "PriceListStatus": "Expired",
                }
            )
        return pd.DataFrame(rows[:target])

    def _generate_price_list_line(
        self,
        schema: SchemaContract | None,
        product_master: pd.DataFrame,
        price_list_header: pd.DataFrame,
        unit_costs: dict[Any, float],
        rng: random.Random,
    ) -> pd.DataFrame:
        target = self._target_rows(schema, "SalesPriceListLine", len(product_master))
        product_ids = list(product_master["ProductID"].dropna().drop_duplicates())
        price_list_ids = list(price_list_header["PriceListID"])
        margin_low, margin_high = self.profile_values.sales_margin_pct_range()
        moq_low, moq_high = self.profile_values.sales_minimum_order_quantity_range()
        fallback_low, fallback_high = self.profile_values.sales_fallback_price_range()

        rows: list[dict[str, Any]] = []
        line_id = 1
        for price_list_id in price_list_ids:
            for product_id in product_ids:
                cost = unit_costs.get(product_id)
                margin_pct = rng.uniform(margin_low, margin_high)
                if cost is not None and cost > 0:
                    unit_price = round(cost * (1.0 + margin_pct), 2)
                    if unit_price <= cost:
                        unit_price = round(cost + 0.01, 2)
                else:
                    unit_price = round(rng.uniform(fallback_low, fallback_high), 2)
                rows.append(
                    {
                        "PriceListLineID": line_id,
                        "PriceListID": price_list_id,
                        "ProductID": product_id,
                        "UnitPrice": unit_price,
                        "MinimumOrderQuantity": round(rng.uniform(moq_low, moq_high), 2),
                        "DiscountPct": round(rng.uniform(0.0, 15.0), 2),
                        "LineStatus": "Active" if int(price_list_id) == 1 else "Inactive",
                    }
                )
                line_id += 1

        if target > len(rows):
            active_price_list_id = price_list_ids[0]
            cycle_index = 0
            while len(rows) < target:
                product_id = product_ids[cycle_index % len(product_ids)]
                cost = unit_costs.get(product_id)
                margin_pct = rng.uniform(margin_low, margin_high)
                unit_price = round(cost * (1.0 + margin_pct), 2) if cost is not None and cost > 0 else round(rng.uniform(fallback_low, fallback_high), 2)
                if cost is not None and cost > 0 and unit_price <= cost:
                    unit_price = round(cost + 0.01, 2)
                rows.append(
                    {
                        "PriceListLineID": line_id,
                        "PriceListID": active_price_list_id,
                        "ProductID": product_id,
                        "UnitPrice": unit_price,
                        "MinimumOrderQuantity": round(rng.uniform(moq_low, moq_high), 2),
                        "DiscountPct": round(rng.uniform(0.0, 15.0), 2),
                        "LineStatus": "Active",
                    }
                )
                line_id += 1
                cycle_index += 1

        return pd.DataFrame(rows)

    def _customer_location_row(
        self,
        location_id: int,
        customer_id: int,
        location_type: str,
        location: dict[str, str],
        is_default: int,
    ) -> dict[str, Any]:
        return {
            "CustomerLocationID": location_id,
            "CustomerID": customer_id,
            "LocationType": location_type,
            "AddressLine1": f"{100 + location_id} {location['city']} Distribution Road",
            "City": location["city"],
            "State": location["state"],
            "Country": location["country"],
            "PostalCode": location["zip"] or f"{100000 + location_id}",
            "IsDefault": is_default,
        }

    def _load_upstream_data(
        self,
        upstream_data: Mapping[str, pd.DataFrame] | str | Path | None,
    ) -> dict[str, pd.DataFrame]:
        if upstream_data is None:
            return {}
        if isinstance(upstream_data, Mapping):
            return {str(name): dataframe for name, dataframe in upstream_data.items() if isinstance(dataframe, pd.DataFrame)}

        folder = Path(upstream_data)
        loaded: dict[str, pd.DataFrame] = {}
        for table_name in ("ProductMaster", "FinishedGoodsReceipt", "ProductionCostSummary"):
            path = folder / f"{table_name}.csv"
            if path.exists():
                loaded[table_name] = pd.read_csv(path)
        return loaded

    def _require_product_master(self, upstream: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        product_master = upstream.get("ProductMaster")
        if product_master is None or product_master.empty:
            raise ValueError("Sales master generation requires upstream ProductMaster.")
        if "ProductID" not in product_master.columns:
            raise ValueError("Sales master generation requires upstream ProductMaster with ProductID.")
        if product_master["ProductID"].dropna().empty:
            raise ValueError("Sales master generation requires upstream ProductMaster with ProductID values.")
        return product_master.copy()

    def _unit_costs_by_product(self, upstream: Mapping[str, pd.DataFrame]) -> dict[Any, float]:
        for table_name, cost_column in (
            ("FinishedGoodsReceipt", "UnitCost"),
            ("ProductionCostSummary", "UnitProductionCost"),
            ("ProductMaster", "StandardCost"),
        ):
            dataframe = upstream.get(table_name)
            if dataframe is None or dataframe.empty:
                continue
            if "ProductID" not in dataframe.columns or cost_column not in dataframe.columns:
                continue
            cost_frame = dataframe[["ProductID", cost_column]].copy()
            cost_frame[cost_column] = pd.to_numeric(cost_frame[cost_column], errors="coerce")
            costs = (
                cost_frame
                .dropna()
                .groupby("ProductID", as_index=True)[cost_column]
                .mean()
                .to_dict()
            )
            return {product_id: float(cost) for product_id, cost in costs.items() if float(cost) > 0}
        return {}

    def _target_rows(self, schema: SchemaContract | None, table_name: str, default: int) -> int:
        if schema is None:
            return default
        table = schema.tables.get(table_name)
        if table is None:
            return default
        return _table_target_rows(table, default)

    @staticmethod
    def _customer_status(index: int) -> str:
        if index % 37 == 0:
            return "Inactive"
        if index % 11 == 0:
            return "Hold"
        return "Active"


def _table_target_rows(table: TableContract, default: int) -> int:
    try:
        return int(table.target_rows or default)
    except (TypeError, ValueError):
        return default


def _channel_name(channel_code: str) -> str:
    return channel_code.replace("_", " ").replace("-", " ").title()


def _channel_type(channel_code: str) -> str:
    normalized = channel_code.strip().upper()
    if "ONLINE" in normalized or "E-COMMERCE" in normalized:
        return "Online"
    if "EXPORT" in normalized:
        return "Export"
    if "DISTRIBUTOR" in normalized:
        return "Indirect"
    if "FOODSERVICE" in normalized:
        return "Foodservice"
    if "RETAIL" in normalized:
        return "Retail"
    return "Direct"
