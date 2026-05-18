"""Procurement-specific reconciliation checks for final generated data."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

import numpy as np
import pandas as pd

from procurement_data_generator.core.contracts.data_quality_report import (
    DataQualityReport,
    ReconciliationSummary,
)
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.validation.generic_validator import _json_safe
from procurement_data_generator.modules.procurement.quantity_precision import is_whole_quantity, requires_integer_quantity
from procurement_data_generator.modules.procurement.role_catalog import PROCUREMENT_V1_UNSUPPORTED_MESSAGE
from procurement_data_generator.modules.procurement.validation_rules import ProcurementGeneratedDataValidator
from procurement_data_generator.modules.shared.operating_scope import (
    get_expected_plant_count,
    get_expected_warehouse_count,
)


class ProcurementReconciler:
    """Run procurement lifecycle and financial/inventory reconciliation checks."""

    def reconcile_dataset(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        plan: LLMGenerationPlan | None = None,
        model_version: str = "v2",
    ) -> DataQualityReport:
        report = DataQualityReport()
        if model_version != "v2":
            raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)

        self._reconcile_v2(dataframes, plan, report)
        return report

    def _reconcile_dates(self, by_role: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        self._date_order(
            by_role.get("purchase_requisition_header"),
            by_role.get("purchase_order_header"),
            "RequisitionID",
            "RequisitionDate",
            "OrderDate",
            "DATE_REQUISITION_TO_ORDER",
            report,
        )
        self._date_order(
            by_role.get("purchase_order_header"),
            by_role.get("shipment_header"),
            "PurchaseOrderID",
            "OrderDate",
            "ShipmentDate",
            "DATE_ORDER_TO_SHIPMENT",
            report,
        )
        self._date_order(
            by_role.get("shipment_header"),
            by_role.get("goods_receipt_header"),
            "ShipmentID",
            "ShipmentDate",
            "ReceiptDate",
            "DATE_SHIPMENT_TO_RECEIPT",
            report,
        )
        grl = by_role.get("goods_receipt_line")
        qih = by_role.get("quality_inspection_header")
        grh = by_role.get("goods_receipt_header")
        if grl is not None and qih is not None and grh is not None and {"GoodsReceiptLineID", "GoodsReceiptID"}.issubset(grl.columns):
            receipt_dates = grl[["GoodsReceiptLineID", "GoodsReceiptID"]].merge(
                grh[["GoodsReceiptID", "ReceiptDate"]],
                on="GoodsReceiptID",
                how="left",
            )
            self._date_order(receipt_dates, qih, "GoodsReceiptLineID", "ReceiptDate", "InspectionDate", "DATE_RECEIPT_TO_INSPECTION", report)
        qil = by_role.get("quality_inspection_line")
        it = by_role.get("inventory_transaction")
        if qil is not None and qih is not None and it is not None and {"InspectionLineID", "InspectionID"}.issubset(qil.columns):
            inspection_dates = qil[["InspectionLineID", "InspectionID"]].merge(
                qih[["InspectionID", "InspectionDate"]],
                on="InspectionID",
                how="left",
            )
            self._date_order(inspection_dates, it, "InspectionLineID", "InspectionDate", "TransactionDate", "DATE_INSPECTION_TO_INVENTORY", report)

    def _reconcile_plant_and_warehouse(self, by_role: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        prh = by_role.get("purchase_requisition_header")
        poh = by_role.get("purchase_order_header")
        sh = by_role.get("shipment_header")
        grh = by_role.get("goods_receipt_header")
        wh = by_role.get("warehouse_dimension")
        grl = by_role.get("goods_receipt_line")
        qih = by_role.get("quality_inspection_header")
        qil = by_role.get("quality_inspection_line")
        it = by_role.get("inventory_transaction")

        self._equality_join(prh, poh, "RequisitionID", "PlantID", "PlantID", "PLANT_REQUISITION_TO_PO", "error", report)
        if grh is not None and sh is not None and poh is not None and {"ShipmentID", "PlantID"}.issubset(grh.columns):
            merged = grh.merge(sh[["ShipmentID", "PurchaseOrderID"]], on="ShipmentID", how="left").merge(
                poh[["PurchaseOrderID", "PlantID"]],
                on="PurchaseOrderID",
                how="left",
                suffixes=("_receipt", "_po"),
            )
            self._compare_mask(
                merged,
                merged["PlantID_receipt"] == merged["PlantID_po"],
                "PLANT_PO_TO_RECEIPT",
                "GoodsReceiptHeader.PlantID must match linked PurchaseOrderHeader.PlantID.",
                "Carry PlantID through ShipmentHeader -> PurchaseOrderHeader lineage.",
                "error",
                "GoodsReceiptHeader",
                "PlantID",
                report,
            )
        if grh is not None and wh is not None and {"WarehouseID", "PlantID"}.issubset(grh.columns) and {"WarehouseID", "PlantID"}.issubset(wh.columns):
            merged = grh.merge(wh[["WarehouseID", "PlantID"]], on="WarehouseID", how="left", suffixes=("_receipt", "_warehouse"))
            self._compare_mask(
                merged,
                merged["PlantID_receipt"] == merged["PlantID_warehouse"],
                "WAREHOUSE_PLANT_ALIGNMENT",
                "GoodsReceiptHeader.WarehouseID must belong to the same PlantID.",
                "Select warehouses from the linked receipt plant.",
                "error",
                "GoodsReceiptHeader",
                "WarehouseID",
                report,
            )
        if it is not None and qil is not None and qih is not None and grl is not None and grh is not None:
            if {"InspectionLineID", "InspectionID"}.issubset(qil.columns) and {"InspectionID", "GoodsReceiptLineID"}.issubset(qih.columns):
                merged = (
                    it.merge(qil[["InspectionLineID", "InspectionID"]], on="InspectionLineID", how="left")
                    .merge(qih[["InspectionID", "GoodsReceiptLineID"]], on="InspectionID", how="left")
                    .merge(grl[["GoodsReceiptLineID", "GoodsReceiptID"]], on="GoodsReceiptLineID", how="left")
                    .merge(grh[["GoodsReceiptID", "PlantID", "WarehouseID"]], on="GoodsReceiptID", how="left", suffixes=("_txn", "_receipt"))
                )
                self._compare_mask(
                    merged,
                    (merged["PlantID_txn"] == merged["PlantID_receipt"]) & (merged["WarehouseID_txn"] == merged["WarehouseID_receipt"]),
                    "INVENTORY_TRANSACTION_LOCATION_LINEAGE",
                    "InventoryTransaction PlantID/WarehouseID must match linked receipt lineage.",
                    "Carry PlantID and WarehouseID from receipt through inspection to inventory transactions.",
                    "error",
                    "InventoryTransaction",
                    None,
                    report,
                )

    def _reconcile_quantities(self, by_role: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        self._positive(by_role.get("purchase_requisition_line"), "RequestedQuantity", "REQUESTED_QUANTITY_POSITIVE", report)
        self._positive(by_role.get("purchase_order_line"), "OrderedQuantity", "ORDERED_QUANTITY_POSITIVE", report)
        self._quantity_join(
            by_role.get("shipment_line"),
            by_role.get("purchase_order_line"),
            "PurchaseOrderLineID",
            "ShippedQuantity",
            "OrderedQuantity",
            "SHIPPED_LE_ORDERED",
            report,
        )
        self._quantity_join(
            by_role.get("goods_receipt_line"),
            by_role.get("shipment_line"),
            "ShipmentLineID",
            "ReceivedQuantity",
            "ShippedQuantity",
            "RECEIVED_LE_SHIPPED",
            report,
        )
        grl = by_role.get("goods_receipt_line")
        if grl is not None:
            if {"DamagedQuantity", "ReceivedQuantity"}.issubset(grl.columns):
                self._compare_mask(
                    grl,
                    pd.to_numeric(grl["DamagedQuantity"], errors="coerce") <= pd.to_numeric(grl["ReceivedQuantity"], errors="coerce"),
                    "DAMAGED_LE_RECEIVED",
                    "DamagedQuantity must be <= ReceivedQuantity.",
                    "Limit damaged quantity to received quantity.",
                    "error",
                    "GoodsReceiptLine",
                    "DamagedQuantity",
                    report,
                )
            if {"ShortQuantity", "ShippedQuantity", "ReceivedQuantity"}.issubset(grl.columns):
                expected = pd.to_numeric(grl["ShippedQuantity"], errors="coerce") - pd.to_numeric(grl["ReceivedQuantity"], errors="coerce")
                self._numeric_compare(grl, grl["ShortQuantity"], expected, "GRN_SHORT_QTY", "ShortQuantity must equal ShippedQuantity - ReceivedQuantity.", "GoodsReceiptLine", "ShortQuantity", report)
        qil = by_role.get("quality_inspection_line")
        qih = by_role.get("quality_inspection_header")
        if qil is not None:
            if {"AcceptedQuantity", "RejectedQuantity", "InspectedQuantity"}.issubset(qil.columns):
                expected = pd.to_numeric(qil["AcceptedQuantity"], errors="coerce") + pd.to_numeric(qil["RejectedQuantity"], errors="coerce")
                self._numeric_compare(qil, expected, qil["InspectedQuantity"], "QUALITY_ACCEPT_REJECT_TOTAL", "AcceptedQuantity + RejectedQuantity must equal InspectedQuantity.", "QualityInspectionLine", None, report)
        if qil is not None and qih is not None and grl is not None and {"InspectionID", "InspectedQuantity"}.issubset(qil.columns):
            if {"InspectionID", "GoodsReceiptLineID"}.issubset(qih.columns) and {"GoodsReceiptLineID", "ReceivedQuantity"}.issubset(grl.columns):
                merged = qil.merge(qih[["InspectionID", "GoodsReceiptLineID"]], on="InspectionID", how="left").merge(
                    grl[["GoodsReceiptLineID", "ReceivedQuantity"]],
                    on="GoodsReceiptLineID",
                    how="left",
                )
                self._compare_mask(
                    merged,
                    pd.to_numeric(merged["InspectedQuantity"], errors="coerce") <= pd.to_numeric(merged["ReceivedQuantity"], errors="coerce"),
                    "INSPECTED_LE_RECEIVED",
                    "InspectedQuantity should be <= linked ReceivedQuantity.",
                    "Base inspected quantity on the linked receipt line quantity.",
                    "error",
                    "QualityInspectionLine",
                    "InspectedQuantity",
                    report,
                )

    def _reconcile_amounts(self, by_role: dict[str, pd.DataFrame], plan: LLMGenerationPlan | None, report: DataQualityReport) -> None:
        pol = by_role.get("purchase_order_line")
        poh = by_role.get("purchase_order_header")
        amount_tolerance = self._tolerance(plan, "PurchaseOrderLine", "LineAmount", 0.01)
        total_tolerance = self._tolerance(plan, "PurchaseOrderHeader", "TotalAmount", 0.01)
        if pol is not None and {"OrderedQuantity", "UnitPrice", "LineAmount"}.issubset(pol.columns):
            expected = pd.to_numeric(pol["OrderedQuantity"], errors="coerce") * pd.to_numeric(pol["UnitPrice"], errors="coerce")
            self._numeric_compare(
                pol,
                pol["LineAmount"],
                expected,
                "PO_LINE_AMOUNT_RECONCILIATION",
                "PurchaseOrderLine.LineAmount must equal OrderedQuantity * UnitPrice.",
                "PurchaseOrderLine",
                "LineAmount",
                report,
                tolerance=amount_tolerance,
            )
        if poh is not None and pol is not None and {"PurchaseOrderID", "TotalAmount"}.issubset(poh.columns) and {"PurchaseOrderID", "LineAmount"}.issubset(pol.columns):
            grouped = pol.groupby("PurchaseOrderID", dropna=False)["LineAmount"].sum().reset_index().rename(columns={"LineAmount": "ExpectedTotal"})
            merged = poh.merge(grouped, on="PurchaseOrderID", how="left")
            self._numeric_compare(
                merged,
                merged["TotalAmount"],
                merged["ExpectedTotal"].fillna(0),
                "PO_HEADER_TOTAL_RECONCILIATION",
                "PurchaseOrderHeader.TotalAmount must equal SUM(PurchaseOrderLine.LineAmount).",
                "PurchaseOrderHeader",
                "TotalAmount",
                report,
                tolerance=total_tolerance,
            )

    def _reconcile_inventory(self, by_role: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        it = by_role.get("inventory_transaction")
        qil = by_role.get("quality_inspection_line")
        if it is not None and qil is not None and {"InspectionLineID", "TransactionQuantity"}.issubset(it.columns) and {"InspectionLineID", "AcceptedQuantity"}.issubset(qil.columns):
            merged = it.merge(qil[["InspectionLineID", "AcceptedQuantity"]], on="InspectionLineID", how="left")
            self._numeric_compare(
                merged,
                merged["TransactionQuantity"],
                merged["AcceptedQuantity"],
                "INVENTORY_TRANSACTION_ACCEPTED_QTY",
                "InventoryTransaction.TransactionQuantity must equal linked AcceptedQuantity.",
                "InventoryTransaction",
                "TransactionQuantity",
                report,
            )

    def _reconcile_statuses(self, by_role: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        qil = by_role.get("quality_inspection_line")
        if qil is not None and {"RejectedQuantity", "ResultStatus"}.issubset(qil.columns):
            rejected = pd.to_numeric(qil["RejectedQuantity"], errors="coerce").fillna(0)
            mask = ~((rejected > 0) & qil["ResultStatus"].astype(str).str.lower().eq("passed"))
            self._compare_mask(
                qil,
                mask,
                "QUALITY_REJECTION_STATUS",
                "Rows with rejected quantity should not have ResultStatus = Passed.",
                "Use PartiallyRejected or Failed when rejected quantity is present.",
                "warning",
                "QualityInspectionLine",
                "ResultStatus",
                report,
            )
        grl = by_role.get("goods_receipt_line")
        grh = by_role.get("goods_receipt_header")
        if grl is not None and grh is not None and {"GoodsReceiptID", "ShortQuantity"}.issubset(grl.columns) and {"GoodsReceiptID", "ReceiptStatus"}.issubset(grh.columns):
            short_receipts = set(grl.loc[pd.to_numeric(grl["ShortQuantity"], errors="coerce").fillna(0) > 0, "GoodsReceiptID"])
            if short_receipts:
                impacted = grh[grh["GoodsReceiptID"].isin(short_receipts)]
                suspicious = impacted["ReceiptStatus"].astype(str).str.lower().eq("received")
                self._compare_mask(
                    impacted,
                    ~suspicious,
                    "SHORT_RECEIPT_STATUS",
                    "Receipts with short quantities are marked as fully Received.",
                    "Use a partial/short receipt status when metadata AllowedValues support it.",
                    "warning",
                    "GoodsReceiptHeader",
                    "ReceiptStatus",
                    report,
                )

    def _reconcile_v2(self, data: dict[str, pd.DataFrame], plan: LLMGenerationPlan | None, report: DataQualityReport) -> None:
        required = {
            "SupplierMaster", "SupplierComponent", "ComponentMaster", "Plant", "Warehouse",
            "PurchaseRequisition", "PurchaseReqLine", "RFQHeader", "RFQLine", "SupplierQuotation",
            "SupplierQuotationLn", "PurchaseOrderHdr", "PurchaseOrderLine", "POSchedule", "ShipmentHdr",
            "ShipmentLine", "GoodsReceiptHeader", "GoodsReceiptLine", "IncomingInspection", "InspectionResult",
            "InventoryReceiptDetail", "InventoryTransaction", "Inventory", "SupplierInvoice", "PaymentTransaction",
        }
        missing = sorted(required - set(data))
        if missing:
            for table_name in missing:
                report.record_check(False)
                report.add_issue(
                    "error",
                    "V2_REQUIRED_TABLE_MISSING",
                    f"Required Procurement v2 table {table_name} is missing from final data.",
                    "Generate every required Procurement v2 lifecycle table.",
                    table_name=table_name,
            )
            return
        self._v2_operating_scope(data, report)
        self._v2_locations(data, report)
        self._v2_dates(data, report)
        self._v2_quantities(data, report)
        self._v2_component_quantity_precision(data, report)
        self._v2_cumulative_quantity_lifecycle(data, report)
        self._v2_rfq_quotation(data, report)
        self._v2_po_schedule_shipment(data, plan, report)
        self._v2_receipt_inspection_inventory(data, report)
        self._v2_inventory_receipt_detail(data, report)
        self._v2_inventory_snapshot(data, report)
        self._v2_invoice_payment(data, plan, report)
        self._v2_status_and_rejection_reasons(data, report)

    def _v2_operating_scope(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        plant = data["Plant"]
        warehouse = data["Warehouse"]
        expected_plant_count = get_expected_plant_count()
        expected_warehouse_count = get_expected_warehouse_count()

        plant_count_ok = len(plant) == expected_plant_count
        report.record_check(plant_count_ok)
        if not plant_count_ok:
            report.add_issue(
                "error",
                "V2_OPERATING_SCOPE_PLANT_COUNT",
                f"Procurement v2 must contain exactly {expected_plant_count} Plant row.",
                "Use the shared operating scope plant count during Procurement v2 generation.",
                table_name="Plant",
                sample_failed_rows=self._sample_rows(plant),
            )

        warehouse_count_ok = len(warehouse) == expected_warehouse_count
        report.record_check(warehouse_count_ok)
        if not warehouse_count_ok:
            report.add_issue(
                "error",
                "V2_OPERATING_SCOPE_WAREHOUSE_COUNT",
                f"Procurement v2 must contain exactly {expected_warehouse_count} Warehouse row.",
                "Use the shared operating scope warehouse count during Procurement v2 generation.",
                table_name="Warehouse",
                sample_failed_rows=self._sample_rows(warehouse),
            )

        if "PlantID" not in plant.columns or "WarehouseID" not in warehouse.columns:
            return
        plant_ids = plant["PlantID"].dropna().unique()
        warehouse_ids = warehouse["WarehouseID"].dropna().unique()
        if len(plant_ids) != 1 or len(warehouse_ids) != 1:
            return
        single_plant_id = plant_ids[0]
        single_warehouse_id = warehouse_ids[0]

        if "PlantID" in warehouse.columns:
            self._compare_mask(
                warehouse,
                warehouse["PlantID"].eq(single_plant_id),
                "V2_OPERATING_SCOPE_WAREHOUSE_PLANT",
                "Warehouse.PlantID must reference the single Procurement PlantID.",
                "Assign the single PlantID from Plant to Warehouse.",
                "error",
                "Warehouse",
                "PlantID",
                report,
            )

        for table_name, dataframe in data.items():
            if table_name == "InventoryBalance":
                continue
            if "PlantID" in dataframe.columns:
                self._compare_mask(
                    dataframe,
                    dataframe["PlantID"].eq(single_plant_id),
                    "V2_OPERATING_SCOPE_PLANT_REFERENCE",
                    f"{table_name}.PlantID must use the single Procurement PlantID.",
                    "Carry the single PlantID through all Procurement v2 location references.",
                    "error",
                    table_name,
                    "PlantID",
                    report,
                )
            if "WarehouseID" in dataframe.columns:
                self._compare_mask(
                    dataframe,
                    dataframe["WarehouseID"].eq(single_warehouse_id),
                    "V2_OPERATING_SCOPE_WAREHOUSE_REFERENCE",
                    f"{table_name}.WarehouseID must use the single Procurement WarehouseID.",
                    "Carry the single WarehouseID through all Procurement v2 location references.",
                    "error",
                    table_name,
                    "WarehouseID",
                    report,
                )

    def _v2_locations(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        wh = data["Warehouse"][["WarehouseID", "PlantID"]]
        grh = data["GoodsReceiptHeader"].merge(wh, on="WarehouseID", how="left", suffixes=("_receipt", "_warehouse"))
        self._compare_mask(grh, grh["PlantID_receipt"] == grh["PlantID_warehouse"], "V2_RECEIPT_WAREHOUSE_PLANT", "GoodsReceiptHeader.WarehouseID must belong to GoodsReceiptHeader.PlantID.", "Select warehouses from the same plant.", "error", "GoodsReceiptHeader", "WarehouseID", report)
        it = data["InventoryTransaction"].merge(wh, on="WarehouseID", how="left", suffixes=("_txn", "_warehouse"))
        self._compare_mask(it, it["PlantID_txn"] == it["PlantID_warehouse"], "V2_INVENTORY_WAREHOUSE_PLANT", "InventoryTransaction.WarehouseID must belong to InventoryTransaction.PlantID.", "Carry warehouse from receipt lineage.", "error", "InventoryTransaction", "WarehouseID", report)
        inventory = data["Inventory"].merge(wh, on="WarehouseID", how="left", suffixes=("_inventory", "_warehouse"))
        self._compare_mask(inventory, inventory["PlantID_inventory"] == inventory["PlantID_warehouse"], "V2_INVENTORY_SNAPSHOT_WAREHOUSE_PLANT", "Inventory.WarehouseID must belong to Inventory.PlantID.", "Build inventory balances from transaction groups with matching warehouse plant.", "error", "Inventory", "WarehouseID", report)
        receipt_po = data["GoodsReceiptHeader"].merge(data["ShipmentHdr"][["ShipmentID", "PurchaseOrderID"]], on="ShipmentID", how="left").merge(data["PurchaseOrderHdr"][["PurchaseOrderID", "PlantID"]], on="PurchaseOrderID", how="left", suffixes=("_receipt", "_po"))
        self._compare_mask(receipt_po, receipt_po["PlantID_receipt"] == receipt_po["PlantID_po"], "V2_RECEIPT_PO_PLANT", "GoodsReceiptHeader.PlantID must match linked PurchaseOrderHdr.PlantID.", "Carry PlantID through shipment lineage.", "error", "GoodsReceiptHeader", "PlantID", report)

    def _v2_dates(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        self._same_table_date(data["PurchaseRequisition"], "RequisitionDate", "RequiredDate", "V2_REQ_REQUIRED_DATE", "PurchaseRequisition", report)
        self._date_order(data["PurchaseRequisition"], data["RFQHeader"], "RequisitionID", "RequisitionDate", "RFQDate", "V2_REQ_TO_RFQ_DATE", report)
        self._same_table_date(data["RFQHeader"], "RFQDate", "RFQDueDate", "V2_RFQ_DUE_DATE", "RFQHeader", report)
        self._date_order(data["RFQHeader"], data["SupplierQuotation"], "RFQID", "RFQDate", "QuotationDate", "V2_RFQ_TO_QUOTE_DATE", report)
        self._same_table_date(data["SupplierQuotation"], "QuotationDate", "ValidUntilDate", "V2_QUOTE_VALID_DATE", "SupplierQuotation", report)
        self._date_order(data["SupplierQuotation"], data["PurchaseOrderHdr"], "QuotationID", "QuotationDate", "OrderDate", "V2_QUOTE_TO_PO_DATE", report)
        self._same_table_date(data["PurchaseOrderHdr"], "OrderDate", "ExpectedDeliveryDate", "V2_PO_EXPECTED_DATE", "PurchaseOrderHdr", report)
        po_line_dates = data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID"]].merge(data["PurchaseOrderHdr"][["PurchaseOrderID", "OrderDate"]], on="PurchaseOrderID", how="left")
        self._date_order(po_line_dates, data["POSchedule"], "PurchaseOrderLineID", "OrderDate", "ScheduledDeliveryDate", "V2_PO_TO_SCHEDULE_DATE", report)
        self._date_order(data["PurchaseOrderHdr"], data["ShipmentHdr"], "PurchaseOrderID", "OrderDate", "ShipmentDate", "V2_PO_TO_SHIPMENT_DATE", report)
        self._date_order(data["ShipmentHdr"], data["GoodsReceiptHeader"], "ShipmentID", "ShipmentDate", "ReceiptDate", "V2_SHIPMENT_TO_RECEIPT_DATE", report)
        receipt_dates = data["GoodsReceiptLine"][["GoodsReceiptLineID", "GoodsReceiptID"]].merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ReceiptDate"]], on="GoodsReceiptID", how="left")
        self._date_order(receipt_dates, data["IncomingInspection"], "GoodsReceiptLineID", "ReceiptDate", "InspectionDate", "V2_RECEIPT_TO_INSPECTION_DATE", report)
        inspection_dates = data["InspectionResult"][["InspectionResultID", "InspectionID"]].merge(data["IncomingInspection"][["InspectionID", "InspectionDate"]], on="InspectionID", how="left")
        self._date_order(inspection_dates, data["InventoryTransaction"], "InspectionResultID", "InspectionDate", "TransactionDate", "V2_INSPECTION_TO_INVENTORY_DATE", report)
        self._date_order(data["GoodsReceiptHeader"], data["SupplierInvoice"], "GoodsReceiptID", "ReceiptDate", "InvoiceDate", "V2_RECEIPT_TO_INVOICE_DATE", report)
        self._same_table_date(data["SupplierInvoice"], "InvoiceDate", "DueDate", "V2_INVOICE_DUE_DATE", "SupplierInvoice", report)
        self._date_order(data["SupplierInvoice"], data["PaymentTransaction"], "SupplierInvoiceID", "InvoiceDate", "PaymentDate", "V2_INVOICE_TO_PAYMENT_DATE", report)

    def _v2_quantities(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        self._positive(data["PurchaseReqLine"], "RequestedQuantity", "V2_REQUESTED_QTY_POSITIVE", report)
        self._positive(data["RFQLine"], "RFQQuantity", "V2_RFQ_QTY_POSITIVE", report)
        self._positive(data["SupplierQuotationLn"], "QuotedQuantity", "V2_QUOTED_QTY_POSITIVE", report)
        self._positive(data["PurchaseOrderLine"], "OrderedQuantity", "V2_ORDERED_QTY_POSITIVE", report)
        self._positive(data["POSchedule"], "ScheduledQuantity", "V2_SCHEDULE_QTY_POSITIVE", report)
        self._positive(data["ShipmentLine"], "ShippedQuantity", "V2_SHIPPED_QTY_POSITIVE", report)
        sched = data["POSchedule"].groupby("PurchaseOrderLineID", dropna=False)["ScheduledQuantity"].sum().reset_index().merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID", how="left")
        self._compare_mask(sched, sched["ScheduledQuantity"] <= sched["OrderedQuantity"] + 0.0001, "V2_SCHEDULE_LE_ORDERED", "Total POSchedule.ScheduledQuantity per PO line must be <= OrderedQuantity.", "Cap schedules by ordered quantity.", "error", "POSchedule", "ScheduledQuantity", report)
        shipped = data["ShipmentLine"].groupby("POScheduleID", dropna=False)["ShippedQuantity"].sum().reset_index().merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID", how="left")
        self._compare_mask(shipped, shipped["ShippedQuantity"] <= shipped["ScheduledQuantity"] + 0.0001, "V2_SHIPPED_LE_SCHEDULED", "Total ShipmentLine.ShippedQuantity per schedule must be <= ScheduledQuantity.", "Cap shipped quantity by schedule.", "error", "ShipmentLine", "ShippedQuantity", report)

    def _v2_component_quantity_precision(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        component = data["ComponentMaster"][["ComponentID", "UOM"]].copy()
        component["__requires_integer_quantity"] = component["UOM"].map(requires_integer_quantity)

        direct_specs = [
            ("PurchaseReqLine", ["RequestedQuantity"]),
            ("RFQLine", ["RFQQuantity"]),
            ("SupplierQuotationLn", ["QuotedQuantity"]),
            ("PurchaseOrderLine", ["OrderedQuantity"]),
            ("ShipmentLine", ["ShippedQuantity"]),
            ("GoodsReceiptLine", ["ShippedQuantity", "ReceivedQuantity", "DamagedQuantity", "ShortQuantity"]),
            ("InventoryReceiptDetail", ["OrderedQuantity", "ShippedQuantity", "ReceivedQuantity", "InspectedQuantity", "AcceptedQuantity", "RejectedQuantity"]),
            ("InventoryTransaction", ["TransactionQuantity"]),
            ("Inventory", ["OnHandQuantity", "AvailableQuantity"]),
        ]
        for table_name, quantity_columns in direct_specs:
            dataframe = data.get(table_name)
            if dataframe is None or "ComponentID" not in dataframe.columns:
                continue
            merged = dataframe.merge(component, on="ComponentID", how="left")
            for column_name in quantity_columns:
                if column_name in merged.columns:
                    self._integer_quantity_mask(merged, table_name, column_name, report)

        schedule = data["POSchedule"].merge(
            data["PurchaseOrderLine"][["PurchaseOrderLineID", "ComponentID"]],
            on="PurchaseOrderLineID",
            how="left",
        ).merge(component, on="ComponentID", how="left")
        self._integer_quantity_mask(schedule, "POSchedule", "ScheduledQuantity", report)

        inspection = (
            data["InspectionResult"]
            .merge(data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID"]], on="InspectionID", how="left")
            .merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "ComponentID"]], on="GoodsReceiptLineID", how="left")
            .merge(component, on="ComponentID", how="left")
        )
        for column_name in ["InspectedQuantity", "AcceptedQuantity", "RejectedQuantity"]:
            self._integer_quantity_mask(inspection, "InspectionResult", column_name, report)

    def _integer_quantity_mask(self, dataframe: pd.DataFrame, table_name: str, column_name: str, report: DataQualityReport) -> None:
        integer_required = dataframe["__requires_integer_quantity"].map(lambda value: bool(value) if pd.notna(value) else False)
        quantity = pd.to_numeric(dataframe[column_name], errors="coerce")
        whole = quantity.map(is_whole_quantity)
        mask = (~integer_required) | whole
        self._compare_mask(
            dataframe,
            mask,
            f"V2_INTEGER_QUANTITY_PRECISION_{table_name.upper()}_{column_name.upper()}",
            f"{table_name}.{column_name} must be a whole number for countable component UOMs.",
            "Generate integer quantities for countable component UOMs such as Each, Box, Set, PCS, Module, Assembly, Device, Sensor, Motor, and BatteryPack.",
            "error",
            table_name,
            column_name,
            report,
        )

    def _v2_cumulative_quantity_lifecycle(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        tolerance = 0.0001

        rfq = data["RFQLine"].merge(
            data["PurchaseReqLine"][["RequisitionLineID", "RequestedQuantity"]],
            on="RequisitionLineID",
            how="left",
        )
        self._compare_mask(
            rfq,
            pd.to_numeric(rfq["RFQQuantity"], errors="coerce") <= pd.to_numeric(rfq["RequestedQuantity"], errors="coerce") + tolerance,
            "RFQ_QUANTITY_EXCEEDS_REQUESTED",
            "RFQLine.RFQQuantity must not exceed PurchaseReqLine.RequestedQuantity.",
            "Generate RFQ quantity from the linked requisition line requested quantity.",
            "error",
            "RFQLine",
            "RFQQuantity",
            report,
        )

        quoted = data["SupplierQuotationLn"].merge(
            data["RFQLine"][["RFQLineID", "RFQQuantity"]],
            on="RFQLineID",
            how="left",
        )
        self._compare_mask(
            quoted,
            pd.to_numeric(quoted["QuotedQuantity"], errors="coerce") <= pd.to_numeric(quoted["RFQQuantity"], errors="coerce") + tolerance,
            "QUOTED_QUANTITY_EXCEEDS_RFQ",
            "SupplierQuotationLn.QuotedQuantity must not exceed RFQLine.RFQQuantity.",
            "Generate quoted quantity from the linked RFQ line quantity.",
            "error",
            "SupplierQuotationLn",
            "QuotedQuantity",
            report,
        )

        awarded = data["SupplierQuotationLn"][data["SupplierQuotationLn"]["AwardedFlag"].astype(str).isin(["1", "1.0", "True"])]
        ordered = data["PurchaseOrderLine"].merge(
            awarded[["QuotationLineID", "QuotedQuantity"]],
            on="QuotationLineID",
            how="left",
        )
        self._compare_mask(
            ordered,
            pd.to_numeric(ordered["OrderedQuantity"], errors="coerce") <= pd.to_numeric(ordered["QuotedQuantity"], errors="coerce") + tolerance,
            "ORDERED_QUANTITY_EXCEEDS_AWARDED_QUOTE",
            "PurchaseOrderLine.OrderedQuantity must not exceed awarded SupplierQuotationLn.QuotedQuantity.",
            "Create PO lines from awarded quote lines and cap ordered quantity by quoted quantity.",
            "error",
            "PurchaseOrderLine",
            "OrderedQuantity",
            report,
        )

        ordered_cumulative = self._v2_group_sum(
            data["PurchaseOrderLine"],
            ["QuotationLineID"],
            "OrderedQuantity",
            "ActualTotalOrderedQuantity",
        ).merge(data["SupplierQuotationLn"][["QuotationLineID", "QuotedQuantity"]], on="QuotationLineID", how="left")
        ordered_cumulative["ExcessQuantity"] = ordered_cumulative["ActualTotalOrderedQuantity"] - ordered_cumulative["QuotedQuantity"]
        self._compare_mask(
            ordered_cumulative,
            ordered_cumulative["ActualTotalOrderedQuantity"] <= ordered_cumulative["QuotedQuantity"] + tolerance,
            "PO_CUMULATIVE_EXCEEDS_AWARDED_QUOTE",
            "Total PurchaseOrderLine.OrderedQuantity for a QuotationLineID must not exceed SupplierQuotationLn.QuotedQuantity.",
            "Track remaining awarded quoted quantity by QuotationLineID when creating PO lines.",
            "error",
            "PurchaseOrderLine",
            "OrderedQuantity",
            report,
        )

        schedule = self._v2_group_sum(
            data["POSchedule"],
            ["PurchaseOrderLineID"],
            "ScheduledQuantity",
            "ActualTotalQuantity",
        ).merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID", how="left")
        schedule["ExcessQuantity"] = schedule["ActualTotalQuantity"] - schedule["OrderedQuantity"]
        self._compare_mask(
            schedule,
            schedule["ActualTotalQuantity"] <= schedule["OrderedQuantity"] + tolerance,
            "PO_SCHEDULE_CUMULATIVE_EXCEEDS_ORDERED",
            "Total POSchedule.ScheduledQuantity for a PurchaseOrderLineID must not exceed PurchaseOrderLine.OrderedQuantity.",
            "Track remaining ordered quantity when generating PO schedules.",
            "error",
            "POSchedule",
            "ScheduledQuantity",
            report,
        )
        self._numeric_compare(
            schedule,
            schedule["ActualTotalQuantity"],
            schedule["OrderedQuantity"],
            "FULL_RECEIVED_SCHEDULE_EQUALS_ORDERED",
            "For full-received Procurement v2, total POSchedule.ScheduledQuantity must equal PurchaseOrderLine.OrderedQuantity.",
            "POSchedule",
            "ScheduledQuantity",
            report,
            tolerance=tolerance,
        )

        shipped_schedule = self._v2_group_sum(
            data["ShipmentLine"],
            ["POScheduleID"],
            "ShippedQuantity",
            "ActualShippedQuantity",
        ).merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID", how="left")
        shipped_schedule["ExcessQuantity"] = shipped_schedule["ActualShippedQuantity"] - shipped_schedule["ScheduledQuantity"]
        self._compare_mask(
            shipped_schedule,
            shipped_schedule["ActualShippedQuantity"] <= shipped_schedule["ScheduledQuantity"] + tolerance,
            "SHIPMENT_CUMULATIVE_EXCEEDS_SCHEDULE",
            "Total ShipmentLine.ShippedQuantity for a POScheduleID must not exceed POSchedule.ScheduledQuantity.",
            "Track remaining scheduled quantity when generating shipment lines.",
            "error",
            "ShipmentLine",
            "ShippedQuantity",
            report,
        )
        self._numeric_compare(
            shipped_schedule,
            shipped_schedule["ActualShippedQuantity"],
            shipped_schedule["ScheduledQuantity"],
            "FULL_RECEIVED_SHIPPED_EQUALS_SCHEDULED",
            "For full-received Procurement v2, total ShipmentLine.ShippedQuantity must equal POSchedule.ScheduledQuantity.",
            "ShipmentLine",
            "ShippedQuantity",
            report,
            tolerance=tolerance,
        )

        shipped_po = self._v2_group_sum(
            data["ShipmentLine"],
            ["PurchaseOrderLineID"],
            "ShippedQuantity",
            "ActualTotalQuantity",
        ).merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID", how="left")
        shipped_po["ExcessQuantity"] = shipped_po["ActualTotalQuantity"] - shipped_po["OrderedQuantity"]
        self._compare_mask(
            shipped_po,
            shipped_po["ActualTotalQuantity"] <= shipped_po["OrderedQuantity"] + tolerance,
            "SHIPMENT_CUMULATIVE_EXCEEDS_ORDERED",
            "Total ShipmentLine.ShippedQuantity for a PurchaseOrderLineID must not exceed PurchaseOrderLine.OrderedQuantity.",
            "Track remaining PO quantity when generating shipment lines.",
            "error",
            "ShipmentLine",
            "ShippedQuantity",
            report,
        )
        self._numeric_compare(
            shipped_po,
            shipped_po["ActualTotalQuantity"],
            shipped_po["OrderedQuantity"],
            "FULL_RECEIVED_SHIPPED_EQUALS_ORDERED",
            "For full-received Procurement v2, total ShipmentLine.ShippedQuantity must equal PurchaseOrderLine.OrderedQuantity.",
            "ShipmentLine",
            "ShippedQuantity",
            report,
            tolerance=tolerance,
        )

        receipt_shipment = self._v2_group_sum(
            data["GoodsReceiptLine"],
            ["ShipmentLineID"],
            "ReceivedQuantity",
            "ActualReceivedQuantity",
        ).merge(data["ShipmentLine"][["ShipmentLineID", "ShippedQuantity"]], on="ShipmentLineID", how="left")
        receipt_shipment["ExcessQuantity"] = receipt_shipment["ActualReceivedQuantity"] - receipt_shipment["ShippedQuantity"]
        self._compare_mask(
            receipt_shipment,
            receipt_shipment["ActualReceivedQuantity"] <= receipt_shipment["ShippedQuantity"] + tolerance,
            "RECEIPT_CUMULATIVE_EXCEEDS_SHIPPED",
            "Total GoodsReceiptLine.ReceivedQuantity for a ShipmentLineID must not exceed ShipmentLine.ShippedQuantity.",
            "Track remaining shipped quantity when generating goods receipt lines.",
            "error",
            "GoodsReceiptLine",
            "ReceivedQuantity",
            report,
        )
        self._numeric_compare(
            receipt_shipment,
            receipt_shipment["ActualReceivedQuantity"],
            receipt_shipment["ShippedQuantity"],
            "FULL_RECEIVED_RECEIVED_EQUALS_SHIPPED",
            "For full-received Procurement v2, total GoodsReceiptLine.ReceivedQuantity must equal ShipmentLine.ShippedQuantity.",
            "GoodsReceiptLine",
            "ReceivedQuantity",
            report,
            tolerance=tolerance,
        )

        receipt_po = self._v2_group_sum(
            data["GoodsReceiptLine"],
            ["PurchaseOrderLineID"],
            "ReceivedQuantity",
            "ActualTotalQuantity",
        ).merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID", how="left")
        receipt_po["ExcessQuantity"] = receipt_po["ActualTotalQuantity"] - receipt_po["OrderedQuantity"]
        self._compare_mask(
            receipt_po,
            receipt_po["ActualTotalQuantity"] <= receipt_po["OrderedQuantity"] + tolerance,
            "RECEIPT_CUMULATIVE_EXCEEDS_ORDERED",
            "Total GoodsReceiptLine.ReceivedQuantity for a PurchaseOrderLineID must not exceed PurchaseOrderLine.OrderedQuantity.",
            "Track remaining PO quantity when generating goods receipt lines.",
            "error",
            "GoodsReceiptLine",
            "ReceivedQuantity",
            report,
        )
        self._numeric_compare(
            receipt_po,
            receipt_po["ActualTotalQuantity"],
            receipt_po["OrderedQuantity"],
            "FULL_RECEIVED_RECEIVED_EQUALS_ORDERED",
            "For full-received Procurement v2, total GoodsReceiptLine.ReceivedQuantity must equal PurchaseOrderLine.OrderedQuantity.",
            "GoodsReceiptLine",
            "ReceivedQuantity",
            report,
            tolerance=tolerance,
        )

        inspection = (
            data["InspectionResult"]
            .merge(data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID"]], on="InspectionID", how="left")
            .merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "ReceivedQuantity", "PurchaseOrderLineID"]], on="GoodsReceiptLineID", how="left")
        )
        self._compare_mask(
            inspection,
            pd.to_numeric(inspection["InspectedQuantity"], errors="coerce") <= pd.to_numeric(inspection["ReceivedQuantity"], errors="coerce") + tolerance,
            "INSPECTION_QUANTITY_EXCEEDS_RECEIVED",
            "InspectionResult.InspectedQuantity must not exceed GoodsReceiptLine.ReceivedQuantity.",
            "Generate inspected quantity from received quantity.",
            "error",
            "InspectionResult",
            "InspectedQuantity",
            report,
        )
        self._numeric_compare(
            inspection,
            inspection["InspectedQuantity"],
            inspection["ReceivedQuantity"],
            "FULL_RECEIVED_INSPECTED_EQUALS_RECEIVED",
            "For full-received Procurement v2, InspectionResult.InspectedQuantity must equal GoodsReceiptLine.ReceivedQuantity.",
            "InspectionResult",
            "InspectedQuantity",
            report,
            tolerance=tolerance,
        )
        self._numeric_compare(
            inspection,
            pd.to_numeric(inspection["AcceptedQuantity"], errors="coerce") + pd.to_numeric(inspection["RejectedQuantity"], errors="coerce"),
            inspection["InspectedQuantity"],
            "INSPECTION_ACCEPTED_REJECTED_MISMATCH",
            "InspectionResult.AcceptedQuantity plus RejectedQuantity must equal InspectedQuantity.",
            "InspectionResult",
            None,
            report,
            tolerance=tolerance,
        )
        self._numeric_compare(
            inspection,
            inspection["AcceptedQuantity"],
            inspection["InspectedQuantity"],
            "FULL_RECEIVED_ACCEPTED_EQUALS_INSPECTED",
            "For full-received Procurement v2, InspectionResult.AcceptedQuantity must equal InspectionResult.InspectedQuantity.",
            "InspectionResult",
            "AcceptedQuantity",
            report,
            tolerance=tolerance,
        )
        self._numeric_compare(
            inspection,
            inspection["RejectedQuantity"],
            0,
            "FULL_RECEIVED_REJECTED_QUANTITY_ZERO",
            "For full-received Procurement v2, InspectionResult.RejectedQuantity must be zero.",
            "InspectionResult",
            "RejectedQuantity",
            report,
            tolerance=tolerance,
        )

        accepted_po = self._v2_group_sum(
            inspection,
            ["PurchaseOrderLineID"],
            "AcceptedQuantity",
            "ActualTotalQuantity",
        ).merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID", how="left")
        accepted_po["ExcessQuantity"] = accepted_po["ActualTotalQuantity"] - accepted_po["OrderedQuantity"]
        self._compare_mask(
            accepted_po,
            accepted_po["ActualTotalQuantity"] <= accepted_po["OrderedQuantity"] + tolerance,
            "ACCEPTED_CUMULATIVE_EXCEEDS_ORDERED",
            "Total InspectionResult.AcceptedQuantity for a PurchaseOrderLineID must not exceed PurchaseOrderLine.OrderedQuantity.",
            "Track remaining PO quantity before accepting inspection results.",
            "error",
            "InspectionResult",
            "AcceptedQuantity",
            report,
        )
        self._numeric_compare(
            accepted_po,
            accepted_po["ActualTotalQuantity"],
            accepted_po["OrderedQuantity"],
            "FULL_RECEIVED_ACCEPTED_EQUALS_ORDERED",
            "For full-received Procurement v2, total InspectionResult.AcceptedQuantity must equal PurchaseOrderLine.OrderedQuantity.",
            "InspectionResult",
            "AcceptedQuantity",
            report,
            tolerance=tolerance,
        )

        inventory_txn = data["InventoryTransaction"].merge(
            data["InventoryReceiptDetail"][["InspectionResultID", "AcceptedQuantity"]],
            on="InspectionResultID",
            how="left",
        )
        self._numeric_compare(
            inventory_txn,
            inventory_txn["TransactionQuantity"],
            inventory_txn["AcceptedQuantity"],
            "INVENTORY_TRANSACTION_ACCEPTED_MISMATCH",
            "InventoryTransaction.TransactionQuantity must equal InventoryReceiptDetail.AcceptedQuantity.",
            "InventoryTransaction",
            "TransactionQuantity",
            report,
            tolerance=tolerance,
        )

        stock_in_po = self._v2_group_sum(
            data["InventoryTransaction"],
            ["PurchaseOrderLineID"],
            "TransactionQuantity",
            "ActualTotalQuantity",
        ).merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "ComponentID", "OrderedQuantity"]], on="PurchaseOrderLineID", how="left")
        stock_in_po["ExcessQuantity"] = stock_in_po["ActualTotalQuantity"] - stock_in_po["OrderedQuantity"]
        self._compare_mask(
            stock_in_po,
            stock_in_po["ActualTotalQuantity"] <= stock_in_po["OrderedQuantity"] + tolerance,
            "INVENTORY_TRANSACTION_CUMULATIVE_EXCEEDS_ORDERED",
            "Total InventoryTransaction.TransactionQuantity for a PurchaseOrderLineID must not exceed PurchaseOrderLine.OrderedQuantity.",
            "Generate downstream inventory quantities from accepted inspection quantity and enforce remaining PO quantity.",
            "error",
            "InventoryTransaction",
            "TransactionQuantity",
            report,
        )
        self._numeric_compare(
            stock_in_po,
            stock_in_po["ActualTotalQuantity"],
            stock_in_po["OrderedQuantity"],
            "FULL_RECEIVED_STOCK_IN_EQUALS_ORDERED",
            "For full-received Procurement v2, total InventoryTransaction.TransactionQuantity must equal PurchaseOrderLine.OrderedQuantity.",
            "InventoryTransaction",
            "TransactionQuantity",
            report,
            tolerance=tolerance,
        )

        inventory_grouped = self._v2_group_sum(
            data["InventoryTransaction"],
            ["ComponentID", "PlantID", "WarehouseID"],
            "TransactionQuantity",
            "ExpectedOnHandQuantity",
        )
        inventory = data["Inventory"].merge(inventory_grouped, on=["ComponentID", "PlantID", "WarehouseID"], how="left")
        self._numeric_compare(
            inventory,
            inventory["OnHandQuantity"],
            inventory["ExpectedOnHandQuantity"],
            "INVENTORY_ON_HAND_RECONCILIATION",
            "Inventory.OnHandQuantity must equal SUM(InventoryTransaction.TransactionQuantity) grouped by ComponentID, PlantID, WarehouseID.",
            "Inventory",
            "OnHandQuantity",
            report,
            tolerance=tolerance,
        )

    def _v2_rfq_quotation(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        rfq = data["RFQLine"].merge(data["PurchaseReqLine"][["RequisitionLineID", "ComponentID"]], on="RequisitionLineID", how="left", suffixes=("_rfq", "_req"))
        self._compare_mask(rfq, rfq["ComponentID_rfq"] == rfq["ComponentID_req"], "V2_RFQ_COMPONENT_MATCH", "RFQLine.ComponentID must match PurchaseReqLine.ComponentID.", "Carry component from requisition line.", "error", "RFQLine", "ComponentID", report)
        quoted = data["SupplierQuotationLn"].merge(data["RFQLine"][["RFQLineID", "ComponentID"]], on="RFQLineID", how="left", suffixes=("_quote", "_rfq"))
        self._compare_mask(quoted, quoted["ComponentID_quote"] == quoted["ComponentID_rfq"], "V2_QUOTE_COMPONENT_MATCH", "SupplierQuotationLn.ComponentID must match RFQLine.ComponentID.", "Carry component from RFQ line.", "error", "SupplierQuotationLn", "ComponentID", report)
        quoted = data["SupplierQuotationLn"].merge(data["SupplierQuotation"][["QuotationID", "SupplierID"]], on="QuotationID", how="left")
        eligible = set(map(tuple, data["SupplierComponent"][["SupplierID", "ComponentID"]].to_numpy()))
        mask = quoted.apply(lambda row: (row["SupplierID"], row["ComponentID"]) in eligible, axis=1)
        self._compare_mask(quoted, mask, "V2_QUOTE_SUPPLIER_ELIGIBILITY", "SupplierQuotationLn supplier/component pair must exist in SupplierComponent.", "Quote only eligible supplier/component pairs.", "error", "SupplierQuotationLn", "ComponentID", report)
        awarded_counts = data["SupplierQuotationLn"].groupby("RFQLineID", dropna=False)["AwardedFlag"].sum()
        passed = not (awarded_counts > 1).any()
        report.record_check(passed)
        report.add_reconciliation_summary(ReconciliationSummary("V2_RFQ_SINGLE_AWARDED_QUOTE", "passed" if passed else "failed", len(awarded_counts), int((awarded_counts > 1).sum()), "At most one awarded quote per RFQLine."))
        if not passed:
            report.add_issue("warning", "V2_RFQ_SINGLE_AWARDED_QUOTE", "More than one quote line is awarded for some RFQLine rows.", "Prefer one awarded supplier per RFQ line in later generation tuning.", table_name="SupplierQuotationLn", column_name="AwardedFlag")

    def _v2_po_schedule_shipment(self, data: dict[str, pd.DataFrame], plan: LLMGenerationPlan | None, report: DataQualityReport) -> None:
        po = data["PurchaseOrderHdr"].merge(data["SupplierQuotation"][["QuotationID", "SupplierID"]], on="QuotationID", how="left", suffixes=("_po", "_quote"))
        self._compare_mask(po, po["SupplierID_po"] == po["SupplierID_quote"], "V2_PO_SUPPLIER_MATCH", "PurchaseOrderHdr.SupplierID must match SupplierQuotation.SupplierID.", "Carry supplier from quotation.", "error", "PurchaseOrderHdr", "SupplierID", report)
        awarded = data["SupplierQuotationLn"][data["SupplierQuotationLn"]["AwardedFlag"].astype(str).isin(["1", "1.0", "True"])]
        pol = data["PurchaseOrderLine"].merge(awarded[["QuotationLineID", "ComponentID", "QuotedUnitPrice"]], on="QuotationLineID", how="left", suffixes=("_po", "_quote"))
        self._compare_mask(pol, pol["QuotedUnitPrice"].notna(), "V2_PO_FROM_AWARDED_QUOTE", "PurchaseOrderLine must reference an awarded SupplierQuotationLn.", "Use awarded quote lines for PO lines.", "error", "PurchaseOrderLine", "QuotationLineID", report)
        self._compare_mask(pol, pol["ComponentID_po"] == pol["ComponentID_quote"], "V2_PO_COMPONENT_MATCH", "PurchaseOrderLine.ComponentID must match SupplierQuotationLn.ComponentID.", "Carry component from quote line.", "error", "PurchaseOrderLine", "ComponentID", report)
        self._numeric_compare(pol, pol["UnitPrice"], pol["QuotedUnitPrice"], "V2_PO_UNIT_PRICE_MATCH", "PurchaseOrderLine.UnitPrice must match SupplierQuotationLn.QuotedUnitPrice.", "PurchaseOrderLine", "UnitPrice", report, tolerance=0.01)
        self._numeric_compare(data["PurchaseOrderLine"], data["PurchaseOrderLine"]["LineAmount"], data["PurchaseOrderLine"]["OrderedQuantity"] * data["PurchaseOrderLine"]["UnitPrice"], "V2_PO_LINE_AMOUNT", "PurchaseOrderLine.LineAmount must equal OrderedQuantity * UnitPrice.", "PurchaseOrderLine", "LineAmount", report, tolerance=self._tolerance(plan, "PurchaseOrderLine", "LineAmount", 0.01))
        grouped = data["PurchaseOrderLine"].groupby("PurchaseOrderID", dropna=False)["LineAmount"].sum().reset_index(name="ExpectedTotal")
        po_total = data["PurchaseOrderHdr"].merge(grouped, on="PurchaseOrderID", how="left")
        self._numeric_compare(po_total, po_total["TotalAmount"], po_total["ExpectedTotal"].fillna(0), "V2_PO_HEADER_TOTAL", "PurchaseOrderHdr.TotalAmount must equal SUM(PurchaseOrderLine.LineAmount).", "PurchaseOrderHdr", "TotalAmount", report, tolerance=self._tolerance(plan, "PurchaseOrderHdr", "TotalAmount", 0.01))
        shipment = data["ShipmentHdr"].merge(data["PurchaseOrderHdr"][["PurchaseOrderID", "SupplierID"]], on="PurchaseOrderID", how="left", suffixes=("_ship", "_po"))
        self._compare_mask(shipment, shipment["SupplierID_ship"] == shipment["SupplierID_po"], "V2_SHIPMENT_SUPPLIER_MATCH", "ShipmentHdr.SupplierID must match PurchaseOrderHdr.SupplierID.", "Carry supplier from PO.", "error", "ShipmentHdr", "SupplierID", report)
        sl = data["ShipmentLine"].merge(data["POSchedule"][["POScheduleID", "PurchaseOrderLineID", "ScheduledQuantity"]], on="POScheduleID", how="left", suffixes=("_ship", "_schedule"))
        self._compare_mask(sl, sl["PurchaseOrderLineID_ship"] == sl["PurchaseOrderLineID_schedule"], "V2_SHIPMENT_SCHEDULE_POLINE", "ShipmentLine.POScheduleID must belong to the same PurchaseOrderLineID.", "Use schedule from same PO line.", "error", "ShipmentLine", "POScheduleID", report)
        self._compare_mask(sl, sl["ShippedQuantity"] <= sl["ScheduledQuantity"] + 0.0001, "V2_SHIPMENT_LE_SCHEDULE", "ShipmentLine.ShippedQuantity must be <= POSchedule.ScheduledQuantity.", "Cap shipped quantity by schedule.", "error", "ShipmentLine", "ShippedQuantity", report)

    def _v2_receipt_inspection_inventory(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        grl = data["GoodsReceiptLine"].merge(data["ShipmentLine"][["ShipmentLineID", "ShipmentID", "PurchaseOrderLineID", "ComponentID", "ShippedQuantity"]], on="ShipmentLineID", how="left", suffixes=("_receipt", "_ship")).merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ShipmentID"]], on="GoodsReceiptID", how="left")
        self._compare_mask(grl, grl["ShipmentID_x"] == grl["ShipmentID_y"], "V2_RECEIPT_LINE_SHIPMENT", "GoodsReceiptLine.ShipmentLineID must belong to GoodsReceiptHeader.ShipmentID.", "Use shipment lines from the receipt shipment.", "error", "GoodsReceiptLine", "ShipmentLineID", report)
        self._compare_mask(grl, grl["PurchaseOrderLineID_receipt"] == grl["PurchaseOrderLineID_ship"], "V2_RECEIPT_POLINE_MATCH", "GoodsReceiptLine.PurchaseOrderLineID must match ShipmentLine.PurchaseOrderLineID.", "Carry PO line from shipment.", "error", "GoodsReceiptLine", "PurchaseOrderLineID", report)
        self._compare_mask(grl, grl["ComponentID_receipt"] == grl["ComponentID_ship"], "V2_RECEIPT_COMPONENT_MATCH", "GoodsReceiptLine.ComponentID must match ShipmentLine.ComponentID.", "Carry component from shipment.", "error", "GoodsReceiptLine", "ComponentID", report)
        self._numeric_compare(grl, grl["ShippedQuantity_receipt"], grl["ShippedQuantity_ship"], "V2_RECEIPT_SHIPPED_MATCH", "GoodsReceiptLine.ShippedQuantity must match ShipmentLine.ShippedQuantity.", "GoodsReceiptLine", "ShippedQuantity", report)
        self._compare_mask(grl, grl["ReceivedQuantity"] <= grl["ShippedQuantity_receipt"] + 0.0001, "V2_RECEIVED_LE_SHIPPED", "ReceivedQuantity must be <= ShippedQuantity.", "Cap received quantity.", "error", "GoodsReceiptLine", "ReceivedQuantity", report)
        self._numeric_compare(grl, grl["ShortQuantity"], grl["ShippedQuantity_receipt"] - grl["ReceivedQuantity"], "V2_SHORT_QTY", "ShortQuantity must equal ShippedQuantity - ReceivedQuantity.", "GoodsReceiptLine", "ShortQuantity", report)
        self._numeric_compare(grl, grl["ShortQuantity"], 0, "FULL_RECEIVED_SHORT_QUANTITY_ZERO", "For full-received Procurement v2, GoodsReceiptLine.ShortQuantity must be zero.", "GoodsReceiptLine", "ShortQuantity", report)
        self._numeric_compare(grl, grl["DamagedQuantity"], 0, "FULL_RECEIVED_DAMAGED_QUANTITY_ZERO", "For full-received Procurement v2, GoodsReceiptLine.DamagedQuantity must be zero.", "GoodsReceiptLine", "DamagedQuantity", report)
        insp = data["InspectionResult"].merge(data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID", "InspectionDate"]], on="InspectionID", how="left").merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "ReceivedQuantity", "ComponentID", "GoodsReceiptID"]], on="GoodsReceiptLineID", how="left")
        self._compare_mask(insp, insp["InspectedQuantity"] <= insp["ReceivedQuantity"] + 0.0001, "V2_INSPECTED_LE_RECEIVED", "InspectionResult.InspectedQuantity must be <= GoodsReceiptLine.ReceivedQuantity.", "Base inspected quantity on receipt.", "error", "InspectionResult", "InspectedQuantity", report)
        self._numeric_compare(insp, insp["AcceptedQuantity"] + insp["RejectedQuantity"], insp["InspectedQuantity"], "V2_INSPECTION_QTY_TOTAL", "AcceptedQuantity + RejectedQuantity must equal InspectedQuantity.", "InspectionResult", None, report)
        self._numeric_compare(insp, insp["RejectedQuantity"], insp["InspectedQuantity"] - insp["AcceptedQuantity"], "V2_REJECTED_QTY", "RejectedQuantity must equal InspectedQuantity - AcceptedQuantity.", "InspectionResult", "RejectedQuantity", report)
        expected_rate = (insp["RejectedQuantity"] / insp["InspectedQuantity"].replace({0: np.nan}) * 100).round(2)
        self._compare_mask(insp, (insp["InspectedQuantity"].eq(0) | ((insp["RejectionRatePct"] - expected_rate).abs() <= 0.01)).fillna(True), "V2_REJECTION_RATE", "RejectionRatePct must equal RejectedQuantity / InspectedQuantity * 100.", "Use guarded percentage formula.", "error", "InspectionResult", "RejectionRatePct", report)
        inspection_lineage = data["InspectionResult"][["InspectionResultID", "InspectionID", "AcceptedQuantity"]].merge(
            data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID", "InspectionDate"]],
            on="InspectionID",
            how="left",
        ).rename(
            columns={
                "GoodsReceiptLineID": "ExpectedGoodsReceiptLineID",
                "AcceptedQuantity": "ExpectedAcceptedQuantity",
            }
        )
        receipt_lineage = data["GoodsReceiptLine"][["GoodsReceiptLineID", "GoodsReceiptID", "PurchaseOrderLineID", "ComponentID"]].rename(
            columns={
                "PurchaseOrderLineID": "ExpectedReceiptPurchaseOrderLineID",
                "ComponentID": "ExpectedReceiptComponentID",
            }
        )
        po_lineage = data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "ComponentID", "UnitPrice"]].merge(
            data["PurchaseOrderHdr"][["PurchaseOrderID", "SupplierID"]],
            on="PurchaseOrderID",
            how="left",
        ).rename(
            columns={
                "ComponentID": "ExpectedPoComponentID",
                "SupplierID": "ExpectedSupplierID",
                "UnitPrice": "ExpectedUnitPrice",
            }
        )
        receipt_location = data["GoodsReceiptHeader"][["GoodsReceiptID", "PlantID", "WarehouseID"]].rename(
            columns={"PlantID": "ExpectedPlantID", "WarehouseID": "ExpectedWarehouseID"}
        )
        receipt_detail_lineage = data["InventoryReceiptDetail"][
            [
                "InspectionResultID",
                "GoodsReceiptLineID",
                "PurchaseOrderLineID",
                "SupplierID",
                "ComponentID",
                "PlantID",
                "WarehouseID",
                "StockPostedDate",
                "AcceptedQuantity",
                "DeliveredUnitPrice",
            ]
        ].rename(
            columns={
                "GoodsReceiptLineID": "DetailGoodsReceiptLineID",
                "PurchaseOrderLineID": "DetailPurchaseOrderLineID",
                "SupplierID": "DetailSupplierID",
                "ComponentID": "DetailComponentID",
                "PlantID": "DetailPlantID",
                "WarehouseID": "DetailWarehouseID",
                "StockPostedDate": "DetailStockPostedDate",
                "AcceptedQuantity": "DetailAcceptedQuantity",
                "DeliveredUnitPrice": "DetailDeliveredUnitPrice",
            }
        )
        inv = (
            data["InventoryTransaction"]
            .merge(inspection_lineage, on="InspectionResultID", how="left")
            .merge(receipt_lineage, on="GoodsReceiptLineID", how="left")
            .merge(po_lineage, on="PurchaseOrderLineID", how="left")
            .merge(receipt_location, on="GoodsReceiptID", how="left")
            .merge(receipt_detail_lineage, on="InspectionResultID", how="left")
        )
        for column_name in ["GoodsReceiptLineID", "PurchaseOrderLineID", "SupplierID", "UnitPrice", "InventoryValue", "InventoryStatus"]:
            self._compare_mask(
                inv,
                inv[column_name].notna(),
                f"V2_INVENTORY_TRANSACTION_{column_name.upper()}_REQUIRED",
                f"InventoryTransaction.{column_name} must be populated for StockIn traceability.",
                "Generate InventoryTransaction rows from accepted inspection, receipt, and PO lineage.",
                "error",
                "InventoryTransaction",
                column_name,
                report,
            )
        self._compare_mask(inv, inv["TransactionType"].astype(str).eq("StockIn"), "V2_INVENTORY_TRANSACTION_STOCK_IN", "InventoryTransaction.TransactionType must be StockIn for Procurement v2 inbound receipts.", "Use StockIn for accepted supplier goods posted into inventory.", "error", "InventoryTransaction", "TransactionType", report)
        self._compare_mask(inv, inv["InventoryStatus"].astype(str).isin(["Posted", "QualityAccepted", "ReceivedToInventory"]), "V2_INVENTORY_TRANSACTION_STATUS_ALLOWED", "InventoryTransaction.InventoryStatus must be a valid stock-in posting status.", "Use Posted, QualityAccepted, or ReceivedToInventory for accepted inventory postings.", "error", "InventoryTransaction", "InventoryStatus", report)
        self._compare_mask(inv, inv["DetailGoodsReceiptLineID"].notna(), "V2_INVENTORY_TRANSACTION_RECEIPT_DETAIL_MATCH", "Every InventoryTransaction row must map to one InventoryReceiptDetail row by InspectionResultID.", "Generate InventoryTransaction rows from InventoryReceiptDetail.", "error", "InventoryTransaction", "InspectionResultID", report)
        self._compare_mask(inv, inv["GoodsReceiptLineID"] == inv["DetailGoodsReceiptLineID"], "V2_INVENTORY_GOODS_RECEIPT_LINE_LINEAGE", "InventoryTransaction.GoodsReceiptLineID must match InventoryReceiptDetail.GoodsReceiptLineID.", "Carry GoodsReceiptLineID from InventoryReceiptDetail.", "error", "InventoryTransaction", "GoodsReceiptLineID", report)
        self._compare_mask(inv, inv["PurchaseOrderLineID"] == inv["DetailPurchaseOrderLineID"], "V2_INVENTORY_PO_LINE_RECEIPT_LINEAGE", "InventoryTransaction.PurchaseOrderLineID must match InventoryReceiptDetail.PurchaseOrderLineID.", "Carry PurchaseOrderLineID from InventoryReceiptDetail.", "error", "InventoryTransaction", "PurchaseOrderLineID", report)
        self._compare_mask(inv, inv["ComponentID"] == inv["DetailComponentID"], "V2_INVENTORY_COMPONENT_RECEIPT_MATCH", "InventoryTransaction.ComponentID must match InventoryReceiptDetail.ComponentID.", "Carry ComponentID from InventoryReceiptDetail.", "error", "InventoryTransaction", "ComponentID", report)
        self._compare_mask(inv, inv["ComponentID"] == inv["ExpectedPoComponentID"], "V2_INVENTORY_COMPONENT_PO_MATCH", "InventoryTransaction.ComponentID must still match PurchaseOrderLine.ComponentID through InventoryReceiptDetail lineage.", "Carry ComponentID from InventoryReceiptDetail.", "error", "InventoryTransaction", "ComponentID", report)
        self._compare_mask(inv, inv["SupplierID"] == inv["DetailSupplierID"], "V2_INVENTORY_SUPPLIER_LINEAGE", "InventoryTransaction.SupplierID must match InventoryReceiptDetail.SupplierID.", "Derive SupplierID from InventoryReceiptDetail.", "error", "InventoryTransaction", "SupplierID", report)
        self._compare_mask(inv, (inv["PlantID"] == inv["DetailPlantID"]) & (inv["WarehouseID"] == inv["DetailWarehouseID"]), "V2_INVENTORY_LOCATION_LINEAGE", "InventoryTransaction PlantID/WarehouseID must match InventoryReceiptDetail location.", "Carry location from InventoryReceiptDetail.", "error", "InventoryTransaction", None, report)
        self._compare_mask(inv, pd.to_datetime(inv["TransactionDate"], errors="coerce").dt.normalize().eq(pd.to_datetime(inv["DetailStockPostedDate"], errors="coerce").dt.normalize()), "V2_INVENTORY_TRANSACTION_AFTER_INSPECTION", "InventoryTransaction.TransactionDate must equal InventoryReceiptDetail.StockPostedDate.", "Post inventory using the receipt detail stock posted date.", "error", "InventoryTransaction", "TransactionDate", report)
        self._numeric_compare(inv, inv["TransactionQuantity"], inv["DetailAcceptedQuantity"], "V2_INVENTORY_ACCEPTED_QTY", "InventoryTransaction.TransactionQuantity must equal InventoryReceiptDetail.AcceptedQuantity.", "InventoryTransaction", "TransactionQuantity", report)
        self._numeric_compare(inv, inv["UnitPrice"], inv["DetailDeliveredUnitPrice"], "V2_INVENTORY_UNIT_PRICE_MATCH", "InventoryTransaction.UnitPrice must equal InventoryReceiptDetail.DeliveredUnitPrice.", "InventoryTransaction", "UnitPrice", report, tolerance=0.01)
        self._numeric_compare(inv, inv["InventoryValue"], (pd.to_numeric(inv["TransactionQuantity"], errors="coerce") * pd.to_numeric(inv["UnitPrice"], errors="coerce")).round(2), "V2_INVENTORY_TRANSACTION_VALUE", "InventoryTransaction.InventoryValue must equal TransactionQuantity * UnitPrice.", "InventoryTransaction", "InventoryValue", report, tolerance=0.0100001)
        self._compare_mask(inv, pd.to_numeric(inv["TransactionQuantity"], errors="coerce") >= -0.0001, "V2_INVENTORY_TRANSACTION_QTY_NON_NEGATIVE", "InventoryTransaction.TransactionQuantity must be non-negative.", "Post only accepted non-negative quantities.", "error", "InventoryTransaction", "TransactionQuantity", report)
        self._compare_mask(inv, pd.to_numeric(inv["InventoryValue"], errors="coerce") >= -0.01, "V2_INVENTORY_TRANSACTION_VALUE_NON_NEGATIVE", "InventoryTransaction.InventoryValue must be non-negative.", "Calculate stock-in value from non-negative quantity and unit price.", "error", "InventoryTransaction", "InventoryValue", report)

    def _v2_inventory_receipt_detail(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        detail = data["InventoryReceiptDetail"].copy()
        if detail.empty:
            report.record_check(False)
            report.add_issue("error", "V2_INVENTORY_RECEIPT_DETAIL_EXISTS", "InventoryReceiptDetail must contain receipt traceability rows.", "Generate one InventoryReceiptDetail row per InspectionResult.", table_name="InventoryReceiptDetail")
            return

        required_columns = [
            "InventoryReceiptDetailID", "InspectionResultID", "GoodsReceiptLineID", "PurchaseOrderLineID", "PurchaseOrderID",
            "SupplierID", "ComponentID", "PlantID", "WarehouseID", "POOrderDate", "ExpectedDeliveryDate", "ActualDeliveryDate",
            "StockPostedDate", "OrderedQuantity", "ShippedQuantity", "ReceivedQuantity", "InspectedQuantity", "AcceptedQuantity",
            "RejectedQuantity", "OrderedUnitPrice", "DeliveredUnitPrice", "PriceDifference", "PriceDifferencePct", "OrderedValue",
            "DeliveredValue", "AcceptedStockValue", "OrderYear", "DeliveryYear", "CrossYearDeliveryFlag", "DeliveryDelayDays",
            "DeliveryStatus", "PriceVarianceStatus", "InventoryReceiptStatus",
        ]
        for column_name in required_columns:
            mask = detail[column_name].notna() if column_name in detail.columns else pd.Series(False, index=detail.index)
            self._compare_mask(detail, mask, f"V2_INVENTORY_RECEIPT_DETAIL_{column_name.upper()}_REQUIRED", f"InventoryReceiptDetail.{column_name} must be populated.", "Generate InventoryReceiptDetail from inspection, receipt, PO, supplier, and location lineage.", "error", "InventoryReceiptDetail", column_name, report)

        pk_mask = detail["InventoryReceiptDetailID"].notna() & ~detail["InventoryReceiptDetailID"].duplicated(keep=False)
        self._compare_mask(detail, pk_mask, "V2_INVENTORY_RECEIPT_DETAIL_PK_UNIQUE", "InventoryReceiptDetailID must be unique and non-null.", "Generate sequential unique receipt detail IDs.", "error", "InventoryReceiptDetail", "InventoryReceiptDetailID", report)

        result_expected = data["InspectionResult"][["InspectionResultID", "InspectionID", "InspectedQuantity", "AcceptedQuantity", "RejectedQuantity"]].rename(columns={"InspectedQuantity": "ExpectedInspectedQuantity", "AcceptedQuantity": "ExpectedAcceptedQuantity", "RejectedQuantity": "ExpectedRejectedQuantity"})
        inspection_expected = data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID", "InspectionDate"]].rename(columns={"GoodsReceiptLineID": "ExpectedInspectionGoodsReceiptLineID", "InspectionDate": "ExpectedInspectionDate"})
        receipt_line_expected = data["GoodsReceiptLine"][["GoodsReceiptLineID", "GoodsReceiptID", "ShipmentLineID", "PurchaseOrderLineID", "ComponentID", "ShippedQuantity", "ReceivedQuantity"]].rename(columns={"GoodsReceiptID": "ExpectedGoodsReceiptID", "ShipmentLineID": "ExpectedShipmentLineID", "PurchaseOrderLineID": "ExpectedReceiptPurchaseOrderLineID", "ComponentID": "ExpectedReceiptComponentID", "ShippedQuantity": "ExpectedReceiptShippedQuantity", "ReceivedQuantity": "ExpectedReceivedQuantity"})
        receipt_expected = data["GoodsReceiptHeader"][["GoodsReceiptID", "PlantID", "WarehouseID", "ReceiptDate"]].rename(columns={"PlantID": "ExpectedPlantID", "WarehouseID": "ExpectedWarehouseID", "ReceiptDate": "ExpectedActualDeliveryDate"})
        shipment_line_expected = data["ShipmentLine"][["ShipmentLineID", "POScheduleID", "ShippedQuantity"]].rename(columns={"POScheduleID": "ExpectedPOScheduleID", "ShippedQuantity": "ExpectedShippedQuantity"})
        schedule_expected = data["POSchedule"][["POScheduleID", "ScheduledDeliveryDate"]].rename(columns={"ScheduledDeliveryDate": "ExpectedScheduledDeliveryDate"})
        po_line_expected = data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "ComponentID", "OrderedQuantity", "UnitPrice"]].rename(columns={"PurchaseOrderID": "ExpectedPurchaseOrderID", "ComponentID": "ExpectedPoComponentID", "OrderedQuantity": "ExpectedOrderedQuantity", "UnitPrice": "ExpectedOrderedUnitPrice"})
        po_expected = data["PurchaseOrderHdr"][["PurchaseOrderID", "SupplierID", "OrderDate"]].rename(columns={"SupplierID": "ExpectedSupplierID", "OrderDate": "ExpectedPOOrderDate"})
        warehouse_expected = data["Warehouse"][["WarehouseID", "PlantID"]].rename(columns={"PlantID": "ExpectedWarehousePlantID"})

        merged = (
            detail.merge(result_expected, on="InspectionResultID", how="left")
            .merge(inspection_expected, on="InspectionID", how="left")
            .merge(receipt_line_expected, on="GoodsReceiptLineID", how="left")
            .merge(receipt_expected, left_on="ExpectedGoodsReceiptID", right_on="GoodsReceiptID", how="left")
            .merge(shipment_line_expected, left_on="ExpectedShipmentLineID", right_on="ShipmentLineID", how="left")
            .merge(schedule_expected, left_on="ExpectedPOScheduleID", right_on="POScheduleID", how="left")
            .merge(po_line_expected, on="PurchaseOrderLineID", how="left")
            .merge(po_expected, on="PurchaseOrderID", how="left")
            .merge(warehouse_expected, on="WarehouseID", how="left")
        )

        self._compare_mask(merged, merged["ExpectedInspectedQuantity"].notna(), "V2_INVENTORY_RECEIPT_DETAIL_INSPECTION_RESULT_FK", "InventoryReceiptDetail.InspectionResultID must exist in InspectionResult.", "Use valid inspection result IDs.", "error", "InventoryReceiptDetail", "InspectionResultID", report)
        self._compare_mask(merged, merged["ExpectedReceivedQuantity"].notna(), "V2_INVENTORY_RECEIPT_DETAIL_GOODS_RECEIPT_LINE_FK", "InventoryReceiptDetail.GoodsReceiptLineID must exist in GoodsReceiptLine.", "Use valid goods receipt line IDs.", "error", "InventoryReceiptDetail", "GoodsReceiptLineID", report)
        self._compare_mask(merged, merged["ExpectedOrderedQuantity"].notna(), "V2_INVENTORY_RECEIPT_DETAIL_PO_LINE_FK", "InventoryReceiptDetail.PurchaseOrderLineID must exist in PurchaseOrderLine.", "Use valid purchase order line IDs.", "error", "InventoryReceiptDetail", "PurchaseOrderLineID", report)
        self._compare_mask(merged, merged["ExpectedSupplierID"].notna(), "V2_INVENTORY_RECEIPT_DETAIL_PO_FK", "InventoryReceiptDetail.PurchaseOrderID must exist in PurchaseOrderHdr.", "Use valid purchase order IDs.", "error", "InventoryReceiptDetail", "PurchaseOrderID", report)
        self._compare_mask(merged, merged["GoodsReceiptLineID"].eq(merged["ExpectedInspectionGoodsReceiptLineID"]), "V2_INVENTORY_RECEIPT_DETAIL_INSPECTION_LINEAGE", "InventoryReceiptDetail.GoodsReceiptLineID must match IncomingInspection.GoodsReceiptLineID.", "Carry receipt-line lineage from IncomingInspection.", "error", "InventoryReceiptDetail", "GoodsReceiptLineID", report)
        self._compare_mask(merged, merged["PurchaseOrderLineID"].eq(merged["ExpectedReceiptPurchaseOrderLineID"]), "V2_INVENTORY_RECEIPT_DETAIL_PO_LINEAGE", "InventoryReceiptDetail.PurchaseOrderLineID must match GoodsReceiptLine.PurchaseOrderLineID.", "Carry PO line from GoodsReceiptLine.", "error", "InventoryReceiptDetail", "PurchaseOrderLineID", report)
        self._compare_mask(merged, merged["PurchaseOrderID"].eq(merged["ExpectedPurchaseOrderID"]), "V2_INVENTORY_RECEIPT_DETAIL_PO_HEADER_LINEAGE", "InventoryReceiptDetail.PurchaseOrderID must match PurchaseOrderLine.PurchaseOrderID.", "Carry PO header from PurchaseOrderLine.", "error", "InventoryReceiptDetail", "PurchaseOrderID", report)
        self._compare_mask(merged, merged["SupplierID"].eq(merged["ExpectedSupplierID"]), "V2_INVENTORY_RECEIPT_DETAIL_SUPPLIER_LINEAGE", "InventoryReceiptDetail.SupplierID must match PurchaseOrderHdr.SupplierID.", "Carry supplier from PurchaseOrderHdr.", "error", "InventoryReceiptDetail", "SupplierID", report)
        self._compare_mask(merged, merged["ComponentID"].eq(merged["ExpectedPoComponentID"]) & merged["ComponentID"].eq(merged["ExpectedReceiptComponentID"]), "V2_INVENTORY_RECEIPT_DETAIL_COMPONENT_LINEAGE", "InventoryReceiptDetail.ComponentID must match PO and receipt component lineage.", "Carry component from PO and receipt lines.", "error", "InventoryReceiptDetail", "ComponentID", report)
        self._compare_mask(merged, merged["PlantID"].eq(merged["ExpectedPlantID"]) & merged["WarehouseID"].eq(merged["ExpectedWarehouseID"]) & merged["PlantID"].eq(merged["ExpectedWarehousePlantID"]), "V2_INVENTORY_RECEIPT_DETAIL_LOCATION_LINEAGE", "InventoryReceiptDetail PlantID/WarehouseID must match GoodsReceiptHeader and warehouse master lineage.", "Carry plant and warehouse from GoodsReceiptHeader.", "error", "InventoryReceiptDetail", "WarehouseID", report)

        self._compare_mask(merged, pd.to_datetime(merged["POOrderDate"], errors="coerce").dt.normalize().eq(pd.to_datetime(merged["ExpectedPOOrderDate"], errors="coerce").dt.normalize()), "V2_INVENTORY_RECEIPT_DETAIL_PO_ORDER_DATE", "InventoryReceiptDetail.POOrderDate must match PurchaseOrderHdr.OrderDate.", "Carry PO order date from the PO header.", "error", "InventoryReceiptDetail", "POOrderDate", report)
        self._compare_mask(merged, pd.to_datetime(merged["ExpectedDeliveryDate"], errors="coerce").dt.normalize().eq(pd.to_datetime(merged["ExpectedScheduledDeliveryDate"], errors="coerce").dt.normalize()), "V2_INVENTORY_RECEIPT_DETAIL_EXPECTED_DELIVERY_DATE", "InventoryReceiptDetail.ExpectedDeliveryDate must match POSchedule.ScheduledDeliveryDate.", "Carry expected delivery date from POSchedule.", "error", "InventoryReceiptDetail", "ExpectedDeliveryDate", report)
        self._compare_mask(merged, pd.to_datetime(merged["ActualDeliveryDate"], errors="coerce").dt.normalize().eq(pd.to_datetime(merged["ExpectedActualDeliveryDate"], errors="coerce").dt.normalize()), "V2_INVENTORY_RECEIPT_DETAIL_ACTUAL_DELIVERY_DATE", "InventoryReceiptDetail.ActualDeliveryDate must match GoodsReceiptHeader.ReceiptDate.", "Carry actual delivery date from GoodsReceiptHeader.", "error", "InventoryReceiptDetail", "ActualDeliveryDate", report)
        self._compare_mask(merged, pd.to_datetime(merged["StockPostedDate"], errors="coerce") >= pd.to_datetime(merged["ActualDeliveryDate"], errors="coerce"), "V2_INVENTORY_RECEIPT_DETAIL_STOCK_POSTED_DATE", "InventoryReceiptDetail.StockPostedDate must be on or after ActualDeliveryDate.", "Post stock on or after goods receipt.", "error", "InventoryReceiptDetail", "StockPostedDate", report)
        for column_name in ["POOrderDate", "ExpectedDeliveryDate", "ActualDeliveryDate", "StockPostedDate"]:
            dates = pd.to_datetime(merged[column_name], errors="coerce")
            self._compare_mask(merged, (dates >= pd.Timestamp("2025-01-01")) & (dates <= pd.Timestamp("2025-12-31")), f"V2_INVENTORY_RECEIPT_DETAIL_{column_name.upper()}_2025", f"InventoryReceiptDetail.{column_name} must be within calendar year 2025.", "Keep Procurement v2 generated dates in 2025.", "error", "InventoryReceiptDetail", column_name, report)

        self._numeric_compare(merged, merged["OrderedQuantity"], merged["ExpectedOrderedQuantity"], "V2_INVENTORY_RECEIPT_DETAIL_ORDERED_QTY", "InventoryReceiptDetail.OrderedQuantity must match PurchaseOrderLine.OrderedQuantity.", "InventoryReceiptDetail", "OrderedQuantity", report)
        self._numeric_compare(merged, merged["ShippedQuantity"], merged["ExpectedShippedQuantity"], "V2_INVENTORY_RECEIPT_DETAIL_SHIPPED_QTY", "InventoryReceiptDetail.ShippedQuantity must match ShipmentLine.ShippedQuantity.", "InventoryReceiptDetail", "ShippedQuantity", report)
        self._numeric_compare(merged, merged["ReceivedQuantity"], merged["ExpectedReceivedQuantity"], "V2_INVENTORY_RECEIPT_DETAIL_RECEIVED_QTY", "InventoryReceiptDetail.ReceivedQuantity must match GoodsReceiptLine.ReceivedQuantity.", "InventoryReceiptDetail", "ReceivedQuantity", report)
        self._numeric_compare(merged, merged["InspectedQuantity"], merged["ExpectedInspectedQuantity"], "V2_INVENTORY_RECEIPT_DETAIL_INSPECTED_QTY", "InventoryReceiptDetail.InspectedQuantity must match InspectionResult.InspectedQuantity.", "InventoryReceiptDetail", "InspectedQuantity", report)
        self._numeric_compare(merged, merged["AcceptedQuantity"], merged["ExpectedAcceptedQuantity"], "V2_INVENTORY_RECEIPT_DETAIL_ACCEPTED_QTY", "InventoryReceiptDetail.AcceptedQuantity must match InspectionResult.AcceptedQuantity.", "InventoryReceiptDetail", "AcceptedQuantity", report)
        self._numeric_compare(merged, merged["RejectedQuantity"], 0, "V2_INVENTORY_RECEIPT_DETAIL_REJECTED_QTY_ZERO", "InventoryReceiptDetail.RejectedQuantity must be zero for full-received Procurement v2.", "InventoryReceiptDetail", "RejectedQuantity", report)
        for column_name in ["ShippedQuantity", "ReceivedQuantity", "InspectedQuantity", "AcceptedQuantity"]:
            self._numeric_compare(merged, merged[column_name], merged["OrderedQuantity"], f"V2_INVENTORY_RECEIPT_DETAIL_FULL_RECEIVED_{column_name.upper()}", f"InventoryReceiptDetail.{column_name} must equal OrderedQuantity for full-received Procurement v2.", "InventoryReceiptDetail", column_name, report)

        self._numeric_compare(merged, merged["OrderedUnitPrice"], merged["ExpectedOrderedUnitPrice"], "V2_INVENTORY_RECEIPT_DETAIL_ORDERED_UNIT_PRICE", "InventoryReceiptDetail.OrderedUnitPrice must match PurchaseOrderLine.UnitPrice.", "InventoryReceiptDetail", "OrderedUnitPrice", report, tolerance=0.01)
        self._numeric_compare(merged, merged["PriceDifference"], pd.to_numeric(merged["DeliveredUnitPrice"], errors="coerce") - pd.to_numeric(merged["OrderedUnitPrice"], errors="coerce"), "V2_INVENTORY_RECEIPT_DETAIL_PRICE_DIFFERENCE", "InventoryReceiptDetail.PriceDifference must equal DeliveredUnitPrice - OrderedUnitPrice.", "InventoryReceiptDetail", "PriceDifference", report, tolerance=0.01)
        expected_pct = merged.apply(self._inventory_receipt_price_difference_pct, axis=1)
        self._numeric_compare(merged, merged["PriceDifferencePct"], expected_pct, "V2_INVENTORY_RECEIPT_DETAIL_PRICE_DIFFERENCE_PCT", "InventoryReceiptDetail.PriceDifferencePct must equal price difference percentage.", "InventoryReceiptDetail", "PriceDifferencePct", report, tolerance=0.01)
        self._numeric_compare(merged, merged["OrderedValue"], (pd.to_numeric(merged["OrderedQuantity"], errors="coerce") * pd.to_numeric(merged["OrderedUnitPrice"], errors="coerce")).round(2), "V2_INVENTORY_RECEIPT_DETAIL_ORDERED_VALUE", "InventoryReceiptDetail.OrderedValue must equal OrderedQuantity * OrderedUnitPrice.", "InventoryReceiptDetail", "OrderedValue", report, tolerance=0.0100001)
        self._numeric_compare(merged, merged["DeliveredValue"], (pd.to_numeric(merged["ReceivedQuantity"], errors="coerce") * pd.to_numeric(merged["DeliveredUnitPrice"], errors="coerce")).round(2), "V2_INVENTORY_RECEIPT_DETAIL_DELIVERED_VALUE", "InventoryReceiptDetail.DeliveredValue must equal ReceivedQuantity * DeliveredUnitPrice.", "InventoryReceiptDetail", "DeliveredValue", report, tolerance=0.0100001)
        self._numeric_compare(merged, merged["AcceptedStockValue"], (pd.to_numeric(merged["AcceptedQuantity"], errors="coerce") * pd.to_numeric(merged["DeliveredUnitPrice"], errors="coerce")).round(2), "V2_INVENTORY_RECEIPT_DETAIL_ACCEPTED_STOCK_VALUE", "InventoryReceiptDetail.AcceptedStockValue must equal AcceptedQuantity * DeliveredUnitPrice.", "InventoryReceiptDetail", "AcceptedStockValue", report, tolerance=0.0100001)

        self._compare_mask(merged, pd.to_numeric(merged["OrderYear"], errors="coerce").eq(2025) & pd.to_numeric(merged["DeliveryYear"], errors="coerce").eq(2025), "V2_INVENTORY_RECEIPT_DETAIL_YEAR_FIELDS", "InventoryReceiptDetail OrderYear and DeliveryYear must be 2025.", "Keep Phase 3 generation in the 2025-only scope.", "error", "InventoryReceiptDetail", "OrderYear", report)
        self._numeric_compare(merged, merged["CrossYearDeliveryFlag"], 0, "V2_INVENTORY_RECEIPT_DETAIL_CROSS_YEAR_FLAG", "InventoryReceiptDetail.CrossYearDeliveryFlag must be 0 for 2025-only generation.", "InventoryReceiptDetail", "CrossYearDeliveryFlag", report)
        expected_delay = (pd.to_datetime(merged["ActualDeliveryDate"], errors="coerce") - pd.to_datetime(merged["ExpectedDeliveryDate"], errors="coerce")).dt.days
        self._numeric_compare(merged, merged["DeliveryDelayDays"], expected_delay, "V2_INVENTORY_RECEIPT_DETAIL_DELIVERY_DELAY_DAYS", "InventoryReceiptDetail.DeliveryDelayDays must equal ActualDeliveryDate - ExpectedDeliveryDate.", "InventoryReceiptDetail", "DeliveryDelayDays", report)
        expected_delivery_status = np.select([expected_delay < 0, expected_delay > 0], ["Early", "Delayed"], default="OnTime")
        self._compare_mask(merged, merged["DeliveryStatus"].astype(str).eq(pd.Series(expected_delivery_status, index=merged.index)), "V2_INVENTORY_RECEIPT_DETAIL_DELIVERY_STATUS", "InventoryReceiptDetail.DeliveryStatus must match expected versus actual delivery date.", "Derive DeliveryStatus from delivery delay days.", "error", "InventoryReceiptDetail", "DeliveryStatus", report)
        price_difference = pd.to_numeric(merged["PriceDifference"], errors="coerce").fillna(0)
        expected_price_status = np.select([price_difference > 0.01, price_difference < -0.01], ["PriceIncrease", "PriceDecrease"], default="NoChange")
        self._compare_mask(merged, merged["PriceVarianceStatus"].astype(str).eq(pd.Series(expected_price_status, index=merged.index)), "V2_INVENTORY_RECEIPT_DETAIL_PRICE_VARIANCE_STATUS", "InventoryReceiptDetail.PriceVarianceStatus must match PriceDifference.", "Derive price variance status from price difference.", "error", "InventoryReceiptDetail", "PriceVarianceStatus", report)
        self._compare_mask(merged, merged["InventoryReceiptStatus"].astype(str).eq("Received"), "V2_INVENTORY_RECEIPT_DETAIL_STATUS", "InventoryReceiptDetail.InventoryReceiptStatus must be Received.", "Use Received for full-received inventory receipt details.", "error", "InventoryReceiptDetail", "InventoryReceiptStatus", report)

    def _inventory_receipt_price_difference_pct(self, row: pd.Series) -> float:
        try:
            ordered_unit_price = Decimal(str(row["OrderedUnitPrice"]))
            if ordered_unit_price == 0:
                return 0.0
            price_difference = Decimal(str(row["PriceDifference"]))
            percentage = (price_difference / ordered_unit_price) * Decimal("100")
            return float(percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))
        except Exception:
            return float("nan")

    def _v2_inventory_snapshot(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        inventory = data["Inventory"]
        transactions = data["InventoryTransaction"]
        keys = ["ComponentID", "PlantID", "WarehouseID"]
        if not set(keys).issubset(inventory.columns) or not set(keys + ["TransactionQuantity", "TransactionDate", "InventoryValue"]).issubset(transactions.columns):
            report.record_check(False)
            report.add_issue("error", "V2_INVENTORY_REQUIRED_COLUMNS", "Inventory reconciliation requires component, plant, warehouse, quantity, value, and transaction date columns.", "Generate Inventory from InventoryTransaction grouped by ComponentID, PlantID, and WarehouseID.", table_name="Inventory")
            return

        grouped = (
            transactions.groupby(keys, dropna=False)
            .agg(
                ExpectedOnHandQuantity=("TransactionQuantity", "sum"),
                ExpectedOnHandValue=("InventoryValue", "sum"),
                ExpectedLastTransactionDate=("TransactionDate", "max"),
            )
            .reset_index()
        )
        report.add_reconciliation_summary(
            ReconciliationSummary(
                "V2_INVENTORY_GROUP_ROW_COUNT",
                "passed" if len(inventory) == len(grouped) else "failed",
                len(inventory),
                abs(len(inventory) - len(grouped)),
                "Inventory row count should equal distinct InventoryTransaction ComponentID/PlantID/WarehouseID groups.",
            )
        )
        report.record_check(len(inventory) == len(grouped))
        if len(inventory) != len(grouped):
            report.add_issue(
                "error",
                "V2_INVENTORY_GROUP_ROW_COUNT",
                "Inventory row count must equal the number of distinct InventoryTransaction component/plant/warehouse groups.",
                "Build Inventory only from grouped InventoryTransaction rows.",
                table_name="Inventory",
            )

        duplicate_mask = inventory.duplicated(subset=keys, keep=False)
        self._compare_mask(
            inventory,
            ~duplicate_mask,
            "V2_INVENTORY_UNIQUE_STOCK_KEY",
            "Inventory must have at most one row per ComponentID, PlantID, and WarehouseID.",
            "Aggregate InventoryTransaction rows once per component/plant/warehouse stock position.",
            "error",
            "Inventory",
            None,
            report,
        )

        merged = inventory.merge(grouped, on=keys, how="left")
        self._numeric_compare(
            merged,
            merged["OnHandQuantity"],
            merged["ExpectedOnHandQuantity"],
            "V2_INVENTORY_ON_HAND_RECONCILIATION",
            "Inventory.OnHandQuantity must equal SUM(InventoryTransaction.TransactionQuantity) grouped by ComponentID, PlantID, and WarehouseID.",
            "Inventory",
            "OnHandQuantity",
            report,
            tolerance=0.0001,
        )
        self._numeric_compare(
            merged,
            merged["AvailableQuantity"],
            pd.to_numeric(merged["OnHandQuantity"], errors="coerce") - pd.to_numeric(merged["ReservedQuantity"], errors="coerce"),
            "V2_INVENTORY_AVAILABLE_RECONCILIATION",
            "Inventory.AvailableQuantity must equal OnHandQuantity - ReservedQuantity.",
            "Inventory",
            "AvailableQuantity",
            report,
            tolerance=0.0001,
        )
        self._numeric_compare(
            merged,
            merged["OnHandValue"],
            merged["ExpectedOnHandValue"],
            "V2_INVENTORY_ON_HAND_VALUE_RECONCILIATION",
            "Inventory.OnHandValue must equal SUM(InventoryTransaction.InventoryValue) grouped by ComponentID, PlantID, and WarehouseID.",
            "Inventory",
            "OnHandValue",
            report,
            tolerance=0.01,
        )
        on_hand = pd.to_numeric(merged["OnHandQuantity"], errors="coerce")
        reserved = pd.to_numeric(merged["ReservedQuantity"], errors="coerce")
        available = pd.to_numeric(merged["AvailableQuantity"], errors="coerce")
        on_hand_value = pd.to_numeric(merged["OnHandValue"], errors="coerce")
        available_value = pd.to_numeric(merged["AvailableValue"], errors="coerce")
        average_unit_cost = on_hand_value.where(on_hand > 0, 0) / on_hand.where(on_hand > 0, 1)
        expected_available_value = (available * average_unit_cost).round(2)
        self._numeric_compare(
            merged,
            merged["AvailableValue"],
            expected_available_value,
            "V2_INVENTORY_AVAILABLE_VALUE_RECONCILIATION",
            "Inventory.AvailableValue must equal AvailableQuantity multiplied by average unit cost.",
            "Inventory",
            "AvailableValue",
            report,
            tolerance=0.01,
        )
        self._compare_mask(merged, on_hand >= -0.0001, "V2_INVENTORY_ON_HAND_NON_NEGATIVE", "Inventory.OnHandQuantity must be non-negative.", "Regenerate Inventory from non-negative accepted transaction quantities.", "error", "Inventory", "OnHandQuantity", report)
        self._compare_mask(merged, reserved >= -0.0001, "V2_INVENTORY_RESERVED_NON_NEGATIVE", "Inventory.ReservedQuantity must be non-negative.", "Generate reserved quantities at or above zero.", "error", "Inventory", "ReservedQuantity", report)
        self._compare_mask(merged, available >= -0.0001, "V2_INVENTORY_AVAILABLE_NON_NEGATIVE", "Inventory.AvailableQuantity must be non-negative.", "Do not reserve more than on-hand quantity.", "error", "Inventory", "AvailableQuantity", report)
        self._compare_mask(merged, reserved <= on_hand + 0.0001, "V2_INVENTORY_RESERVED_LE_ON_HAND", "Inventory.ReservedQuantity must be <= OnHandQuantity.", "Cap reserved quantity at on-hand quantity.", "error", "Inventory", "ReservedQuantity", report)
        self._compare_mask(merged, on_hand_value >= -0.01, "V2_INVENTORY_ON_HAND_VALUE_NON_NEGATIVE", "Inventory.OnHandValue must be non-negative.", "Sum non-negative InventoryTransaction values.", "error", "Inventory", "OnHandValue", report)
        self._compare_mask(merged, available_value >= -0.01, "V2_INVENTORY_AVAILABLE_VALUE_NON_NEGATIVE", "Inventory.AvailableValue must be non-negative.", "Calculate AvailableValue from non-negative available quantity and average cost.", "error", "Inventory", "AvailableValue", report)
        self._compare_mask(merged, available_value <= on_hand_value + 0.01, "V2_INVENTORY_AVAILABLE_VALUE_LE_ON_HAND_VALUE", "Inventory.AvailableValue must not exceed OnHandValue.", "Do not value available stock above on-hand stock.", "error", "Inventory", "AvailableValue", report)
        self._compare_mask(merged, (on_hand > 0.0001) | (on_hand_value.abs() <= 0.01), "V2_INVENTORY_VALUE_ZERO_WHEN_QTY_ZERO", "Inventory.OnHandValue should be zero when OnHandQuantity is zero.", "Keep quantity and value balance aligned.", "error", "Inventory", "OnHandValue", report)
        self._compare_mask(merged, (available.abs() > 0.0001) | (available_value.abs() <= 0.01), "V2_INVENTORY_AVAILABLE_VALUE_ZERO_WHEN_QTY_ZERO", "Inventory.AvailableValue should be zero when AvailableQuantity is zero.", "Keep available quantity and value aligned.", "error", "Inventory", "AvailableValue", report)

        actual_last = pd.to_datetime(merged["LastTransactionDate"], errors="coerce").dt.normalize()
        expected_last = pd.to_datetime(merged["ExpectedLastTransactionDate"], errors="coerce").dt.normalize()
        self._compare_mask(
            merged,
            actual_last == expected_last,
            "V2_INVENTORY_LAST_TRANSACTION_DATE",
            "Inventory.LastTransactionDate must equal MAX(InventoryTransaction.TransactionDate) for the component/plant/warehouse group.",
            "Carry the latest transaction date into the Inventory snapshot.",
            "error",
            "Inventory",
            "LastTransactionDate",
            report,
        )
        last_updated = pd.to_datetime(merged["LastUpdatedDate"], errors="coerce").dt.normalize()
        self._compare_mask(
            merged,
            last_updated >= actual_last,
            "V2_INVENTORY_LAST_UPDATED_DATE",
            "Inventory.LastUpdatedDate must be >= LastTransactionDate.",
            "Refresh Inventory on or after the latest transaction date.",
            "error",
            "Inventory",
            "LastUpdatedDate",
            report,
        )

        expected_status = np.select(
            [
                on_hand.abs() <= 0.0001,
                (on_hand > 0.0001) & (available.abs() <= 0.0001),
                (on_hand > 0.0001) & (available <= (on_hand * 0.10) + 0.0001),
            ],
            ["OutOfStock", "Hold", "LowStock"],
            default="Available",
        )
        self._compare_mask(
            merged,
            merged["InventoryStatus"].astype(str).eq(pd.Series(expected_status, index=merged.index)),
            "V2_INVENTORY_STATUS_LOGIC",
            "Inventory.InventoryStatus must align with OnHandQuantity, ReservedQuantity, and AvailableQuantity.",
            "Derive InventoryStatus from stock quantity thresholds.",
            "error",
            "Inventory",
            "InventoryStatus",
            report,
        )

    def _v2_invoice_payment(self, data: dict[str, pd.DataFrame], plan: LLMGenerationPlan | None, report: DataQualityReport) -> None:
        inv = data["SupplierInvoice"].merge(data["PurchaseOrderHdr"][["PurchaseOrderID", "SupplierID"]], on="PurchaseOrderID", how="left", suffixes=("_invoice", "_po"))
        self._compare_mask(inv, inv["SupplierID_invoice"] == inv["SupplierID_po"], "V2_INVOICE_SUPPLIER_MATCH", "SupplierInvoice.SupplierID must match PurchaseOrderHdr.SupplierID.", "Carry supplier from PO.", "error", "SupplierInvoice", "SupplierID", report)
        self._positive(data["SupplierInvoice"], "InvoiceAmount", "V2_INVOICE_AMOUNT_POSITIVE", report)
        self._numeric_compare(data["SupplierInvoice"], data["SupplierInvoice"]["TotalInvoiceAmount"], data["SupplierInvoice"]["InvoiceAmount"] + data["SupplierInvoice"]["TaxAmount"] + data["SupplierInvoice"]["FreightAmount"], "V2_INVOICE_TOTAL", "SupplierInvoice.TotalInvoiceAmount must equal InvoiceAmount + TaxAmount + FreightAmount.", "SupplierInvoice", "TotalInvoiceAmount", report, tolerance=self._tolerance(plan, "SupplierInvoice", "TotalInvoiceAmount", 0.01))
        pay = data["PaymentTransaction"].merge(data["SupplierInvoice"][["SupplierInvoiceID", "SupplierID", "InvoiceDate", "TotalInvoiceAmount"]], on="SupplierInvoiceID", how="left", suffixes=("_payment", "_invoice"))
        self._compare_mask(pay, pay["SupplierID_payment"] == pay["SupplierID_invoice"], "V2_PAYMENT_SUPPLIER_MATCH", "PaymentTransaction.SupplierID must match SupplierInvoice.SupplierID.", "Carry supplier from invoice.", "error", "PaymentTransaction", "SupplierID", report)
        self._compare_mask(pay, pd.to_datetime(pay["PaymentDate"]) >= pd.to_datetime(pay["InvoiceDate"]), "V2_PAYMENT_AFTER_INVOICE", "PaymentDate must be >= InvoiceDate.", "Generate payment after invoice.", "error", "PaymentTransaction", "PaymentDate", report)
        self._compare_mask(pay, pay["PaymentAmount"] <= pay["TotalInvoiceAmount"] + 0.0001, "V2_PAYMENT_LE_INVOICE", "PaymentAmount must be <= TotalInvoiceAmount.", "Cap payment by invoice total.", "error", "PaymentTransaction", "PaymentAmount", report)
        payment_amount = pd.to_numeric(pay["PaymentAmount"], errors="coerce").fillna(0)
        invoice_total = pd.to_numeric(pay["TotalInvoiceAmount"], errors="coerce").fillna(0)
        payment_expected_status = np.select(
            [
                payment_amount <= 0.0001,
                (payment_amount > 0.0001) & (payment_amount + 0.01 < invoice_total),
            ],
            [
                "Pending",
                "PartiallyPaid",
            ],
            default="Paid",
        )
        payment_status = pay["PaymentStatus"].astype(str)
        payment_status_mask = (
            ((payment_amount <= 0.0001) & payment_status.isin(["Pending", "Failed"]))
            | ((payment_amount > 0.0001) & (payment_amount + 0.01 < invoice_total) & payment_status.eq("PartiallyPaid"))
            | ((payment_amount + 0.01 >= invoice_total) & payment_status.eq("Paid"))
        )
        self._compare_mask(pay, payment_status_mask, "V2_PAYMENT_STATUS_LOGIC", "PaymentTransaction.PaymentStatus must align with PaymentAmount and TotalInvoiceAmount.", "Derive payment status from the actual payment amount.", "error", "PaymentTransaction", "PaymentStatus", report)

        paid_by_invoice = data["PaymentTransaction"].groupby("SupplierInvoiceID", dropna=False)["PaymentAmount"].sum().reset_index(name="TotalPaidAmount")
        invoice_status = data["SupplierInvoice"].merge(paid_by_invoice, on="SupplierInvoiceID", how="left")
        invoice_status["TotalPaidAmount"] = pd.to_numeric(invoice_status["TotalPaidAmount"], errors="coerce").fillna(0)
        invoice_status_total = pd.to_numeric(invoice_status["TotalInvoiceAmount"], errors="coerce").fillna(0)
        invoice_status_text = invoice_status["InvoiceStatus"].astype(str)
        invoice_status_mask = (
            ((invoice_status["TotalPaidAmount"] <= 0.0001) & invoice_status_text.isin(["Submitted", "Approved", "Overdue", "Draft"]))
            | ((invoice_status["TotalPaidAmount"] > 0.0001) & (invoice_status["TotalPaidAmount"] + 0.01 < invoice_status_total) & invoice_status_text.eq("PartiallyPaid"))
            | ((invoice_status["TotalPaidAmount"] + 0.01 >= invoice_status_total) & invoice_status_text.eq("Paid"))
        )
        self._compare_mask(invoice_status, invoice_status_mask, "V2_INVOICE_STATUS_LOGIC", "SupplierInvoice.InvoiceStatus must align with cumulative payment amount.", "Derive invoice status from total payments against the invoice.", "error", "SupplierInvoice", "InvoiceStatus", report)

    def _v2_status_and_rejection_reasons(self, data: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        tolerance = 0.0001
        ql = data["SupplierQuotationLn"]
        self._compare_mask(ql, ~((ql["AwardedFlag"].astype(str).isin(["1", "1.0", "True"])) & (ql["LineStatus"] != "Awarded")), "V2_AWARDED_STATUS", "Awarded quotation lines should have LineStatus = Awarded.", "Align status with AwardedFlag.", "warning", "SupplierQuotationLn", "LineStatus", report)

        line_status = data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "OrderedQuantity", "LineStatus"]].copy()
        line_status = line_status.merge(self._v2_group_sum(data["POSchedule"], ["PurchaseOrderLineID"], "ScheduledQuantity", "TotalScheduledQuantity"), on="PurchaseOrderLineID", how="left")
        line_status = line_status.merge(self._v2_group_sum(data["ShipmentLine"], ["PurchaseOrderLineID"], "ShippedQuantity", "TotalShippedQuantity"), on="PurchaseOrderLineID", how="left")
        line_status = line_status.merge(self._v2_group_sum(data["GoodsReceiptLine"], ["PurchaseOrderLineID"], "ReceivedQuantity", "TotalReceivedQuantity"), on="PurchaseOrderLineID", how="left")
        line_status = line_status.merge(self._v2_group_sum(data["InventoryTransaction"], ["PurchaseOrderLineID"], "TransactionQuantity", "TotalStockInQuantity"), on="PurchaseOrderLineID", how="left")
        for column in ["TotalScheduledQuantity", "TotalShippedQuantity", "TotalReceivedQuantity", "TotalStockInQuantity"]:
            line_status[column] = pd.to_numeric(line_status[column], errors="coerce").fillna(0)
        ordered = pd.to_numeric(line_status["OrderedQuantity"], errors="coerce").fillna(0)
        full_line_mask = (
            line_status["LineStatus"].astype(str).eq("Received")
            & ((line_status["TotalScheduledQuantity"] - ordered).abs() <= tolerance)
            & ((line_status["TotalShippedQuantity"] - ordered).abs() <= tolerance)
            & ((line_status["TotalReceivedQuantity"] - ordered).abs() <= tolerance)
            & ((line_status["TotalStockInQuantity"] - ordered).abs() <= tolerance)
        )
        self._compare_mask(
            line_status,
            full_line_mask,
            "V2_PO_LINE_STATUS_LOGIC",
            "PurchaseOrderLine.LineStatus must be Received and all downstream quantities must equal OrderedQuantity for full-received Procurement v2.",
            "Generate full-received PO lines with schedule, shipment, receipt, inspection, and stock-in quantities equal to OrderedQuantity.",
            "error",
            "PurchaseOrderLine",
            "LineStatus",
            report,
        )
        self._compare_mask(
            line_status,
            ~line_status["LineStatus"].astype(str).eq("Closed"),
            "V2_PO_LINE_CLOSED_WITH_PARTIAL_STOCK_IN",
            "PurchaseOrderLine.LineStatus must not be Closed in the full-received v2 lifecycle.",
            "Use Received for completed inbound PO lines.",
            "error",
            "PurchaseOrderLine",
            "LineStatus",
            report,
        )

        header_status = data["PurchaseOrderHdr"][["PurchaseOrderID", "POStatus"]].copy()
        by_po = line_status.groupby("PurchaseOrderID", dropna=False).agg(
            TotalOrderedQuantity=("OrderedQuantity", "sum"),
            TotalScheduledQuantity=("TotalScheduledQuantity", "sum"),
            TotalShippedQuantity=("TotalShippedQuantity", "sum"),
            TotalReceivedQuantity=("TotalReceivedQuantity", "sum"),
            TotalStockInQuantity=("TotalStockInQuantity", "sum"),
        ).reset_index()
        header_status = header_status.merge(by_po, on="PurchaseOrderID", how="left").fillna(0)
        po_status_text = header_status["POStatus"].astype(str)
        po_status_mask = (
            po_status_text.eq("Received")
            & ((header_status["TotalScheduledQuantity"] - header_status["TotalOrderedQuantity"]).abs() <= tolerance)
            & ((header_status["TotalShippedQuantity"] - header_status["TotalOrderedQuantity"]).abs() <= tolerance)
            & ((header_status["TotalReceivedQuantity"] - header_status["TotalOrderedQuantity"]).abs() <= tolerance)
            & ((header_status["TotalStockInQuantity"] - header_status["TotalOrderedQuantity"]).abs() <= tolerance)
        )
        self._compare_mask(header_status, po_status_mask, "V2_PO_HEADER_STATUS_LOGIC", "PurchaseOrderHdr.POStatus must be Received and all aggregate downstream quantities must equal ordered quantity for full-received Procurement v2.", "Generate full-received PO headers with completed downstream lifecycle totals.", "error", "PurchaseOrderHdr", "POStatus", report)
        self._compare_mask(
            header_status,
            ~po_status_text.eq("Closed"),
            "V2_PO_HEADER_CLOSED_WITH_PARTIAL_STOCK_IN",
            "PurchaseOrderHdr.POStatus must not be Closed in the full-received v2 lifecycle.",
            "Use Received for completed inbound POs.",
            "error",
            "PurchaseOrderHdr",
            "POStatus",
            report,
        )

        schedule_status = data["POSchedule"][["POScheduleID", "ScheduledQuantity", "ScheduleStatus"]].merge(
            self._v2_group_sum(data["ShipmentLine"], ["POScheduleID"], "ShippedQuantity", "TotalShippedQuantity"),
            on="POScheduleID",
            how="left",
        ).fillna({"TotalShippedQuantity": 0})
        shipped_schedule = pd.to_numeric(schedule_status["TotalShippedQuantity"], errors="coerce").fillna(0)
        scheduled_quantity = pd.to_numeric(schedule_status["ScheduledQuantity"], errors="coerce").fillna(0)
        schedule_status_text = schedule_status["ScheduleStatus"].astype(str)
        schedule_mask = schedule_status_text.eq("Shipped") & ((shipped_schedule - scheduled_quantity).abs() <= tolerance)
        self._compare_mask(schedule_status, schedule_mask, "V2_PO_SCHEDULE_STATUS_LOGIC", "POSchedule.ScheduleStatus must be Shipped and shipped quantity must equal scheduled quantity.", "Generate completed schedules for the full-received v2 lifecycle.", "error", "POSchedule", "ScheduleStatus", report)

        shipment_quantities = data["ShipmentLine"].groupby("ShipmentID", dropna=False)["ShippedQuantity"].sum().reset_index(name="TotalShippedQuantity")
        receipt_quantities = data["GoodsReceiptLine"].merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ShipmentID"]], on="GoodsReceiptID", how="left").groupby("ShipmentID", dropna=False)["ReceivedQuantity"].sum().reset_index(name="TotalReceivedQuantity")
        shipment_status = data["ShipmentHdr"][["ShipmentID", "ShipmentStatus"]].merge(shipment_quantities, on="ShipmentID", how="left").merge(receipt_quantities, on="ShipmentID", how="left").fillna(0)
        shipment_status_text = shipment_status["ShipmentStatus"].astype(str)
        shipment_mask = shipment_status_text.eq("Delivered") & ((shipment_status["TotalReceivedQuantity"] - shipment_status["TotalShippedQuantity"]).abs() <= tolerance)
        self._compare_mask(shipment_status, shipment_mask, "V2_SHIPMENT_DELIVERED_WITH_PARTIAL_RECEIPT", "ShipmentHdr.ShipmentStatus must be Delivered and received quantity must equal shipped quantity.", "Generate delivered shipments for the full-received v2 lifecycle.", "error", "ShipmentHdr", "ShipmentStatus", report)

        receipt_status = data["GoodsReceiptHeader"][["GoodsReceiptID", "ReceiptStatus"]].merge(
            data["GoodsReceiptLine"].groupby("GoodsReceiptID", dropna=False).agg(
                TotalDamagedQuantity=("DamagedQuantity", "sum"),
                TotalShortQuantity=("ShortQuantity", "sum"),
                TotalReceivedQuantity=("ReceivedQuantity", "sum"),
                TotalShippedQuantity=("ShippedQuantity", "sum"),
            ).reset_index(),
            on="GoodsReceiptID",
            how="left",
        ).fillna(0)
        receipt_mask = (
            receipt_status["ReceiptStatus"].astype(str).eq("Received")
            & (receipt_status["TotalDamagedQuantity"].abs() <= tolerance)
            & (receipt_status["TotalShortQuantity"].abs() <= tolerance)
            & ((receipt_status["TotalReceivedQuantity"] - receipt_status["TotalShippedQuantity"]).abs() <= tolerance)
        )
        self._compare_mask(receipt_status, receipt_mask, "V2_RECEIPT_STATUS_LOGIC", "GoodsReceiptHeader.ReceiptStatus must be Received with no short or damaged quantity.", "Generate fully received goods receipts with zero short and damaged quantities.", "error", "GoodsReceiptHeader", "ReceiptStatus", report)

        result = data["InspectionResult"]
        rejected = pd.to_numeric(result["RejectedQuantity"], errors="coerce").fillna(0)
        accepted = pd.to_numeric(result["AcceptedQuantity"], errors="coerce").fillna(0)
        zero_bad = rejected.eq(0) & ~result["RejectionReason"].fillna("").isin(["", "Not Applicable"])
        self._compare_mask(result, ~zero_bad, "V2_REJECTION_REASON_ZERO", "Rows with RejectedQuantity = 0 must not contain a real RejectionReason.", "Use blank or Not Applicable when no quantity is rejected.", "error", "InspectionResult", "RejectionReason", report)
        missing = rejected.gt(0) & result["RejectionReason"].fillna("").isin(["", "Not Applicable"])
        if missing.any():
            report.record_check(False)
            report.add_issue("error", "V2_REJECTION_REASON_REQUIRED", "Rows with RejectedQuantity > 0 must have a populated rejection reason.", "Populate rejection reasons for rejected rows.", table_name="InspectionResult", column_name="RejectionReason", sample_failed_rows=self._sample_rows(result[missing]))
        else:
            report.record_check(True)
        inspected = pd.to_numeric(result["InspectedQuantity"], errors="coerce").fillna(0)
        status_mask = (rejected.abs() <= tolerance) & ((accepted - inspected).abs() <= tolerance) & result["ResultStatus"].astype(str).eq("Passed")
        self._compare_mask(result, status_mask, "V2_INSPECTION_STATUS_REALISM", "InspectionResult.ResultStatus must be Passed with AcceptedQuantity equal to InspectedQuantity and RejectedQuantity equal to zero.", "Generate passed inspection results for the full-received v2 lifecycle.", "error", "InspectionResult", "ResultStatus", report)
        incoming_status = data["IncomingInspection"][["InspectionID", "InspectionStatus"]].merge(result[["InspectionID", "AcceptedQuantity", "RejectedQuantity", "ResultStatus"]], on="InspectionID", how="left")
        incoming_mask = incoming_status["InspectionStatus"].astype(str).eq("Passed") & incoming_status["ResultStatus"].astype(str).eq("Passed")
        self._compare_mask(incoming_status, incoming_mask, "V2_INCOMING_INSPECTION_STATUS_LOGIC", "IncomingInspection.InspectionStatus must be Passed when the linked InspectionResult is Passed.", "Generate passed incoming inspections for the full-received v2 lifecycle.", "error", "IncomingInspection", "InspectionStatus", report)
        rejected_rows = result[rejected > 0]
        enough_variety = len(rejected_rows) <= 50 or rejected_rows["RejectionReason"].nunique(dropna=True) >= 3
        report.record_check(enough_variety)
        if not enough_variety:
            report.add_issue("warning", "V2_REJECTION_REASON_DIVERSITY", "Rejected rows have too little RejectionReason variety.", "Use at least three rejection reasons for many rejected rows.", table_name="InspectionResult", column_name="RejectionReason")

    def _same_table_date(self, dataframe: pd.DataFrame, earlier_col: str, later_col: str, check_type: str, table_name: str, report: DataQualityReport) -> None:
        if earlier_col not in dataframe.columns or later_col not in dataframe.columns:
            return
        mask = pd.to_datetime(dataframe[earlier_col], errors="coerce") <= pd.to_datetime(dataframe[later_col], errors="coerce")
        self._compare_mask(dataframe, mask, check_type, f"{earlier_col} must be <= {later_col}.", "Maintain lifecycle date order.", "error", table_name, later_col, report)

    def _date_order(self, earlier, later, key, earlier_col, later_col, check_type, report) -> None:
        if earlier is None or later is None or key not in earlier.columns or key not in later.columns or earlier_col not in earlier.columns or later_col not in later.columns:
            report.record_check(False)
            report.add_issue("warning", check_type, f"Skipped date check {earlier_col} <= {later_col}; required lineage columns are missing.", "Add/link the required date and key columns.", None, None)
            return
        merged = later.merge(earlier[[key, earlier_col]], on=key, how="left")
        mask = pd.to_datetime(merged[later_col], errors="coerce") >= pd.to_datetime(merged[earlier_col], errors="coerce")
        self._compare_mask(merged, mask, check_type, f"{earlier_col} must be <= {later_col}.", "Maintain procurement lifecycle date order.", "error", None, None, report)

    def _quantity_join(self, left, right, key, left_qty, right_qty, check_type, report) -> None:
        if left is None or right is None or key not in left.columns or key not in right.columns or left_qty not in left.columns or right_qty not in right.columns:
            report.record_check(False)
            report.add_issue("warning", check_type, f"Skipped quantity check {left_qty} <= {right_qty}; required lineage columns are missing.", "Add/link the required quantity and key columns.", None, None)
            return
        right_subset = right[[key, right_qty]].rename(columns={right_qty: "__right_qty"})
        merged = left.merge(right_subset, on=key, how="left")
        mask = pd.to_numeric(merged[left_qty], errors="coerce") <= pd.to_numeric(merged["__right_qty"], errors="coerce")
        self._compare_mask(merged, mask, check_type, f"{left_qty} must be <= {right_qty}.", "Respect procurement quantity lifecycle.", "error", None, left_qty, report)

    def _positive(self, dataframe, column_name, check_type, report) -> None:
        if dataframe is None or column_name not in dataframe.columns:
            return
        mask = pd.to_numeric(dataframe[column_name], errors="coerce") > 0
        self._compare_mask(dataframe, mask, check_type, f"{column_name} must be > 0.", "Generate positive procurement quantities.", "error", None, column_name, report)

    def _equality_join(self, left, right, key, left_col, right_col, check_type, level, report) -> None:
        if left is None or right is None or key not in left.columns or key not in right.columns or left_col not in left.columns or right_col not in right.columns:
            return
        merged = right.merge(left[[key, left_col]], on=key, how="left", suffixes=("_right", "_left"))
        right_column = f"{right_col}_right" if f"{right_col}_right" in merged.columns else right_col
        left_column = f"{left_col}_left" if f"{left_col}_left" in merged.columns else left_col
        self._compare_mask(merged, merged[right_column] == merged[left_column], check_type, f"{right_col} must match linked {left_col}.", "Carry values through lifecycle lineage.", level, None, right_col, report)

    def _numeric_compare(self, dataframe, actual, expected, check_type, message, table_name, column_name, report, tolerance=0.0001) -> None:
        actual_num = pd.to_numeric(actual, errors="coerce")
        expected_num = pd.to_numeric(expected, errors="coerce")
        mask = (actual_num - expected_num).abs() <= tolerance
        self._compare_mask(dataframe, mask, check_type, message, "Recalculate or regenerate the reconciled value from source records.", "error", table_name, column_name, report)

    def _v2_group_sum(self, dataframe: pd.DataFrame, keys: list[str], quantity_column: str, output_column: str) -> pd.DataFrame:
        grouped = dataframe.copy()
        grouped[quantity_column] = pd.to_numeric(grouped[quantity_column], errors="coerce").fillna(0)
        return grouped.groupby(keys, dropna=False, as_index=False)[quantity_column].sum().rename(columns={quantity_column: output_column})

    def _compare_mask(self, dataframe, mask, check_type, message, suggested_fix, level, table_name, column_name, report) -> None:
        mask = pd.Series(mask, index=dataframe.index).fillna(False)
        passed = bool(mask.all())
        report.record_check(passed)
        mismatches = int((~mask).sum())
        report.add_reconciliation_summary(
            ReconciliationSummary(check_type=check_type, status="passed" if passed else "failed", rows_checked=len(dataframe), mismatches=mismatches, message=message)
        )
        if not passed:
            report.add_issue(level, check_type, message, suggested_fix, table_name=table_name, column_name=column_name, sample_failed_rows=self._sample_rows(dataframe.loc[~mask]))

    def _tolerance(self, plan: LLMGenerationPlan | None, table_name: str, column_name: str, default: float) -> float:
        if plan is not None:
            for rule in plan.formula_rules:
                if (
                    rule.target_table == table_name
                    and rule.target_column == column_name
                    and rule.tolerance_type != "none"
                    and rule.tolerance_value is not None
                ):
                    return rule.tolerance_value
        return default

    def _dataframes_by_role(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract) -> dict[str, pd.DataFrame]:
        return {table.table_role: dataframes[table.table_name] for table in schema.tables.values() if table.table_name in dataframes}

    def _sample_rows(self, dataframe: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        return [_json_safe(row) for row in dataframe.head(limit).to_dict(orient="records")]


class ProcurementDataQualityEngine:
    """Combined Phase 11 validation and reconciliation engine."""

    def __init__(self) -> None:
        self.validator = ProcurementGeneratedDataValidator()
        self.reconciler = ProcurementReconciler()

    def validate_and_reconcile(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        plan: LLMGenerationPlan | None = None,
        model_version: str = "v2",
    ) -> DataQualityReport:
        if model_version != "v2":
            raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
        report = self.validator.validate_dataset(dataframes, schema, plan, model_version=model_version)
        reconciliation_report = self.reconciler.reconcile_dataset(dataframes, schema, plan, model_version=model_version)
        report.merge(reconciliation_report)
        return report


def format_data_quality_report(
    report: DataQualityReport,
    json_path: str | None = None,
    markdown_path: str | None = None,
    model_version: str | None = None,
) -> str:
    """Format a concise CLI summary."""

    lines = [
        "Generated data validation completed.",
        f"Tables checked: {len(report.table_summaries)}",
        f"Checks run: {report.checks_run}",
        f"Checks passed: {report.checks_passed}",
        f"Checks failed: {report.checks_failed}",
        f"Errors: {report.error_count}",
        f"Warnings: {report.warning_count}",
        f"Overall status: {report.overall_status}",
    ]
    if model_version:
        lines.insert(1, f"Model version: {model_version}")
    if json_path:
        lines.append(f"Report JSON: {json_path}")
    if markdown_path:
        lines.append(f"Report Markdown: {markdown_path}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors[:10], start=1):
            lines.append(f"{index}. {issue.check_type} | Table: {issue.table_name or 'N/A'}")
            if issue.column_name:
                lines.append(f"   Column: {issue.column_name}")
            lines.append(f"   Message: {issue.message}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, issue in enumerate(report.warnings[:10], start=1):
            lines.append(f"{index}. {issue.check_type} | Table: {issue.table_name or 'N/A'}")
            if issue.column_name:
                lines.append(f"   Column: {issue.column_name}")
            lines.append(f"   Message: {issue.message}")
    return "\n".join(lines)
