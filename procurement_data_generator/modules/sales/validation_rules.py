"""Sales-specific generated-data validation rules."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from procurement_data_generator.core.contracts.data_quality_report import DataQualityReport, TableQualitySummary
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES, SALES_V1_ROLE_CATALOG


SALES_V1_VALIDATION_RULES = (
    "sales_required_tables",
    "sales_master_references",
    "sales_order_quantity_lifecycle",
    "sales_order_financial_formulas",
    "sales_reservation_not_exceed_finished_goods_available",
    "sales_pick_not_exceed_reserved",
    "sales_ship_not_exceed_picked",
    "sales_shipment_cogs_formula",
    "sales_invoice_quantity_equals_shipped",
    "sales_invoice_totals",
    "sales_payment_not_exceed_invoice_total",
    "sales_invoice_status_fact_derived",
    "sales_return_not_exceed_shipped",
    "sales_return_split_balanced",
    "sales_traceability_links_complete",
    "sales_traceability_allocation_formula",
    "sales_finished_goods_inventory_rollup",
)

SALES_V1_REQUIRED_COLUMNS = {
    definition.expected_table_name: definition.required_column_names
    for definition in SALES_V1_ROLE_CATALOG.values()
}

TOLERANCE = 0.011


class SalesDataQualityEngine:
    """Validate generated Sales v1 dataframes and post-Sales finished goods inventory."""

    def validate_dataset(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream_data: Mapping[str, pd.DataFrame] | None = None,
        adjusted_finished_goods_inventory: pd.DataFrame | None = None,
        profile_id: str | None = None,
    ) -> DataQualityReport:
        upstream = dict(upstream_data or {})
        if adjusted_finished_goods_inventory is not None:
            upstream["AdjustedFinishedGoodsInventory"] = adjusted_finished_goods_inventory
        report = DataQualityReport()
        self._initialize_table_summaries(report, sales_data, upstream)
        self._validate_required_tables(sales_data, report)
        self._validate_required_columns(sales_data, report)
        if report.error_count:
            return report

        self._validate_master_references(sales_data, upstream, report)
        self._validate_order_flow(sales_data, upstream, report)
        self._validate_reservations(sales_data, upstream, report)
        self._validate_pick_flow(sales_data, report)
        self._validate_shipment_flow(sales_data, upstream, report)
        self._validate_invoice_flow(sales_data, report)
        self._validate_payment_flow(sales_data, report)
        self._validate_returns(sales_data, report)
        self._validate_traceability(sales_data, upstream, report)
        if adjusted_finished_goods_inventory is not None:
            self._validate_adjusted_inventory(sales_data, upstream, adjusted_finished_goods_inventory, report)
        if profile_id == "food_manufacturing":
            self._validate_no_ev_vocabulary(sales_data, report)
        return report

    def _initialize_table_summaries(
        self,
        report: DataQualityReport,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
    ) -> None:
        for table_name, dataframe in {**sales_data, **upstream}.items():
            if isinstance(dataframe, pd.DataFrame):
                report.table_summaries[table_name] = TableQualitySummary(table_name=table_name, row_count=len(dataframe))

    def _validate_required_tables(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        for table_name in SALES_V1_EXPECTED_TABLES:
            dataframe = sales_data.get(table_name)
            passed = isinstance(dataframe, pd.DataFrame)
            _record(
                report,
                passed,
                "SALES_REQUIRED_TABLE",
                f"Required Sales v1 table {table_name} is missing.",
                "Provide every approved Sales v1 table before validation.",
                table_name=table_name,
                rule_id="sales_required_tables",
            )
        _record(
            report,
            "SalesCreditMemo" not in sales_data,
            "SALES_CREDIT_MEMO_EXCLUDED",
            "SalesCreditMemo is excluded from Sales v1 and must not be generated.",
            "Remove SalesCreditMemo from Sales v1 outputs.",
            table_name="SalesCreditMemo",
            rule_id="sales_required_tables",
        )

    def _validate_required_columns(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        for table_name, columns in SALES_V1_REQUIRED_COLUMNS.items():
            dataframe = sales_data.get(table_name)
            if not isinstance(dataframe, pd.DataFrame):
                continue
            for column_name in columns:
                _record(
                    report,
                    column_name in dataframe.columns,
                    "SALES_REQUIRED_COLUMN",
                    f"{table_name}.{column_name} is missing.",
                    "Generate all columns listed in Sales v1 metadata.",
                    table_name=table_name,
                    column_name=column_name,
                    rule_id="sales_required_tables",
                )
            pk_candidates = [column for column in columns if column.endswith("ID")]
            if pk_candidates and pk_candidates[0] in dataframe.columns:
                pk_column = pk_candidates[0]
                _record(
                    report,
                    dataframe[pk_column].notna().all() and dataframe[pk_column].is_unique,
                    "SALES_PK_UNIQUE",
                    f"{table_name}.{pk_column} must be non-null and unique.",
                    "Generate stable unique Sales primary keys.",
                    table_name=table_name,
                    column_name=pk_column,
                    failed_rows=dataframe[dataframe[pk_column].isna() | dataframe[pk_column].duplicated(keep=False)],
                    rule_id="sales_required_tables",
                )

    def _validate_master_references(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
        report: DataQualityReport,
    ) -> None:
        customer = sales_data["CustomerMaster"]
        location = sales_data["CustomerLocation"]
        price_header = sales_data["SalesPriceListHeader"]
        price_line = sales_data["SalesPriceListLine"]
        product = upstream.get("ProductMaster")
        _fk(report, location, "CustomerLocation", "CustomerID", customer, "CustomerID", "sales_master_references")
        active_customers = set(customer.loc[customer["CustomerStatus"].astype(str).str.lower() == "active", "CustomerID"])
        located_customers = set(location["CustomerID"])
        _record(
            report,
            active_customers.issubset(located_customers),
            "SALES_ACTIVE_CUSTOMER_HAS_LOCATION",
            "Every active customer must have at least one customer location.",
            "Generate one or more CustomerLocation rows for each active customer.",
            table_name="CustomerLocation",
            rule_id="sales_master_references",
        )
        _fk(report, price_line, "SalesPriceListLine", "PriceListID", price_header, "PriceListID", "sales_master_references")
        if product is not None:
            _fk(report, price_line, "SalesPriceListLine", "ProductID", product, "ProductID", "sales_master_references")

    def _validate_order_flow(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
        report: DataQualityReport,
    ) -> None:
        customer = sales_data["CustomerMaster"]
        location = sales_data["CustomerLocation"]
        channel = sales_data["SalesChannel"]
        order_header = sales_data["SalesOrderHdr"]
        order_line = sales_data["SalesOrderLine"]
        product = upstream.get("ProductMaster")
        _fk(report, order_header, "SalesOrderHdr", "CustomerID", customer, "CustomerID", "sales_order_header_references")
        _fk(report, order_header, "SalesOrderHdr", "BillToLocationID", location, "CustomerLocationID", "sales_order_header_references")
        _fk(report, order_header, "SalesOrderHdr", "ShipToLocationID", location, "CustomerLocationID", "sales_order_header_references")
        _fk(report, order_header, "SalesOrderHdr", "SalesChannelID", channel, "SalesChannelID", "sales_order_header_references")
        _fk(report, order_line, "SalesOrderLine", "SalesOrderID", order_header, "SalesOrderID", "sales_order_line_references")
        if product is not None:
            _fk(report, order_line, "SalesOrderLine", "ProductID", product, "ProductID", "sales_order_line_references")

        locations_by_id = location.set_index("CustomerLocationID")["CustomerID"].to_dict()
        same_customer = order_header.apply(
            lambda row: locations_by_id.get(row["BillToLocationID"]) == row["CustomerID"]
            and locations_by_id.get(row["ShipToLocationID"]) == row["CustomerID"],
            axis=1,
        )
        _record(
            report,
            bool(same_customer.all()),
            "SALES_ORDER_LOCATION_CUSTOMER_MATCH",
            "Bill-to and ship-to locations must belong to the Sales order customer.",
            "Select CustomerLocation rows from the same CustomerID as SalesOrderHdr.",
            table_name="SalesOrderHdr",
            failed_rows=order_header[~same_customer],
            rule_id="sales_order_header_references",
        )

        quantity_mask = (
            (_num(order_line["OrderedQuantity"]) >= 0)
            & (_num(order_line["ReservedQuantity"]) >= 0)
            & (_num(order_line["ShippedQuantity"]) >= 0)
            & (_num(order_line["BackorderQuantity"]) >= 0)
            & (_num(order_line["OrderedQuantity"]) + TOLERANCE >= _num(order_line["ReservedQuantity"]))
            & (_num(order_line["ReservedQuantity"]) + TOLERANCE >= _num(order_line["ShippedQuantity"]))
            & (_num(order_line["OrderedQuantity"]) + TOLERANCE >= _num(order_line["ShippedQuantity"]))
            & _near(_num(order_line["BackorderQuantity"]), _num(order_line["OrderedQuantity"]) - _num(order_line["ShippedQuantity"]))
        )
        _record(
            report,
            bool(quantity_mask.all()),
            "SALES_ORDER_QUANTITY_LIFECYCLE",
            "Sales order quantities must satisfy Ordered >= Reserved >= Shipped and Backorder = Ordered - Shipped.",
            "Recalculate SalesOrderLine quantity lifecycle fields from generated reservation and shipment facts.",
            table_name="SalesOrderLine",
            failed_rows=order_line[~quantity_mask],
            rule_id="sales_order_quantity_lifecycle",
        )
        self._validate_order_financials(order_line, report)
        self._validate_order_line_status(order_line, report)

    def _validate_order_financials(self, order_line: pd.DataFrame, report: DataQualityReport) -> None:
        line_amount_ok = _near(_num(order_line["LineAmount"]), _num(order_line["OrderedQuantity"]) * _num(order_line["UnitPrice"]))
        discount_ok = _near(_num(order_line["DiscountAmount"]), _num(order_line["LineAmount"]) * _num(order_line["DiscountPct"]) / 100.0)
        net_ok = _near(_num(order_line["NetLineAmount"]), _num(order_line["LineAmount"]) - _num(order_line["DiscountAmount"]))
        mask = line_amount_ok & discount_ok & net_ok
        _record(
            report,
            bool(mask.all()),
            "SALES_ORDER_FINANCIAL_FORMULA",
            "SalesOrderLine financial formulas are inconsistent.",
            "Set LineAmount = OrderedQuantity * UnitPrice, DiscountAmount = LineAmount * DiscountPct / 100, and NetLineAmount = LineAmount - DiscountAmount.",
            table_name="SalesOrderLine",
            failed_rows=order_line[~mask],
            rule_id="sales_order_financial_formulas",
        )

    def _validate_order_line_status(self, order_line: pd.DataFrame, report: DataQualityReport) -> None:
        def expected_status(row: pd.Series) -> str:
            if abs(float(row["ShippedQuantity"]) - float(row["OrderedQuantity"])) <= TOLERANCE:
                return "Closed"
            if float(row["ReservedQuantity"]) + TOLERANCE < float(row["OrderedQuantity"]):
                return "Backordered"
            if float(row["ShippedQuantity"]) > 0:
                return "PartiallyShipped"
            return "Backordered"

        expected = order_line.apply(expected_status, axis=1)
        mask = order_line["LineStatus"].astype(str).eq(expected)
        _record(
            report,
            bool(mask.all()),
            "SALES_ORDER_LINE_STATUS",
            "SalesOrderLine.LineStatus must be derived from ordered, reserved, and shipped quantities.",
            "Set Closed, PartiallyShipped, or Backordered from line quantity facts.",
            table_name="SalesOrderLine",
            column_name="LineStatus",
            failed_rows=order_line[~mask],
            rule_id="sales_order_quantity_lifecycle",
        )

    def _validate_reservations(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
        report: DataQualityReport,
    ) -> None:
        reservations = sales_data["SalesInventoryReservation"]
        order_line = sales_data["SalesOrderLine"]
        inventory = upstream.get("FinishedGoodsInventory")
        _fk(report, reservations, "SalesInventoryReservation", "SalesOrderLineID", order_line, "SalesOrderLineID", "sales_reservation_not_exceed_finished_goods_available")
        if inventory is not None:
            _fk(report, reservations, "SalesInventoryReservation", "FinishedGoodsInventoryID", inventory, "FinishedGoodsInventoryID", "sales_reservation_not_exceed_finished_goods_available")
        merged = reservations.merge(
            order_line[["SalesOrderLineID", "OrderedQuantity", "ProductID", "PlantID", "WarehouseID"]],
            on="SalesOrderLineID",
            suffixes=("", "_line"),
        )
        align_mask = (
            merged["ProductID"].eq(merged["ProductID_line"])
            & merged["PlantID"].eq(merged["PlantID_line"])
            & merged["WarehouseID"].eq(merged["WarehouseID_line"])
        )
        quantity_mask = (
            (_num(merged["ReservedQuantity"]) >= 0)
            & (_num(merged["ReleasedQuantity"]) >= 0)
            & (_num(merged["ReservedQuantity"]) <= _num(merged["OrderedQuantity"]) + TOLERANCE)
        )
        _record(
            report,
            bool((align_mask & quantity_mask).all()),
            "SALES_RESERVATION_QUANTITY_OR_CONTEXT",
            "Reservations must align to SalesOrderLine product/location and not exceed ordered quantity.",
            "Carry product/location from SalesOrderLine and cap reservation quantity by ordered quantity.",
            table_name="SalesInventoryReservation",
            failed_rows=merged[~(align_mask & quantity_mask)],
            rule_id="sales_reservation_not_exceed_finished_goods_available",
        )
        if inventory is not None:
            reserved_by_inventory = reservations.groupby("FinishedGoodsInventoryID")["ReservedQuantity"].sum()
            available_by_inventory = inventory.set_index("FinishedGoodsInventoryID")["AvailableQuantity"]
            oversold_ids = [
                inventory_id
                for inventory_id, reserved_quantity in reserved_by_inventory.items()
                if reserved_quantity > float(available_by_inventory.get(inventory_id, -1)) + TOLERANCE
            ]
            _record(
                report,
                not oversold_ids,
                "SALES_RESERVATION_OVERSELL",
                "Total reservation quantity must not exceed original FinishedGoodsInventory.AvailableQuantity.",
                "Allocate reservations only from available finished goods inventory.",
                table_name="SalesInventoryReservation",
                failed_rows=reservations[reservations["FinishedGoodsInventoryID"].isin(oversold_ids)],
                rule_id="sales_reservation_not_exceed_finished_goods_available",
            )
        _record(
            report,
            set(reservations["ReservationStatus"].dropna()).issubset({"Reserved", "Consumed", "Released"}),
            "SALES_RESERVATION_STATUS_ALLOWED",
            "ReservationStatus must be Reserved, Consumed, or Released.",
            "Use only the Sales v1 reservation status values.",
            table_name="SalesInventoryReservation",
            column_name="ReservationStatus",
            rule_id="sales_reservation_not_exceed_finished_goods_available",
        )

    def _validate_pick_flow(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        pick_header = sales_data["SalesPickListHeader"]
        pick_line = sales_data["SalesPickListLine"]
        order_header = sales_data["SalesOrderHdr"]
        order_line = sales_data["SalesOrderLine"]
        reservation = sales_data["SalesInventoryReservation"]
        _fk(report, pick_header, "SalesPickListHeader", "SalesOrderID", order_header, "SalesOrderID", "sales_pick_not_exceed_reserved")
        _fk(report, pick_line, "SalesPickListLine", "PickListID", pick_header, "PickListID", "sales_pick_not_exceed_reserved")
        _fk(report, pick_line, "SalesPickListLine", "SalesOrderLineID", order_line, "SalesOrderLineID", "sales_pick_not_exceed_reserved")
        _fk(report, pick_line, "SalesPickListLine", "ReservationID", reservation, "ReservationID", "sales_pick_not_exceed_reserved")
        merged = pick_line.merge(reservation[["ReservationID", "ReservedQuantity"]], on="ReservationID")
        quantity_mask = (_num(merged["PickedQuantity"]) >= 0) & (_num(merged["PickedQuantity"]) <= _num(merged["ReservedQuantity"]) + TOLERANCE)
        status_mask = merged.apply(
            lambda row: row["PickLineStatus"] == ("Picked" if abs(float(row["PickedQuantity"]) - float(row["ReservedQuantity"])) <= TOLERANCE else "ShortPicked"),
            axis=1,
        )
        _record(
            report,
            bool((quantity_mask & status_mask).all()),
            "SALES_PICK_QUANTITY_OR_STATUS",
            "Picked quantity must not exceed reserved quantity and PickLineStatus must match pick facts.",
            "Cap picked quantity by reservation and derive PickLineStatus from quantity facts.",
            table_name="SalesPickListLine",
            failed_rows=merged[~(quantity_mask & status_mask)],
            rule_id="sales_pick_not_exceed_reserved",
        )

    def _validate_shipment_flow(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
        report: DataQualityReport,
    ) -> None:
        shipment_header = sales_data["SalesShipmentHeader"]
        shipment_line = sales_data["SalesShipmentLine"]
        order_header = sales_data["SalesOrderHdr"]
        order_line = sales_data["SalesOrderLine"]
        pick_line = sales_data["SalesPickListLine"]
        location = sales_data["CustomerLocation"]
        product = upstream.get("ProductMaster")
        inventory = upstream.get("FinishedGoodsInventory")
        receipt = upstream.get("FinishedGoodsReceipt")
        batch = upstream.get("ProductionBatch")
        _fk(report, shipment_header, "SalesShipmentHeader", "SalesOrderID", order_header, "SalesOrderID", "sales_ship_not_exceed_picked")
        _fk(report, shipment_header, "SalesShipmentHeader", "ShipToLocationID", location, "CustomerLocationID", "sales_ship_not_exceed_picked")
        _fk(report, shipment_line, "SalesShipmentLine", "ShipmentID", shipment_header, "ShipmentID", "sales_ship_not_exceed_picked")
        _fk(report, shipment_line, "SalesShipmentLine", "SalesOrderLineID", order_line, "SalesOrderLineID", "sales_ship_not_exceed_picked")
        _fk(report, shipment_line, "SalesShipmentLine", "PickListLineID", pick_line, "PickListLineID", "sales_ship_not_exceed_picked")
        if product is not None:
            _fk(report, shipment_line, "SalesShipmentLine", "ProductID", product, "ProductID", "sales_ship_not_exceed_picked")
        if inventory is not None:
            _fk(report, shipment_line, "SalesShipmentLine", "FinishedGoodsInventoryID", inventory, "FinishedGoodsInventoryID", "sales_ship_not_exceed_picked")
        if receipt is not None:
            _fk(report, shipment_line, "SalesShipmentLine", "FinishedGoodsReceiptID", receipt, "FinishedGoodsReceiptID", "sales_ship_not_exceed_picked")
        if batch is not None:
            _fk(report, shipment_line, "SalesShipmentLine", "ProductionBatchID", batch, "ProductionBatchID", "sales_ship_not_exceed_picked")

        header_context = shipment_header.merge(order_header[["SalesOrderID", "CustomerID"]], on="SalesOrderID", suffixes=("", "_order"))
        customer_mask = header_context["CustomerID"].eq(header_context["CustomerID_order"])
        _record(
            report,
            bool(customer_mask.all()),
            "SALES_SHIPMENT_CUSTOMER_MATCH",
            "SalesShipmentHeader.CustomerID must match SalesOrderHdr.CustomerID.",
            "Carry customer identity from SalesOrderHdr to shipment headers.",
            table_name="SalesShipmentHeader",
            failed_rows=header_context[~customer_mask],
            rule_id="sales_ship_not_exceed_picked",
        )
        merged = shipment_line.merge(pick_line[["PickListLineID", "PickedQuantity"]], on="PickListLineID")
        quantity_mask = (_num(merged["ShippedQuantity"]) >= 0) & (_num(merged["ShippedQuantity"]) <= _num(merged["PickedQuantity"]) + TOLERANCE)
        cogs_mask = _near(_num(merged["COGSValue"]), _num(merged["ShippedQuantity"]) * _num(merged["UnitCost"]))
        _record(
            report,
            bool(quantity_mask.all()),
            "SALES_SHIPMENT_QUANTITY",
            "ShippedQuantity must not exceed picked quantity.",
            "Generate shipments from picked quantities only.",
            table_name="SalesShipmentLine",
            failed_rows=merged[~quantity_mask],
            rule_id="sales_ship_not_exceed_picked",
        )
        _record(
            report,
            bool(cogs_mask.all()),
            "SALES_SHIPMENT_COGS_FORMULA",
            "SalesShipmentLine.COGSValue must equal ShippedQuantity * UnitCost.",
            "Recalculate shipment COGS from shipped quantity and unit cost.",
            table_name="SalesShipmentLine",
            column_name="COGSValue",
            failed_rows=merged[~cogs_mask],
            rule_id="sales_shipment_cogs_formula",
        )
        self._validate_shipment_capacity(shipment_line, inventory, receipt, report)

    def _validate_shipment_capacity(
        self,
        shipment_line: pd.DataFrame,
        inventory: pd.DataFrame | None,
        receipt: pd.DataFrame | None,
        report: DataQualityReport,
    ) -> None:
        if inventory is not None:
            shipped_by_inventory = shipment_line.groupby("FinishedGoodsInventoryID")["ShippedQuantity"].sum()
            available_by_inventory = inventory.set_index("FinishedGoodsInventoryID")["AvailableQuantity"]
            oversold_ids = [
                inventory_id
                for inventory_id, shipped_quantity in shipped_by_inventory.items()
                if shipped_quantity > float(available_by_inventory.get(inventory_id, -1)) + TOLERANCE
            ]
            _record(
                report,
                not oversold_ids,
                "SALES_SHIPMENT_INVENTORY_OVERSELL",
                "Total shipped quantity must not exceed original FinishedGoodsInventory.AvailableQuantity.",
                "Allocate shipment quantities within available finished goods inventory.",
                table_name="SalesShipmentLine",
                failed_rows=shipment_line[shipment_line["FinishedGoodsInventoryID"].isin(oversold_ids)],
                rule_id="sales_ship_not_exceed_picked",
            )
        if receipt is not None:
            shipped_by_receipt = shipment_line.groupby("FinishedGoodsReceiptID")["ShippedQuantity"].sum()
            good_by_receipt = receipt.set_index("FinishedGoodsReceiptID")["GoodQuantity"]
            oversold_ids = [
                receipt_id
                for receipt_id, shipped_quantity in shipped_by_receipt.items()
                if shipped_quantity > float(good_by_receipt.get(receipt_id, -1)) + TOLERANCE
            ]
            _record(
                report,
                not oversold_ids,
                "SALES_SHIPMENT_RECEIPT_OVERSELL",
                "Total shipped quantity must not exceed FinishedGoodsReceipt.GoodQuantity.",
                "Allocate shipment quantities within finished goods receipt quantities.",
                table_name="SalesShipmentLine",
                failed_rows=shipment_line[shipment_line["FinishedGoodsReceiptID"].isin(oversold_ids)],
                rule_id="sales_ship_not_exceed_picked",
            )

    def _validate_invoice_flow(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        invoice_header = sales_data["SalesInvoiceHeader"]
        invoice_line = sales_data["SalesInvoiceLine"]
        shipment_header = sales_data["SalesShipmentHeader"]
        shipment_line = sales_data["SalesShipmentLine"]
        order_line = sales_data["SalesOrderLine"]
        customer = sales_data["CustomerMaster"]
        _fk(report, invoice_header, "SalesInvoiceHeader", "SalesOrderID", sales_data["SalesOrderHdr"], "SalesOrderID", "sales_invoice_totals")
        _fk(report, invoice_header, "SalesInvoiceHeader", "ShipmentID", shipment_header, "ShipmentID", "sales_invoice_totals")
        _fk(report, invoice_header, "SalesInvoiceHeader", "CustomerID", customer, "CustomerID", "sales_invoice_totals")
        _fk(report, invoice_line, "SalesInvoiceLine", "InvoiceID", invoice_header, "InvoiceID", "sales_invoice_totals")
        _fk(report, invoice_line, "SalesInvoiceLine", "ShipmentLineID", shipment_line, "ShipmentLineID", "sales_invoice_quantity_equals_shipped")
        _fk(report, invoice_line, "SalesInvoiceLine", "SalesOrderLineID", order_line, "SalesOrderLineID", "sales_invoice_quantity_equals_shipped")

        merged = invoice_line.merge(
            shipment_line[["ShipmentLineID", "ProductID", "ShippedQuantity", "UnitCost"]],
            on="ShipmentLineID",
            suffixes=("", "_shipment"),
        )
        product_mask = merged["ProductID"].eq(merged["ProductID_shipment"])
        invoice_quantity_mask = _near(_num(merged["InvoiceQuantity"]), _num(merged["ShippedQuantity"]))
        cogs_mask = _near(_num(merged["COGSValue"]), _num(merged["InvoiceQuantity"]) * _num(merged["UnitCost"]))
        margin_mask = _near(_num(merged["GrossMarginAmount"]), _num(merged["NetLineAmount"]) - _num(merged["COGSValue"]))
        expected_pct = (_num(merged["GrossMarginAmount"]) / _num(merged["NetLineAmount"]).replace(0, pd.NA)).fillna(0.0)
        pct_mask = _near(_num(merged["GrossMarginPct"]), expected_pct, tolerance=0.0001)
        _record(
            report,
            bool((product_mask & invoice_quantity_mask & cogs_mask & margin_mask & pct_mask).all()),
            "SALES_INVOICE_LINE_FORMULA",
            "Invoice lines must match shipped quantities, COGS, and gross margin formulas.",
            "Generate invoice lines directly from SalesShipmentLine and order pricing facts.",
            table_name="SalesInvoiceLine",
            failed_rows=merged[~(product_mask & invoice_quantity_mask & cogs_mask & margin_mask & pct_mask)],
            rule_id="sales_invoice_quantity_equals_shipped",
        )
        self._validate_invoice_header_totals(invoice_header, invoice_line, report)
        invoice_dates = invoice_header.merge(shipment_header[["ShipmentID", "ShipmentDate"]], on="ShipmentID")
        date_mask = (pd.to_datetime(invoice_dates["InvoiceDate"]) >= pd.to_datetime(invoice_dates["ShipmentDate"])) & (
            pd.to_datetime(invoice_dates["DueDate"]) >= pd.to_datetime(invoice_dates["InvoiceDate"])
        )
        _record(
            report,
            bool(date_mask.all()),
            "SALES_INVOICE_DATES",
            "InvoiceDate must be on or after ShipmentDate, and DueDate must be on or after InvoiceDate.",
            "Derive invoice dates from shipment date and customer payment terms.",
            table_name="SalesInvoiceHeader",
            failed_rows=invoice_dates[~date_mask],
            rule_id="sales_invoice_totals",
        )

    def _validate_invoice_header_totals(self, invoice_header: pd.DataFrame, invoice_line: pd.DataFrame, report: DataQualityReport) -> None:
        lines = invoice_line.copy()
        lines["GrossLineAmount"] = _num(lines["InvoiceQuantity"]) * _num(lines["UnitPrice"])
        totals = lines.groupby("InvoiceID").agg(
            Subtotal=("GrossLineAmount", "sum"),
            Discount=("DiscountAmount", "sum"),
            Tax=("TaxAmount", "sum"),
        )
        merged = invoice_header.merge(totals, on="InvoiceID", how="left").fillna({"Subtotal": 0, "Discount": 0, "Tax": 0})
        mask = (
            _near(_num(merged["SubtotalAmount"]), _num(merged["Subtotal"]))
            & _near(_num(merged["DiscountAmount"]), _num(merged["Discount"]))
            & _near(_num(merged["TaxAmount"]), _num(merged["Tax"]))
            & _near(
                _num(merged["TotalInvoiceAmount"]),
                _num(merged["SubtotalAmount"]) - _num(merged["DiscountAmount"]) + _num(merged["TaxAmount"]) + _num(merged["FreightAmount"]),
            )
        )
        _record(
            report,
            bool(mask.all()),
            "SALES_INVOICE_TOTAL_FORMULA",
            "SalesInvoiceHeader totals must reconcile to invoice lines and freight.",
            "Set TotalInvoiceAmount = SubtotalAmount - DiscountAmount + TaxAmount + FreightAmount.",
            table_name="SalesInvoiceHeader",
            failed_rows=merged[~mask],
            rule_id="sales_invoice_totals",
        )

    def _validate_payment_flow(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        payment = sales_data["CustomerPaymentReceipt"]
        invoice_header = sales_data["SalesInvoiceHeader"]
        customer = sales_data["CustomerMaster"]
        _fk(report, payment, "CustomerPaymentReceipt", "InvoiceID", invoice_header, "InvoiceID", "sales_payment_not_exceed_invoice_total")
        _fk(report, payment, "CustomerPaymentReceipt", "CustomerID", customer, "CustomerID", "sales_payment_not_exceed_invoice_total")
        paid_by_invoice = payment.groupby("InvoiceID")["PaidAmount"].sum() if not payment.empty else pd.Series(dtype=float)
        merged = invoice_header.copy()
        merged["PaidAmount"] = merged["InvoiceID"].map(paid_by_invoice).fillna(0.0)
        payment_mask = (_num(merged["PaidAmount"]) >= 0) & (_num(merged["PaidAmount"]) <= _num(merged["TotalInvoiceAmount"]) + TOLERANCE)
        status_mask = merged.apply(lambda row: row["InvoiceStatus"] == _invoice_status(row["TotalInvoiceAmount"], row["PaidAmount"]), axis=1)
        _record(
            report,
            bool((payment_mask & status_mask).all()),
            "SALES_PAYMENT_OR_INVOICE_STATUS",
            "Payments must not exceed invoice totals and InvoiceStatus must match payment facts.",
            "Derive InvoiceStatus from total paid amount.",
            table_name="SalesInvoiceHeader",
            failed_rows=merged[~(payment_mask & status_mask)],
            rule_id="sales_payment_not_exceed_invoice_total",
        )
        if not payment.empty:
            pay_dates = payment.merge(invoice_header[["InvoiceID", "InvoiceDate"]], on="InvoiceID")
            date_mask = pd.to_datetime(pay_dates["PaymentDate"]) >= pd.to_datetime(pay_dates["InvoiceDate"])
            status_allowed = payment["PaymentStatus"].astype(str).isin({"Received", "Partial", "Failed"})
            _record(
                report,
                bool(date_mask.all() and status_allowed.all()),
                "SALES_PAYMENT_DATE_OR_STATUS",
                "Payment dates must be on or after invoice date and PaymentStatus must be allowed.",
                "Use Received, Partial, or Failed and date payments after invoice creation.",
                table_name="CustomerPaymentReceipt",
                failed_rows=pay_dates[~date_mask],
                rule_id="sales_payment_not_exceed_invoice_total",
            )

    def _validate_returns(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        return_header = sales_data["SalesReturnHeader"]
        return_line = sales_data["SalesReturnLine"]
        if return_header.empty and return_line.empty:
            _record(report, True, "SALES_RETURNS_OPTIONAL_EMPTY", "", "", rule_id="sales_return_not_exceed_shipped")
            return
        shipment_header = sales_data["SalesShipmentHeader"]
        shipment_line = sales_data["SalesShipmentLine"]
        customer = sales_data["CustomerMaster"]
        order_header = sales_data["SalesOrderHdr"]
        _fk(report, return_header, "SalesReturnHeader", "CustomerID", customer, "CustomerID", "sales_return_not_exceed_shipped")
        _fk(report, return_header, "SalesReturnHeader", "SalesOrderID", order_header, "SalesOrderID", "sales_return_not_exceed_shipped")
        _fk(report, return_header, "SalesReturnHeader", "ShipmentID", shipment_header, "ShipmentID", "sales_return_not_exceed_shipped")
        _fk(report, return_line, "SalesReturnLine", "SalesReturnID", return_header, "SalesReturnID", "sales_return_not_exceed_shipped")
        _fk(report, return_line, "SalesReturnLine", "ShipmentLineID", shipment_line, "ShipmentLineID", "sales_return_not_exceed_shipped")
        merged = return_line.merge(shipment_line[["ShipmentLineID", "ProductID", "ShippedQuantity"]], on="ShipmentLineID", suffixes=("", "_shipment"))
        quantity_mask = (
            (_num(merged["ReturnedQuantity"]) > 0)
            & (_num(merged["ReturnedQuantity"]) <= _num(merged["ShippedQuantity"]) + TOLERANCE)
            & (_num(merged["RestockedQuantity"]) >= 0)
            & (_num(merged["ScrappedQuantity"]) >= 0)
        )
        split_mask = _near(_num(merged["ReturnedQuantity"]), _num(merged["RestockedQuantity"]) + _num(merged["ScrappedQuantity"]))
        product_mask = merged["ProductID"].eq(merged["ProductID_shipment"])
        _record(
            report,
            bool((quantity_mask & split_mask & product_mask).all()),
            "SALES_RETURN_QUANTITY_OR_SPLIT",
            "Return quantities must be positive, not exceed shipped quantity, and split into restocked plus scrapped quantity.",
            "Generate returns from shipment lines and balance returned quantity against restocked/scrapped quantities.",
            table_name="SalesReturnLine",
            failed_rows=merged[~(quantity_mask & split_mask & product_mask)],
            rule_id="sales_return_split_balanced",
        )
        dates = return_header.merge(shipment_header[["ShipmentID", "ShipmentDate"]], on="ShipmentID")
        date_mask = pd.to_datetime(dates["ReturnDate"]) >= pd.to_datetime(dates["ShipmentDate"])
        _record(
            report,
            bool(date_mask.all() and (_num(return_line["ReturnUnitValue"]) > 0).all()),
            "SALES_RETURN_DATE_OR_VALUE",
            "ReturnDate must be after shipment and ReturnUnitValue must be positive.",
            "Use valid shipment-sourced return dates and positive return values.",
            table_name="SalesReturnHeader",
            failed_rows=dates[~date_mask],
            rule_id="sales_return_not_exceed_shipped",
        )

    def _validate_traceability(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
        report: DataQualityReport,
    ) -> None:
        trace = sales_data["SalesShipmentTraceability"]
        shipment_line = sales_data["SalesShipmentLine"]
        for table_name, parent_column in (
            ("FinishedGoodsReceipt", "FinishedGoodsReceiptID"),
            ("ProductionBatch", "ProductionBatchID"),
            ("ProductionGenealogy", "ProductionGenealogyID"),
            ("MaterialIssueLine", "MaterialIssueLineID"),
            ("InventoryReceiptDetail", "InventoryReceiptDetailID"),
            ("SupplierMaster", "SupplierID"),
            ("ComponentMaster", "ComponentID"),
            ("ProductMaster", "ProductID"),
        ):
            parent = upstream.get(table_name)
            if parent is not None:
                _fk(report, trace, "SalesShipmentTraceability", parent_column, parent, parent_column, "sales_traceability_links_complete")
        _fk(report, trace, "SalesShipmentTraceability", "ShipmentLineID", shipment_line, "ShipmentLineID", "sales_traceability_links_complete")
        shipped_line_ids = set(shipment_line.loc[_num(shipment_line["ShippedQuantity"]) > 0, "ShipmentLineID"])
        traced_line_ids = set(trace["ShipmentLineID"])
        _record(
            report,
            shipped_line_ids.issubset(traced_line_ids),
            "SALES_TRACEABILITY_ROW_PER_SHIPMENT_LINE",
            "Every shipped SalesShipmentLine must have at least one SalesShipmentTraceability row.",
            "Generate traceability rows for every shipped customer shipment line.",
            table_name="SalesShipmentTraceability",
            rule_id="sales_traceability_links_complete",
        )
        receipt = upstream.get("FinishedGoodsReceipt")
        genealogy = upstream.get("ProductionGenealogy")
        if receipt is not None and genealogy is not None:
            merged = (
                trace.merge(shipment_line[["ShipmentLineID", "ShippedQuantity"]], on="ShipmentLineID", suffixes=("", "_shipment"))
                .merge(receipt[["FinishedGoodsReceiptID", "GoodQuantity"]], on="FinishedGoodsReceiptID")
                .merge(genealogy[["ProductionGenealogyID", "ConsumedQuantity"]], on="ProductionGenealogyID")
            )
            expected = _num(merged["ConsumedQuantity"]) * _num(merged["ShippedQuantity"]) / _num(merged["GoodQuantity"])
            mask = (_num(merged["AllocatedConsumedQuantity"]) >= 0) & _near(_num(merged["AllocatedConsumedQuantity"]), expected)
            status_mask = trace["TraceabilityStatus"].astype(str).eq("Traced")
            _record(
                report,
                bool(mask.all() and status_mask.all()),
                "SALES_TRACEABILITY_ALLOCATION",
                "AllocatedConsumedQuantity must be proportional to shipped finished goods quantity and TraceabilityStatus must be Traced.",
                "Set allocation from ProductionGenealogy.ConsumedQuantity * SalesShipmentLine.ShippedQuantity / FinishedGoodsReceipt.GoodQuantity.",
                table_name="SalesShipmentTraceability",
                failed_rows=merged[~mask],
                rule_id="sales_traceability_allocation_formula",
            )

    def _validate_adjusted_inventory(
        self,
        sales_data: Mapping[str, pd.DataFrame],
        upstream: Mapping[str, pd.DataFrame],
        adjusted_inventory: pd.DataFrame,
        report: DataQualityReport,
    ) -> None:
        receipt = upstream.get("FinishedGoodsReceipt")
        original_inventory = upstream.get("FinishedGoodsInventory")
        if receipt is None or original_inventory is None:
            return
        expected = _expected_inventory_rollup(
            original_inventory,
            receipt,
            sales_data["SalesShipmentLine"],
            sales_data["SalesInventoryReservation"],
            sales_data.get("SalesReturnLine", pd.DataFrame()),
        )
        merged = adjusted_inventory.merge(expected, on=["ProductID", "PlantID", "WarehouseID"], suffixes=("", "_expected"))
        quantity_mask = (
            _near(_num(merged["OnHandQuantity"]), _num(merged["OnHandQuantity_expected"]))
            & _near(_num(merged["ReservedQuantity"]), _num(merged["ReservedQuantity_expected"]))
            & _near(_num(merged["AvailableQuantity"]), _num(merged["AvailableQuantity_expected"]))
            & (_num(merged["OnHandQuantity"]) >= 0)
            & (_num(merged["ReservedQuantity"]) >= 0)
            & (_num(merged["AvailableQuantity"]) >= 0)
            & (_num(merged["ReservedQuantity"]) <= _num(merged["OnHandQuantity"]) + TOLERANCE)
        )
        _record(
            report,
            bool(quantity_mask.all()),
            "SALES_FINISHED_GOODS_INVENTORY_ROLLUP",
            "Adjusted FinishedGoodsInventory must equal receipts minus shipments plus restocked returns and active reserved quantity.",
            "Recalculate FinishedGoodsInventory after Sales using Phase 8 rollup rules.",
            table_name="FinishedGoodsInventory",
            failed_rows=merged[~quantity_mask],
            rule_id="sales_finished_goods_inventory_rollup",
        )
        if {"OnHandValue", "AverageUnitCost"}.issubset(merged.columns):
            value_mask = _near(_num(merged["OnHandValue"]), _num(merged["OnHandQuantity"]) * _num(merged["AverageUnitCost"]))
            if "AvailableValue" in merged.columns:
                value_mask = value_mask & _near(_num(merged["AvailableValue"]), _num(merged["AvailableQuantity"]) * _num(merged["AverageUnitCost"]))
            _record(
                report,
                bool(value_mask.all()),
                "SALES_FINISHED_GOODS_INVENTORY_VALUE",
                "FinishedGoodsInventory values must reconcile to average receipt cost.",
                "Set inventory value columns from adjusted quantities and weighted average receipt cost.",
                table_name="FinishedGoodsInventory",
                failed_rows=merged[~value_mask],
                rule_id="sales_finished_goods_inventory_rollup",
            )

    def _validate_no_ev_vocabulary(self, sales_data: Mapping[str, pd.DataFrame], report: DataQualityReport) -> None:
        terms = ("battery", "automotive", "chassis", "drive unit", "power electronics", "dealer", "fleet")
        text_values: list[str] = []
        for dataframe in sales_data.values():
            object_columns = dataframe.select_dtypes(include="object")
            text_values.extend(str(value).lower() for value in object_columns.to_numpy().ravel() if pd.notna(value))
        text = " ".join(text_values)
        has_ev = any(term in text for term in terms) or " ev " in f" {text} "
        _record(
            report,
            not has_ev,
            "SALES_FOOD_PROFILE_NO_EV_VOCABULARY",
            "Food manufacturing Sales data must not contain EV or automotive vocabulary.",
            "Use industry-profile-driven Sales vocabulary for customer, channel, carrier, return, and payment terms.",
            rule_id="sales_master_references",
        )


def validate_sales_generated_data(
    sales_data: Mapping[str, pd.DataFrame],
    upstream_data: Mapping[str, pd.DataFrame] | None = None,
    adjusted_finished_goods_inventory: pd.DataFrame | None = None,
    profile_id: str | None = None,
) -> DataQualityReport:
    """Validate a generated Sales v1 dataset."""

    return SalesDataQualityEngine().validate_dataset(
        sales_data=sales_data,
        upstream_data=upstream_data,
        adjusted_finished_goods_inventory=adjusted_finished_goods_inventory,
        profile_id=profile_id,
    )


def get_sales_validation_rules() -> tuple[str, ...]:
    """Return active Sales validation rule IDs."""

    return SALES_V1_VALIDATION_RULES


def _expected_inventory_rollup(
    original_inventory: pd.DataFrame,
    receipt: pd.DataFrame,
    shipment_line: pd.DataFrame,
    reservations: pd.DataFrame,
    return_line: pd.DataFrame,
) -> pd.DataFrame:
    receipt_frame = receipt.copy()
    receipt_frame["ReceiptValue"] = (
        _num(receipt_frame["ReceiptValue"]) if "ReceiptValue" in receipt_frame.columns else _num(receipt_frame["GoodQuantity"]) * _num(receipt_frame["UnitCost"])
    )
    receipt_rollup = receipt_frame.groupby(["ProductID", "PlantID", "WarehouseID"]).agg(
        OnHandQuantity=("GoodQuantity", "sum"),
        ReceiptValue=("ReceiptValue", "sum"),
    ).reset_index()
    receipt_rollup["AverageUnitCost"] = receipt_rollup["ReceiptValue"] / receipt_rollup["OnHandQuantity"].replace(0, pd.NA)
    base = original_inventory[["FinishedGoodsInventoryID", "ProductID", "PlantID", "WarehouseID"]].merge(
        receipt_rollup,
        on=["ProductID", "PlantID", "WarehouseID"],
        how="left",
    ).fillna({"OnHandQuantity": 0.0, "ReceiptValue": 0.0, "AverageUnitCost": 0.0})
    shipped_by_inventory = shipment_line.groupby("FinishedGoodsInventoryID")["ShippedQuantity"].sum()
    if return_line.empty:
        restocked_by_inventory = pd.Series(dtype=float)
    else:
        restocked = return_line.merge(shipment_line[["ShipmentLineID", "FinishedGoodsInventoryID"]], on="ShipmentLineID")
        restocked_by_inventory = restocked.groupby("FinishedGoodsInventoryID")["RestockedQuantity"].sum()
    active_reserved = reservations[reservations["ReservationStatus"].astype(str).str.lower() == "reserved"]
    reserved_by_inventory = active_reserved.groupby("FinishedGoodsInventoryID")["ReservedQuantity"].sum()
    base["OnHandQuantity"] = (
        _num(base["OnHandQuantity"])
        - base["FinishedGoodsInventoryID"].map(shipped_by_inventory).fillna(0.0)
        + base["FinishedGoodsInventoryID"].map(restocked_by_inventory).fillna(0.0)
    ).round(2)
    base["ReservedQuantity"] = base["FinishedGoodsInventoryID"].map(reserved_by_inventory).fillna(0.0).round(2)
    base["AvailableQuantity"] = (base["OnHandQuantity"] - base["ReservedQuantity"]).round(2)
    base["AverageUnitCost"] = _num(base["AverageUnitCost"]).fillna(0.0)
    return base[["ProductID", "PlantID", "WarehouseID", "OnHandQuantity", "ReservedQuantity", "AvailableQuantity", "AverageUnitCost"]]


def _fk(
    report: DataQualityReport,
    child: pd.DataFrame,
    child_table: str,
    child_column: str,
    parent: pd.DataFrame,
    parent_column: str,
    rule_id: str,
) -> None:
    if child_column not in child.columns or parent_column not in parent.columns:
        return
    mask = child[child_column].isin(parent[parent_column])
    _record(
        report,
        bool(mask.all()),
        "SALES_FK_INTEGRITY",
        f"{child_table}.{child_column} contains values missing from parent {parent_column}.",
        "Generate Sales foreign keys from existing parent rows.",
        table_name=child_table,
        column_name=child_column,
        failed_rows=child[~mask],
        rule_id=rule_id,
    )


def _record(
    report: DataQualityReport,
    passed: bool,
    check_type: str,
    message: str,
    suggested_fix: str,
    table_name: str | None = None,
    column_name: str | None = None,
    failed_rows: pd.DataFrame | None = None,
    rule_id: str | None = None,
) -> None:
    report.record_check(passed)
    if table_name and table_name in report.table_summaries:
        report.table_summaries[table_name].checks_run += 1
    if not passed:
        report.add_issue(
            "error",
            check_type,
            message,
            suggested_fix,
            table_name=table_name,
            column_name=column_name,
            rule_id=rule_id,
            sample_failed_rows=_sample_rows(failed_rows) if failed_rows is not None else [],
        )


def _sample_rows(dataframe: pd.DataFrame | None, limit: int = 5) -> list[dict[str, Any]]:
    if dataframe is None or dataframe.empty:
        return []
    return dataframe.head(limit).where(pd.notna(dataframe.head(limit)), None).to_dict(orient="records")


def _num(series: Any) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _near(left: pd.Series, right: pd.Series, tolerance: float = TOLERANCE) -> pd.Series:
    return (left - right).abs() <= tolerance


def _invoice_status(total_invoice_amount: float, paid_amount: float) -> str:
    if paid_amount >= round(float(total_invoice_amount), 2) - TOLERANCE:
        return "Paid"
    if paid_amount > TOLERANCE:
        return "PartiallyPaid"
    return "Open"


__all__ = [
    "SALES_V1_VALIDATION_RULES",
    "SalesDataQualityEngine",
    "get_sales_validation_rules",
    "validate_sales_generated_data",
]
