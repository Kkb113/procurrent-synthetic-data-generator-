"""Sales / Order-to-Cash v1 order, reservation, pick, and shipment generator."""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_industry_profile_or_default
from procurement_data_generator.modules.shared.industry_profiles.profile_value_provider import IndustryProfileValueProvider


SALES_PHASE4_TRANSACTION_TABLES = (
    "SalesOrderHdr",
    "SalesOrderLine",
    "SalesInventoryReservation",
    "SalesPickListHeader",
    "SalesPickListLine",
    "SalesShipmentHeader",
    "SalesShipmentLine",
)

SALES_PHASE5_TRANSACTION_TABLES = (
    "SalesInvoiceHeader",
    "SalesInvoiceLine",
    "CustomerPaymentReceipt",
)

SALES_PHASE6_TRANSACTION_TABLES = (
    "SalesReturnHeader",
    "SalesReturnLine",
)

SALES_PHASE4_MASTER_TABLES = (
    "CustomerMaster",
    "CustomerLocation",
    "SalesChannel",
    "SalesPriceListHeader",
    "SalesPriceListLine",
)

SALES_PHASE4_UPSTREAM_TABLES = (
    "ProductMaster",
    "FinishedGoodsInventory",
    "FinishedGoodsReceipt",
    "ProductionBatch",
)


class SalesTransactionGenerator:
    """Generate Sales v1 transactions through shipment without inventory mutation."""

    def __init__(
        self,
        sales_master_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        upstream_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        industry_profile: IndustryProfile | None = None,
        profile_id: str | None = None,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self.sales_master_data = sales_master_data
        self.upstream_data = upstream_data
        self.operating_scope = operating_scope or DEFAULT_OPERATING_SCOPE
        self.generation_config = generation_config or GenerationConfig()
        effective_profile_id = profile_id or self.generation_config.profile_id
        self.industry_profile = industry_profile or get_industry_profile_or_default(effective_profile_id)
        self.profile_values = IndustryProfileValueProvider(self.industry_profile)

    def generate_transaction_data(
        self,
        schema: SchemaContract | None = None,
        seed: int | None = None,
        sales_master_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        upstream_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        **kwargs: Any,
    ) -> dict[str, pd.DataFrame]:
        """Generate Sales Phase 4 transaction tables only."""

        master_source = _first_not_none(sales_master_data, kwargs.get("master_data"), self.sales_master_data)
        upstream_source = _first_not_none(upstream_data, kwargs.get("upstream_dataframes"), self.upstream_data)
        masters = self._load_tables(
            master_source,
            SALES_PHASE4_MASTER_TABLES,
        )
        upstream = self._load_tables(
            upstream_source,
            SALES_PHASE4_UPSTREAM_TABLES + ("ProductionCostSummary",),
        )
        self._validate_required_inputs(masters, upstream)
        rng = random.Random(self.generation_config.seed if seed is None else seed)

        context = self._build_generation_context(masters, upstream)
        rows = self._generate_rows(schema, context, rng)

        return {
            "SalesOrderHdr": pd.DataFrame(rows["SalesOrderHdr"], columns=_SALES_ORDER_HDR_COLUMNS),
            "SalesOrderLine": pd.DataFrame(rows["SalesOrderLine"], columns=_SALES_ORDER_LINE_COLUMNS),
            "SalesInventoryReservation": pd.DataFrame(rows["SalesInventoryReservation"], columns=_SALES_INVENTORY_RESERVATION_COLUMNS),
            "SalesPickListHeader": pd.DataFrame(rows["SalesPickListHeader"], columns=_SALES_PICK_LIST_HEADER_COLUMNS),
            "SalesPickListLine": pd.DataFrame(rows["SalesPickListLine"], columns=_SALES_PICK_LIST_LINE_COLUMNS),
            "SalesShipmentHeader": pd.DataFrame(rows["SalesShipmentHeader"], columns=_SALES_SHIPMENT_HEADER_COLUMNS),
            "SalesShipmentLine": pd.DataFrame(rows["SalesShipmentLine"], columns=_SALES_SHIPMENT_LINE_COLUMNS),
        }

    def generate_invoice_payment_data(
        self,
        seed: int | None = None,
        sales_master_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        sales_transaction_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        **kwargs: Any,
    ) -> dict[str, pd.DataFrame]:
        """Generate Sales Phase 5 invoice and payment tables from Phase 4 outputs."""

        master_source = _first_not_none(sales_master_data, kwargs.get("master_data"), self.sales_master_data)
        transaction_source = _first_not_none(
            sales_transaction_data,
            kwargs.get("transaction_data"),
            kwargs.get("phase4_data"),
        )
        masters = self._load_tables(
            master_source,
            ("CustomerMaster", "SalesPriceListLine"),
        )
        transactions = self._load_tables(
            transaction_source,
            SALES_PHASE4_TRANSACTION_TABLES,
        )
        self._validate_phase5_inputs(masters, transactions)
        rng = random.Random(self.generation_config.seed if seed is None else seed)
        rows = self._generate_invoice_payment_rows(masters, transactions, rng)

        return {
            "SalesInvoiceHeader": pd.DataFrame(rows["SalesInvoiceHeader"], columns=_SALES_INVOICE_HEADER_COLUMNS),
            "SalesInvoiceLine": pd.DataFrame(rows["SalesInvoiceLine"], columns=_SALES_INVOICE_LINE_COLUMNS),
            "CustomerPaymentReceipt": pd.DataFrame(rows["CustomerPaymentReceipt"], columns=_CUSTOMER_PAYMENT_RECEIPT_COLUMNS),
        }

    def generate_invoices_and_payments(self, *args: Any, **kwargs: Any) -> dict[str, pd.DataFrame]:
        """Compatibility alias for Phase 5 invoice/payment generation."""

        return self.generate_invoice_payment_data(*args, **kwargs)

    def generate_returns_data(
        self,
        seed: int | None = None,
        sales_master_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        sales_transaction_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        sales_invoice_data: Mapping[str, pd.DataFrame] | str | Path | None = None,
        **kwargs: Any,
    ) -> dict[str, pd.DataFrame]:
        """Generate low-volume Sales Phase 6 return tables from shipment outputs."""

        master_source = _first_not_none(sales_master_data, kwargs.get("master_data"), self.sales_master_data)
        transaction_source = _first_not_none(
            sales_transaction_data,
            kwargs.get("transaction_data"),
            kwargs.get("phase4_data"),
        )
        invoice_source = _first_not_none(
            sales_invoice_data,
            kwargs.get("invoice_data"),
            kwargs.get("phase5_data"),
        )
        masters = self._load_tables(master_source, ("CustomerMaster",))
        transactions = self._load_tables(transaction_source, SALES_PHASE4_TRANSACTION_TABLES + SALES_PHASE5_TRANSACTION_TABLES)
        if invoice_source is not None:
            transactions.update(self._load_tables(invoice_source, SALES_PHASE5_TRANSACTION_TABLES))
        self._validate_phase6_inputs(masters, transactions)
        rng = random.Random(self.generation_config.seed if seed is None else seed)
        rows = self._generate_return_rows(masters, transactions, rng)

        return {
            "SalesReturnHeader": pd.DataFrame(rows["SalesReturnHeader"], columns=_SALES_RETURN_HEADER_COLUMNS),
            "SalesReturnLine": pd.DataFrame(rows["SalesReturnLine"], columns=_SALES_RETURN_LINE_COLUMNS),
        }

    def generate_sales_returns(self, *args: Any, **kwargs: Any) -> dict[str, pd.DataFrame]:
        """Compatibility alias for Phase 6 return generation."""

        return self.generate_returns_data(*args, **kwargs)

    def _generate_return_rows(
        self,
        masters: Mapping[str, pd.DataFrame],
        transactions: Mapping[str, pd.DataFrame],
        rng: random.Random,
    ) -> dict[str, list[dict[str, Any]]]:
        customer_ids = set(masters["CustomerMaster"]["CustomerID"])
        order_ids = set(transactions["SalesOrderHdr"]["SalesOrderID"])
        shipment_header_by_id = _row_map(transactions["SalesShipmentHeader"], "ShipmentID")
        invoice_line_by_shipment_line = (
            _row_map(transactions["SalesInvoiceLine"], "ShipmentLineID")
            if "SalesInvoiceLine" in transactions and not transactions["SalesInvoiceLine"].empty
            else {}
        )
        eligible_lines = []
        for line in transactions["SalesShipmentLine"].sort_values("ShipmentLineID").itertuples(index=False):
            shipment = shipment_header_by_id.get(line.ShipmentID)
            if shipment is None:
                continue
            if str(shipment.ShipmentStatus).lower() == "cancelled":
                continue
            if shipment.CustomerID not in customer_ids or shipment.SalesOrderID not in order_ids:
                continue
            if float(line.ShippedQuantity) > 0:
                eligible_lines.append((shipment, line))

        rows: dict[str, list[dict[str, Any]]] = {table_name: [] for table_name in SALES_PHASE6_TRANSACTION_TABLES}
        if not eligible_lines:
            return rows

        return_low, return_high = self.profile_values.sales_return_rate_range()
        return_rate = rng.uniform(return_low, return_high)
        return_count = max(1, round(len(eligible_lines) * return_rate))
        return_count = min(return_count, len(eligible_lines))
        step = max(1, len(eligible_lines) // return_count)
        selected = [eligible_lines[index] for index in range(0, len(eligible_lines), step)][:return_count]
        return_reasons = self.profile_values.sales_return_reasons()
        restock_low, restock_high = self.profile_values.sales_restock_pct_range()

        for return_id, (shipment, shipment_line) in enumerate(selected, start=1):
            returned_quantity = _return_quantity(float(shipment_line.ShippedQuantity), rng)
            restock_pct = rng.uniform(restock_low, restock_high)
            restocked_quantity = round(returned_quantity * restock_pct, 2)
            scrapped_quantity = round(returned_quantity - restocked_quantity, 2)
            if scrapped_quantity < 0:
                scrapped_quantity = 0.0
                restocked_quantity = returned_quantity
            invoice_line = invoice_line_by_shipment_line.get(shipment_line.ShipmentLineID)
            rows["SalesReturnHeader"].append(
                {
                    "SalesReturnID": return_id,
                    "ReturnNumber": f"RTN-{return_id:06d}",
                    "CustomerID": shipment.CustomerID,
                    "SalesOrderID": shipment.SalesOrderID,
                    "ShipmentID": shipment.ShipmentID,
                    "ReturnDate": _as_date(shipment.ShipmentDate) + timedelta(days=3 + return_id),
                    "ReturnReason": return_reasons[(return_id - 1) % len(return_reasons)],
                    "ReturnStatus": "Received",
                }
            )
            rows["SalesReturnLine"].append(
                {
                    "SalesReturnLineID": return_id,
                    "SalesReturnID": return_id,
                    "ShipmentLineID": shipment_line.ShipmentLineID,
                    "ProductID": shipment_line.ProductID,
                    "ReturnedQuantity": returned_quantity,
                    "RestockedQuantity": restocked_quantity,
                    "ScrappedQuantity": scrapped_quantity,
                    "ReturnUnitValue": _return_unit_value(shipment_line, invoice_line),
                    "ReturnLineStatus": _return_line_status(restocked_quantity, scrapped_quantity),
                }
            )
        return rows

    def _generate_invoice_payment_rows(
        self,
        masters: Mapping[str, pd.DataFrame],
        transactions: Mapping[str, pd.DataFrame],
        rng: random.Random,
    ) -> dict[str, list[dict[str, Any]]]:
        customer_master = masters["CustomerMaster"]
        order_header_by_id = _row_map(transactions["SalesOrderHdr"], "SalesOrderID")
        order_line_by_id = _row_map(transactions["SalesOrderLine"], "SalesOrderLineID")
        shipment_lines_by_shipment = _rows_by_key(transactions["SalesShipmentLine"], "ShipmentID")
        payment_terms_by_customer = {
            row.CustomerID: str(row.PaymentTerms)
            for row in customer_master.itertuples(index=False)
        }
        tax_rate_pct = self.profile_values.sales_tax_rate_pct()
        freight_low, freight_high = self.profile_values.sales_freight_amount_range()
        partial_low, partial_high = self.profile_values.sales_partial_payment_pct_range()
        payment_methods = self.profile_values.sales_payment_methods()
        rows: dict[str, list[dict[str, Any]]] = {table_name: [] for table_name in SALES_PHASE5_TRANSACTION_TABLES}

        for invoice_id, shipment in enumerate(
            transactions["SalesShipmentHeader"].sort_values("ShipmentID").itertuples(index=False),
            start=1,
        ):
            shipment_lines = shipment_lines_by_shipment.get(shipment.ShipmentID, [])
            if not shipment_lines:
                continue
            order_header = order_header_by_id[shipment.SalesOrderID]
            invoice_date = _as_date(shipment.ShipmentDate) + timedelta(days=1)
            payment_terms = payment_terms_by_customer.get(shipment.CustomerID, "Net 30")
            due_date = invoice_date + timedelta(days=_payment_term_days(payment_terms))

            subtotal = 0.0
            invoice_discount = 0.0
            invoice_tax = 0.0
            for shipment_line in shipment_lines:
                order_line = order_line_by_id[shipment_line.SalesOrderLineID]
                invoice_quantity = round(float(shipment_line.ShippedQuantity), 2)
                unit_price = round(float(order_line.UnitPrice), 2)
                gross_line_amount = round(invoice_quantity * unit_price, 2)
                ordered_quantity = float(getattr(order_line, "OrderedQuantity", invoice_quantity) or invoice_quantity)
                order_discount_amount = float(getattr(order_line, "DiscountAmount", 0.0) or 0.0)
                discount_amount = round(order_discount_amount * (invoice_quantity / ordered_quantity), 2) if ordered_quantity > 0 else 0.0
                net_line_amount = round(gross_line_amount - discount_amount, 2)
                tax_amount = round(net_line_amount * tax_rate_pct / 100.0, 2)
                cogs_value = round(invoice_quantity * float(shipment_line.UnitCost), 2)
                gross_margin_amount = round(net_line_amount - cogs_value, 2)
                gross_margin_pct = round(gross_margin_amount / net_line_amount, 4) if net_line_amount > 0 else 0.0
                rows["SalesInvoiceLine"].append(
                    {
                        "InvoiceLineID": len(rows["SalesInvoiceLine"]) + 1,
                        "InvoiceID": invoice_id,
                        "ShipmentLineID": shipment_line.ShipmentLineID,
                        "SalesOrderLineID": shipment_line.SalesOrderLineID,
                        "ProductID": shipment_line.ProductID,
                        "InvoiceQuantity": invoice_quantity,
                        "UnitPrice": unit_price,
                        "DiscountAmount": discount_amount,
                        "TaxAmount": tax_amount,
                        "NetLineAmount": net_line_amount,
                        "COGSValue": cogs_value,
                        "GrossMarginAmount": gross_margin_amount,
                        "GrossMarginPct": gross_margin_pct,
                        "LineStatus": "Invoiced",
                    }
                )
                subtotal = round(subtotal + gross_line_amount, 2)
                invoice_discount = round(invoice_discount + discount_amount, 2)
                invoice_tax = round(invoice_tax + tax_amount, 2)

            freight_amount = round(rng.uniform(freight_low, freight_high), 2)
            total_invoice_amount = round(subtotal - invoice_discount + invoice_tax + freight_amount, 2)
            paid_amount = _payment_amount(invoice_id, total_invoice_amount, partial_low, partial_high, rng)
            invoice_status = _invoice_status(total_invoice_amount, paid_amount)
            rows["SalesInvoiceHeader"].append(
                {
                    "InvoiceID": invoice_id,
                    "InvoiceNumber": f"INV-{invoice_id:06d}",
                    "SalesOrderID": shipment.SalesOrderID,
                    "ShipmentID": shipment.ShipmentID,
                    "CustomerID": shipment.CustomerID,
                    "InvoiceDate": invoice_date,
                    "DueDate": due_date,
                    "CurrencyCode": str(getattr(order_header, "CurrencyCode", self.profile_values.default_currency) or self.profile_values.default_currency),
                    "SubtotalAmount": subtotal,
                    "DiscountAmount": invoice_discount,
                    "TaxAmount": invoice_tax,
                    "FreightAmount": freight_amount,
                    "TotalInvoiceAmount": total_invoice_amount,
                    "InvoiceStatus": invoice_status,
                }
            )
            if paid_amount > 0:
                rows["CustomerPaymentReceipt"].append(
                    {
                        "PaymentReceiptID": len(rows["CustomerPaymentReceipt"]) + 1,
                        "InvoiceID": invoice_id,
                        "CustomerID": shipment.CustomerID,
                        "PaymentDate": _payment_date(invoice_date, due_date, invoice_id),
                        "PaymentMethod": payment_methods[(invoice_id - 1) % len(payment_methods)],
                        "PaidAmount": paid_amount,
                        "CurrencyCode": str(getattr(order_header, "CurrencyCode", self.profile_values.default_currency) or self.profile_values.default_currency),
                        "PaymentStatus": "Received" if invoice_status == "Paid" else "Partial",
                    }
                )

        if not rows["SalesInvoiceHeader"]:
            raise ValueError("Sales invoice generation requires shipment headers with shipment lines.")
        return rows

    def _generate_rows(
        self,
        schema: SchemaContract | None,
        context: dict[str, Any],
        rng: random.Random,
    ) -> dict[str, list[dict[str, Any]]]:
        target_orders = max(1, self._target_rows(schema, "SalesOrderHdr", 12))
        target_orders = min(target_orders, max(1, len(context["customers"]) * 2))
        rows: dict[str, list[dict[str, Any]]] = {table_name: [] for table_name in SALES_PHASE4_TRANSACTION_TABLES}
        year_start = date(self.operating_scope.calendar_year, 1, 1)

        for order_id in range(1, target_orders + 1):
            allocation = self._next_allocation(context, order_id, rng)
            if allocation is None:
                break

            customer = context["customers"].iloc[(order_id - 1) % len(context["customers"])]
            location_pair = context["locations_by_customer"][customer.CustomerID]
            channel = context["channels"].iloc[(order_id - 1) % len(context["channels"])]
            order_date = year_start + timedelta(days=(order_id * 3) % 300)
            requested_ship_date = order_date + timedelta(days=2 + (order_id % 5))
            promised_ship_date = requested_ship_date + timedelta(days=1)
            pick_date = order_date + timedelta(days=1)
            shipment_date = pick_date + timedelta(days=1 + (order_id % 3))

            line_status = _line_status(allocation["ordered_quantity"], allocation["reserved_quantity"], allocation["shipped_quantity"])
            rows["SalesOrderHdr"].append(
                {
                    "SalesOrderID": order_id,
                    "SalesOrderNumber": f"SO-{order_id:06d}",
                    "CustomerID": int(customer.CustomerID),
                    "BillToLocationID": int(location_pair["bill_to"]),
                    "ShipToLocationID": int(location_pair["ship_to"]),
                    "SalesChannelID": int(channel.SalesChannelID),
                    "OrderDate": order_date,
                    "RequestedShipDate": requested_ship_date,
                    "PromisedShipDate": promised_ship_date,
                    "CurrencyCode": self.profile_values.default_currency,
                    "OrderStatus": _order_status((line_status,)),
                }
            )

            line_id = order_id
            line_amount = round(allocation["ordered_quantity"] * allocation["unit_price"], 2)
            discount_amount = round(line_amount * allocation["discount_pct"] / 100.0, 2)
            rows["SalesOrderLine"].append(
                {
                    "SalesOrderLineID": line_id,
                    "SalesOrderID": order_id,
                    "ProductID": allocation["product_id"],
                    "PlantID": allocation["plant_id"],
                    "WarehouseID": allocation["warehouse_id"],
                    "OrderedQuantity": allocation["ordered_quantity"],
                    "ReservedQuantity": allocation["reserved_quantity"],
                    "ShippedQuantity": allocation["shipped_quantity"],
                    "BackorderQuantity": round(allocation["ordered_quantity"] - allocation["shipped_quantity"], 2),
                    "UOM": allocation["uom"],
                    "UnitPrice": allocation["unit_price"],
                    "DiscountPct": allocation["discount_pct"],
                    "LineAmount": line_amount,
                    "DiscountAmount": discount_amount,
                    "NetLineAmount": round(line_amount - discount_amount, 2),
                    "LineStatus": line_status,
                }
            )

            rows["SalesInventoryReservation"].append(
                {
                    "ReservationID": order_id,
                    "SalesOrderLineID": line_id,
                    "FinishedGoodsInventoryID": allocation["finished_goods_inventory_id"],
                    "ProductID": allocation["product_id"],
                    "PlantID": allocation["plant_id"],
                    "WarehouseID": allocation["warehouse_id"],
                    "ReservationDate": order_date,
                    "ReservedQuantity": allocation["reserved_quantity"],
                    "ReleasedQuantity": 0.0,
                    "ReservationStatus": "Consumed" if allocation["shipped_quantity"] == allocation["reserved_quantity"] else "Reserved",
                }
            )

            rows["SalesPickListHeader"].append(
                {
                    "PickListID": order_id,
                    "SalesOrderID": order_id,
                    "WarehouseID": allocation["warehouse_id"],
                    "PickDate": pick_date,
                    "PickStatus": "Picked",
                }
            )
            rows["SalesPickListLine"].append(
                {
                    "PickListLineID": order_id,
                    "PickListID": order_id,
                    "SalesOrderLineID": line_id,
                    "ReservationID": order_id,
                    "ProductID": allocation["product_id"],
                    "PickedQuantity": allocation["picked_quantity"],
                    "UOM": allocation["uom"],
                    "PickLineStatus": "Picked" if allocation["picked_quantity"] == allocation["reserved_quantity"] else "ShortPicked",
                }
            )

            rows["SalesShipmentHeader"].append(
                {
                    "ShipmentID": order_id,
                    "ShipmentNumber": f"SHP-{order_id:06d}",
                    "SalesOrderID": order_id,
                    "CustomerID": int(customer.CustomerID),
                    "ShipToLocationID": int(location_pair["ship_to"]),
                    "WarehouseID": allocation["warehouse_id"],
                    "ShipmentDate": shipment_date,
                    "CarrierName": context["carrier_names"][(order_id - 1) % len(context["carrier_names"])],
                    "TrackingNumber": f"TRK{self.operating_scope.calendar_year}{order_id:08d}",
                    "ShipmentStatus": "Delivered" if order_id % 2 == 0 else "Shipped",
                }
            )
            rows["SalesShipmentLine"].append(
                {
                    "ShipmentLineID": order_id,
                    "ShipmentID": order_id,
                    "SalesOrderLineID": line_id,
                    "PickListLineID": order_id,
                    "FinishedGoodsInventoryID": allocation["finished_goods_inventory_id"],
                    "FinishedGoodsReceiptID": allocation["finished_goods_receipt_id"],
                    "ProductionBatchID": allocation["production_batch_id"],
                    "ProductID": allocation["product_id"],
                    "ShippedQuantity": allocation["shipped_quantity"],
                    "UOM": allocation["uom"],
                    "UnitCost": allocation["unit_cost"],
                    "COGSValue": round(allocation["shipped_quantity"] * allocation["unit_cost"], 2),
                    "ShipmentLineStatus": "Delivered" if order_id % 2 == 0 else "Shipped",
                }
            )

        if not rows["SalesOrderHdr"]:
            raise ValueError("Sales transaction generation requires shippable FinishedGoodsInventory and FinishedGoodsReceipt.")
        return rows

    def _next_allocation(
        self,
        context: dict[str, Any],
        line_number: int,
        rng: random.Random,
    ) -> dict[str, Any] | None:
        inventory = context["inventory"]
        for offset in range(len(inventory)):
            row_index = (line_number + offset - 1) % len(inventory)
            inventory_row = inventory.iloc[row_index]
            inventory_id = int(inventory_row.FinishedGoodsInventoryID)
            product_id = inventory_row.ProductID
            plant_id = int(inventory_row.PlantID)
            warehouse_id = int(inventory_row.WarehouseID)
            inventory_remaining = context["inventory_remaining"].get(inventory_id, 0.0)
            if inventory_remaining <= 0:
                continue
            receipt = self._matching_receipt(context, product_id, plant_id, warehouse_id)
            if receipt is None:
                continue

            receipt_id = int(receipt.FinishedGoodsReceiptID)
            capacity = min(inventory_remaining, context["receipt_remaining"][receipt_id])
            if capacity <= 0:
                continue

            base_quantity = _bounded_quantity(capacity, rng)
            if line_number % 5 == 0:
                reserved_quantity = base_quantity
                picked_quantity = base_quantity
                shipped_quantity = base_quantity
                ordered_quantity = round(base_quantity + max(1.0, min(5.0, base_quantity * 0.25)), 2)
            elif line_number % 3 == 0 and base_quantity > 1:
                reserved_quantity = base_quantity
                picked_quantity = round(max(1.0, base_quantity * 0.75), 2)
                shipped_quantity = picked_quantity
                ordered_quantity = reserved_quantity
            else:
                reserved_quantity = base_quantity
                picked_quantity = base_quantity
                shipped_quantity = base_quantity
                ordered_quantity = base_quantity

            context["inventory_remaining"][inventory_id] = round(inventory_remaining - reserved_quantity, 2)
            context["receipt_remaining"][receipt_id] = round(context["receipt_remaining"][receipt_id] - shipped_quantity, 2)
            price = context["active_price_by_product"][product_id]
            return {
                "finished_goods_inventory_id": inventory_id,
                "finished_goods_receipt_id": receipt_id,
                "production_batch_id": int(receipt.ProductionBatchID),
                "product_id": product_id,
                "plant_id": plant_id,
                "warehouse_id": warehouse_id,
                "ordered_quantity": round(ordered_quantity, 2),
                "reserved_quantity": round(reserved_quantity, 2),
                "picked_quantity": round(picked_quantity, 2),
                "shipped_quantity": round(shipped_quantity, 2),
                "uom": context["uom_by_product"].get(product_id, "EA"),
                "unit_price": float(price.UnitPrice),
                "discount_pct": float(price.DiscountPct),
                "unit_cost": float(receipt.UnitCost),
            }
        return None

    def _matching_receipt(
        self,
        context: dict[str, Any],
        product_id: Any,
        plant_id: int,
        warehouse_id: int,
    ) -> Any | None:
        receipts = context["receipts"]
        exact = receipts[
            (receipts["ProductID"] == product_id)
            & (receipts["PlantID"] == plant_id)
            & (receipts["WarehouseID"] == warehouse_id)
        ]
        product_only = receipts[receipts["ProductID"] == product_id]
        for candidate_frame in (exact, product_only):
            for receipt in candidate_frame.itertuples(index=False):
                receipt_id = int(receipt.FinishedGoodsReceiptID)
                if context["receipt_remaining"].get(receipt_id, 0.0) > 0:
                    return receipt
        return None

    def _build_generation_context(
        self,
        masters: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
    ) -> dict[str, Any]:
        customers = masters["CustomerMaster"]
        active_customers = customers[customers["CustomerStatus"].astype(str).str.lower() == "active"].copy()
        if active_customers.empty:
            active_customers = customers.copy()

        channels = masters["SalesChannel"]
        active_channels = channels[channels["ChannelStatus"].astype(str).str.lower() == "active"].copy()
        if active_channels.empty:
            active_channels = channels.copy()

        active_prices = masters["SalesPriceListLine"]
        active_prices = active_prices[active_prices["LineStatus"].astype(str).str.lower() == "active"].copy()
        if active_prices.empty:
            active_prices = masters["SalesPriceListLine"].copy()
        active_price_by_product = {row.ProductID: row for row in active_prices.drop_duplicates("ProductID").itertuples(index=False)}

        inventory = upstream["FinishedGoodsInventory"].copy()
        inventory["AvailableQuantity"] = pd.to_numeric(inventory["AvailableQuantity"], errors="coerce").fillna(0.0)
        inventory = inventory[
            (inventory["AvailableQuantity"] > 0)
            & (inventory["ProductID"].isin(active_price_by_product))
        ].copy()
        if inventory.empty:
            raise ValueError("Sales transaction generation requires shippable FinishedGoodsInventory with priced ProductID values.")

        receipts = upstream["FinishedGoodsReceipt"].copy()
        receipts["GoodQuantity"] = pd.to_numeric(receipts["GoodQuantity"], errors="coerce").fillna(0.0)
        receipts["UnitCost"] = pd.to_numeric(receipts["UnitCost"], errors="coerce").fillna(0.0)
        batch_ids = set(upstream["ProductionBatch"]["ProductionBatchID"])
        receipts = receipts[
            (receipts["GoodQuantity"] > 0)
            & (receipts["UnitCost"] > 0)
            & (receipts["ProductionBatchID"].isin(batch_ids))
        ].copy()
        if receipts.empty:
            raise ValueError("Sales transaction generation requires FinishedGoodsReceipt rows with GoodQuantity, UnitCost, and valid ProductionBatchID.")

        product_master = upstream["ProductMaster"]
        uom_by_product = {
            row.ProductID: str(getattr(row, "UOM", "EA") or "EA")
            for row in product_master.itertuples(index=False)
        }

        return {
            "customers": active_customers.reset_index(drop=True),
            "locations_by_customer": _locations_by_customer(masters["CustomerLocation"]),
            "channels": active_channels.reset_index(drop=True),
            "active_price_by_product": active_price_by_product,
            "inventory": inventory.sort_values(["ProductID", "FinishedGoodsInventoryID"]).reset_index(drop=True),
            "inventory_remaining": {
                int(row.FinishedGoodsInventoryID): float(row.AvailableQuantity)
                for row in inventory.itertuples(index=False)
            },
            "receipts": receipts.sort_values(["ProductID", "FinishedGoodsReceiptID"]).reset_index(drop=True),
            "receipt_remaining": {
                int(row.FinishedGoodsReceiptID): float(row.GoodQuantity)
                for row in receipts.itertuples(index=False)
            },
            "uom_by_product": uom_by_product,
            "carrier_names": self.profile_values.sales_carrier_names(),
        }

    def _validate_required_inputs(
        self,
        masters: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
    ) -> None:
        for table_name, columns in _REQUIRED_MASTER_COLUMNS.items():
            _require_table_columns(masters, table_name, columns, "Sales master data")
        for table_name, columns in _REQUIRED_UPSTREAM_COLUMNS.items():
            _require_table_columns(upstream, table_name, columns, "upstream Production data")

    def _validate_phase5_inputs(
        self,
        masters: Mapping[str, pd.DataFrame],
        transactions: Mapping[str, pd.DataFrame],
    ) -> None:
        _require_table_columns(masters, "CustomerMaster", _REQUIRED_PHASE5_MASTER_COLUMNS["CustomerMaster"], "Sales master data")
        for table_name, columns in _REQUIRED_PHASE5_TRANSACTION_COLUMNS.items():
            _require_table_columns(transactions, table_name, columns, "Sales Phase 4 transaction data")

    def _validate_phase6_inputs(
        self,
        masters: Mapping[str, pd.DataFrame],
        transactions: Mapping[str, pd.DataFrame],
    ) -> None:
        _require_table_columns(masters, "CustomerMaster", _REQUIRED_PHASE6_MASTER_COLUMNS["CustomerMaster"], "Sales master data")
        for table_name, columns in _REQUIRED_PHASE6_TRANSACTION_COLUMNS.items():
            _require_table_columns(transactions, table_name, columns, "Sales Phase 4 transaction data")
        if "SalesInvoiceLine" in transactions and not transactions["SalesInvoiceLine"].empty:
            missing = [
                column
                for column in _OPTIONAL_PHASE6_INVOICE_COLUMNS["SalesInvoiceLine"]
                if column not in transactions["SalesInvoiceLine"].columns
            ]
            if missing:
                raise ValueError(f"Sales transaction generation requires SalesInvoiceLine.{missing[0]}.")

    def _load_tables(
        self,
        tables: Mapping[str, pd.DataFrame] | str | Path | None,
        table_names: tuple[str, ...],
    ) -> dict[str, pd.DataFrame]:
        if tables is None:
            return {}
        if isinstance(tables, Mapping):
            return {str(name): dataframe.copy() for name, dataframe in tables.items() if isinstance(dataframe, pd.DataFrame)}

        folder = Path(tables)
        loaded: dict[str, pd.DataFrame] = {}
        for table_name in table_names:
            path = folder / f"{table_name}.csv"
            if path.exists():
                loaded[table_name] = pd.read_csv(path)
        return loaded

    def _target_rows(self, schema: SchemaContract | None, table_name: str, default: int) -> int:
        if schema is None:
            return default
        table = schema.tables.get(table_name)
        if table is None:
            return default
        return _table_target_rows(table, default)


def _require_table_columns(
    tables: Mapping[str, pd.DataFrame],
    table_name: str,
    columns: tuple[str, ...],
    label: str,
) -> None:
    dataframe = tables.get(table_name)
    if dataframe is None or dataframe.empty:
        raise ValueError(f"Sales transaction generation requires {label} {table_name}.")
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Sales transaction generation requires {table_name}.{missing[0]}.")


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _row_map(dataframe: pd.DataFrame, key_column: str) -> dict[Any, Any]:
    return {getattr(row, key_column): row for row in dataframe.itertuples(index=False)}


def _rows_by_key(dataframe: pd.DataFrame, key_column: str) -> dict[Any, list[Any]]:
    output: dict[Any, list[Any]] = {}
    for row in dataframe.itertuples(index=False):
        output.setdefault(getattr(row, key_column), []).append(row)
    return output


def _payment_term_days(payment_terms: str) -> int:
    normalized = str(payment_terms or "").strip().lower().replace(" ", "")
    if normalized in {"dueonreceipt", "cod", "cash"}:
        return 0
    digits = "".join(character for character in normalized if character.isdigit())
    if digits:
        return max(0, int(digits))
    return 30


def _payment_amount(
    invoice_id: int,
    total_invoice_amount: float,
    partial_low: float,
    partial_high: float,
    rng: random.Random,
) -> float:
    if total_invoice_amount <= 0:
        return 0.0
    if invoice_id % 10 == 0:
        return 0.0
    if invoice_id % 4 == 0:
        amount = round(total_invoice_amount * rng.uniform(partial_low, partial_high), 2)
        return min(max(0.01, amount), round(total_invoice_amount - 0.01, 2))
    return round(total_invoice_amount, 2)


def _invoice_status(total_invoice_amount: float, paid_amount: float) -> str:
    if paid_amount >= round(total_invoice_amount, 2):
        return "Paid"
    if paid_amount > 0:
        return "PartiallyPaid"
    return "Open"


def _payment_date(invoice_date: date, due_date: date, invoice_id: int) -> date:
    window = max(0, (due_date - invoice_date).days)
    if window == 0:
        return invoice_date
    return invoice_date + timedelta(days=min(window, 2 + (invoice_id % max(window, 1))))


def _return_quantity(shipped_quantity: float, rng: random.Random) -> float:
    quantity = round(max(0.01, shipped_quantity * rng.uniform(0.10, 0.35)), 2)
    return min(round(shipped_quantity, 2), quantity)


def _return_unit_value(shipment_line: Any, invoice_line: Any | None) -> float:
    if invoice_line is not None:
        unit_price = float(getattr(invoice_line, "UnitPrice", 0.0) or 0.0)
        if unit_price > 0:
            return round(unit_price, 2)
        invoice_quantity = float(getattr(invoice_line, "InvoiceQuantity", 0.0) or 0.0)
        net_line_amount = float(getattr(invoice_line, "NetLineAmount", 0.0) or 0.0)
        if invoice_quantity > 0 and net_line_amount > 0:
            return round(net_line_amount / invoice_quantity, 2)
    unit_cost = float(getattr(shipment_line, "UnitCost", 0.0) or 0.0)
    return round(max(0.01, unit_cost), 2)


def _return_line_status(restocked_quantity: float, scrapped_quantity: float) -> str:
    if restocked_quantity > 0 and scrapped_quantity == 0:
        return "Restocked"
    if scrapped_quantity > 0 and restocked_quantity == 0:
        return "Scrapped"
    return "Received"


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _locations_by_customer(customer_location: pd.DataFrame) -> dict[Any, dict[str, Any]]:
    locations: dict[Any, dict[str, Any]] = {}
    for customer_id, group in customer_location.groupby("CustomerID", sort=True):
        default_locations = group[group["IsDefault"].astype(str).isin(("1", "True", "true"))]
        fallback = default_locations.iloc[0] if not default_locations.empty else group.iloc[0]
        billing = _location_for_type(group, ("Billing", "Both"), fallback)
        shipping = _location_for_type(group, ("Shipping", "Both"), fallback)
        locations[customer_id] = {
            "bill_to": billing.CustomerLocationID,
            "ship_to": shipping.CustomerLocationID,
        }
    return locations


def _location_for_type(group: pd.DataFrame, location_types: tuple[str, ...], fallback: pd.Series) -> pd.Series:
    normalized = {location_type.lower() for location_type in location_types}
    candidates = group[group["LocationType"].astype(str).str.lower().isin(normalized)]
    return candidates.iloc[0] if not candidates.empty else fallback


def _bounded_quantity(capacity: float, rng: random.Random) -> float:
    capacity = max(0.0, float(capacity))
    if capacity <= 1.0:
        return round(capacity, 2)
    upper = min(12.0, capacity)
    return round(rng.uniform(1.0, upper), 2)


def _line_status(ordered_quantity: float, reserved_quantity: float, shipped_quantity: float) -> str:
    if shipped_quantity == ordered_quantity:
        return "Closed"
    if shipped_quantity > 0 and reserved_quantity < ordered_quantity:
        return "Backordered"
    if shipped_quantity > 0:
        return "PartiallyShipped"
    return "Backordered"


def _order_status(line_statuses: tuple[str, ...]) -> str:
    if all(status == "Closed" for status in line_statuses):
        return "Closed"
    if any(status == "Backordered" for status in line_statuses):
        return "Backordered"
    if any(status == "PartiallyShipped" for status in line_statuses):
        return "PartiallyShipped"
    return "Backordered"


def _table_target_rows(table: TableContract, default: int) -> int:
    try:
        return int(table.target_rows or default)
    except (TypeError, ValueError):
        return default


_SALES_ORDER_HDR_COLUMNS = (
    "SalesOrderID",
    "SalesOrderNumber",
    "CustomerID",
    "BillToLocationID",
    "ShipToLocationID",
    "SalesChannelID",
    "OrderDate",
    "RequestedShipDate",
    "PromisedShipDate",
    "CurrencyCode",
    "OrderStatus",
)

_SALES_ORDER_LINE_COLUMNS = (
    "SalesOrderLineID",
    "SalesOrderID",
    "ProductID",
    "PlantID",
    "WarehouseID",
    "OrderedQuantity",
    "ReservedQuantity",
    "ShippedQuantity",
    "BackorderQuantity",
    "UOM",
    "UnitPrice",
    "DiscountPct",
    "LineAmount",
    "DiscountAmount",
    "NetLineAmount",
    "LineStatus",
)

_SALES_INVENTORY_RESERVATION_COLUMNS = (
    "ReservationID",
    "SalesOrderLineID",
    "FinishedGoodsInventoryID",
    "ProductID",
    "PlantID",
    "WarehouseID",
    "ReservationDate",
    "ReservedQuantity",
    "ReleasedQuantity",
    "ReservationStatus",
)

_SALES_PICK_LIST_HEADER_COLUMNS = (
    "PickListID",
    "SalesOrderID",
    "WarehouseID",
    "PickDate",
    "PickStatus",
)

_SALES_PICK_LIST_LINE_COLUMNS = (
    "PickListLineID",
    "PickListID",
    "SalesOrderLineID",
    "ReservationID",
    "ProductID",
    "PickedQuantity",
    "UOM",
    "PickLineStatus",
)

_SALES_SHIPMENT_HEADER_COLUMNS = (
    "ShipmentID",
    "ShipmentNumber",
    "SalesOrderID",
    "CustomerID",
    "ShipToLocationID",
    "WarehouseID",
    "ShipmentDate",
    "CarrierName",
    "TrackingNumber",
    "ShipmentStatus",
)

_SALES_SHIPMENT_LINE_COLUMNS = (
    "ShipmentLineID",
    "ShipmentID",
    "SalesOrderLineID",
    "PickListLineID",
    "FinishedGoodsInventoryID",
    "FinishedGoodsReceiptID",
    "ProductionBatchID",
    "ProductID",
    "ShippedQuantity",
    "UOM",
    "UnitCost",
    "COGSValue",
    "ShipmentLineStatus",
)

_SALES_INVOICE_HEADER_COLUMNS = (
    "InvoiceID",
    "InvoiceNumber",
    "SalesOrderID",
    "ShipmentID",
    "CustomerID",
    "InvoiceDate",
    "DueDate",
    "CurrencyCode",
    "SubtotalAmount",
    "DiscountAmount",
    "TaxAmount",
    "FreightAmount",
    "TotalInvoiceAmount",
    "InvoiceStatus",
)

_SALES_INVOICE_LINE_COLUMNS = (
    "InvoiceLineID",
    "InvoiceID",
    "ShipmentLineID",
    "SalesOrderLineID",
    "ProductID",
    "InvoiceQuantity",
    "UnitPrice",
    "DiscountAmount",
    "TaxAmount",
    "NetLineAmount",
    "COGSValue",
    "GrossMarginAmount",
    "GrossMarginPct",
    "LineStatus",
)

_CUSTOMER_PAYMENT_RECEIPT_COLUMNS = (
    "PaymentReceiptID",
    "InvoiceID",
    "CustomerID",
    "PaymentDate",
    "PaymentMethod",
    "PaidAmount",
    "CurrencyCode",
    "PaymentStatus",
)

_SALES_RETURN_HEADER_COLUMNS = (
    "SalesReturnID",
    "ReturnNumber",
    "CustomerID",
    "SalesOrderID",
    "ShipmentID",
    "ReturnDate",
    "ReturnReason",
    "ReturnStatus",
)

_SALES_RETURN_LINE_COLUMNS = (
    "SalesReturnLineID",
    "SalesReturnID",
    "ShipmentLineID",
    "ProductID",
    "ReturnedQuantity",
    "RestockedQuantity",
    "ScrappedQuantity",
    "ReturnUnitValue",
    "ReturnLineStatus",
)

_REQUIRED_MASTER_COLUMNS = {
    "CustomerMaster": ("CustomerID", "PaymentTerms", "CustomerStatus"),
    "CustomerLocation": ("CustomerLocationID", "CustomerID", "LocationType", "IsDefault"),
    "SalesChannel": ("SalesChannelID", "ChannelStatus"),
    "SalesPriceListHeader": ("PriceListID", "CurrencyCode", "PriceListStatus"),
    "SalesPriceListLine": ("ProductID", "UnitPrice", "DiscountPct", "LineStatus"),
}

_REQUIRED_UPSTREAM_COLUMNS = {
    "ProductMaster": ("ProductID",),
    "FinishedGoodsInventory": (
        "FinishedGoodsInventoryID",
        "ProductID",
        "PlantID",
        "WarehouseID",
        "OnHandQuantity",
        "ReservedQuantity",
        "AvailableQuantity",
    ),
    "FinishedGoodsReceipt": (
        "FinishedGoodsReceiptID",
        "ProductID",
        "PlantID",
        "WarehouseID",
        "ProductionBatchID",
        "GoodQuantity",
        "UnitCost",
    ),
    "ProductionBatch": ("ProductionBatchID",),
}

_REQUIRED_PHASE5_MASTER_COLUMNS = {
    "CustomerMaster": ("CustomerID", "PaymentTerms", "CustomerStatus"),
}

_REQUIRED_PHASE5_TRANSACTION_COLUMNS = {
    "SalesOrderHdr": ("SalesOrderID", "CustomerID", "CurrencyCode", "OrderDate"),
    "SalesOrderLine": (
        "SalesOrderLineID",
        "SalesOrderID",
        "ProductID",
        "UnitPrice",
        "DiscountPct",
        "DiscountAmount",
        "NetLineAmount",
    ),
    "SalesShipmentHeader": ("ShipmentID", "SalesOrderID", "CustomerID", "ShipmentDate", "ShipmentStatus"),
    "SalesShipmentLine": (
        "ShipmentLineID",
        "ShipmentID",
        "SalesOrderLineID",
        "ProductID",
        "ShippedQuantity",
        "UnitCost",
        "COGSValue",
    ),
}

_REQUIRED_PHASE6_MASTER_COLUMNS = {
    "CustomerMaster": ("CustomerID",),
}

_REQUIRED_PHASE6_TRANSACTION_COLUMNS = {
    "SalesOrderHdr": ("SalesOrderID", "CustomerID"),
    "SalesShipmentHeader": ("ShipmentID", "SalesOrderID", "CustomerID", "ShipmentDate", "ShipmentStatus"),
    "SalesShipmentLine": (
        "ShipmentLineID",
        "ShipmentID",
        "SalesOrderLineID",
        "ProductID",
        "ShippedQuantity",
        "UnitCost",
        "COGSValue",
    ),
}

_OPTIONAL_PHASE6_INVOICE_COLUMNS = {
    "SalesInvoiceLine": ("ShipmentLineID", "UnitPrice", "NetLineAmount", "InvoiceQuantity"),
}
