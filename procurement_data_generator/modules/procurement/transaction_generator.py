"""Core procurement transaction/process data generator for Phase 9."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

import pandas as pd
from faker import Faker

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.modules.procurement.financial_realism_profiles import (
    generate_order_quantity,
    generate_quote_price,
)
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.name_generators import (
    ARTIFICIAL_NUMERIC_SUFFIX_PATTERN,
    NameGenerationError,
    ProcurementNameGenerator,
)


TRANSACTION_ROLE_ORDER = [
    "purchase_requisition_header",
    "purchase_requisition_line",
    "purchase_order_header",
    "purchase_order_line",
    "shipment_header",
    "shipment_line",
    "goods_receipt_header",
    "goods_receipt_line",
    "quality_inspection_header",
    "quality_inspection_line",
    "inventory_transaction",
    "inventory_balance",
]

V2_TRANSACTION_ROLE_ORDER = [
    "purchase_requisition",
    "purchase_req_line",
    "rfq_header",
    "rfq_line",
    "supplier_quotation",
    "supplier_quotation_line",
    "purchase_order_header",
    "purchase_order_line",
    "po_schedule",
    "shipment_header",
    "shipment_line",
    "goods_receipt_header",
    "goods_receipt_line",
    "incoming_inspection",
    "inspection_result",
    "inventory_transaction",
    "inventory",
    "supplier_invoice",
    "payment_transaction",
]

V2_REJECTION_REASONS = [
    "Dimension Out of Tolerance",
    "Surface Defect",
    "Electrical Test Failure",
    "Packaging Damage",
    "Material Contamination",
    "Wrong Specification",
    "Thermal Stress Failure",
    "Supplier Documentation Issue",
    "Visual Defect",
    "Functional Test Failure",
]


@dataclass
class ProcurementGenerationContext:
    """Holds lineage records used across transaction generation."""

    requisition_headers: list[dict[str, Any]]
    requisition_lines: list[dict[str, Any]]
    purchase_order_headers: list[dict[str, Any]]
    purchase_order_lines: list[dict[str, Any]]
    shipment_headers: list[dict[str, Any]]
    shipment_lines: list[dict[str, Any]]
    goods_receipt_headers: list[dict[str, Any]]
    goods_receipt_lines: list[dict[str, Any]]
    quality_inspection_headers: list[dict[str, Any]]
    quality_inspection_lines: list[dict[str, Any]]
    inventory_transactions: list[dict[str, Any]]
    inventory_balances: list[dict[str, Any]]


class ProcurementTransactionGenerator:
    """Generate procurement transaction tables from metadata, plan, and master data."""

    def __init__(self) -> None:
        self.name_generator = ProcurementNameGenerator()

    def generate_transaction_data(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        master_dataframes: dict[str, pd.DataFrame],
        seed: int | None = None,
        model_version: str = "v1",
    ) -> tuple[dict[str, pd.DataFrame], ValidationReport]:
        """Generate transaction/process dataframes and validate basic lifecycle invariants."""

        if model_version == "v2":
            return self._generate_v2_transaction_data(schema, plan, master_dataframes, seed)

        report = ValidationReport()
        rng = random.Random(seed)
        faker = Faker()
        if seed is not None:
            faker.seed_instance(seed)

        tables_by_role = {table.table_role: table for table in self.get_transaction_tables(schema)}
        master_by_role = self._dataframes_by_role(master_dataframes, schema)
        context = ProcurementGenerationContext([], [], [], [], [], [], [], [], [], [], [], [])
        dataframes: dict[str, pd.DataFrame] = {}

        generators = {
            "purchase_requisition_header": self._generate_purchase_requisition_headers,
            "purchase_requisition_line": self._generate_purchase_requisition_lines,
            "purchase_order_header": self._generate_purchase_order_headers,
            "purchase_order_line": self._generate_purchase_order_lines,
            "shipment_header": self._generate_shipment_headers,
            "shipment_line": self._generate_shipment_lines,
            "goods_receipt_header": self._generate_goods_receipt_headers,
            "goods_receipt_line": self._generate_goods_receipt_lines,
            "quality_inspection_header": self._generate_quality_inspection_headers,
            "quality_inspection_line": self._generate_quality_inspection_lines,
            "inventory_transaction": self._generate_inventory_transactions,
            "inventory_balance": self._generate_inventory_balances,
        }

        for role in TRANSACTION_ROLE_ORDER:
            table = tables_by_role.get(role)
            if table is None:
                continue
            records = generators[role](table, plan, master_by_role, context, rng, faker, report)
            setattr(context, self._context_attr_for_role(role), records)
            dataframe = self._records_to_dataframe(table, records, report)
            dataframes[table.table_name] = dataframe

        self._refresh_mutated_context_tables(tables_by_role, context, dataframes, report)
        self.validate_generated_transaction_data(dataframes, schema, master_dataframes, report)
        return dataframes, report

    def get_transaction_tables(self, schema: SchemaContract, model_version: str = "v1") -> list[TableContract]:
        """Return transaction tables in lifecycle order."""

        table_by_role = {table.table_role: table for table in schema.tables.values()}
        order = V2_TRANSACTION_ROLE_ORDER if model_version == "v2" else TRANSACTION_ROLE_ORDER
        return [table_by_role[role] for role in order if role in table_by_role]

    def export_transaction_data(self, dataframes: dict[str, pd.DataFrame], output_folder: str | Path) -> list[Path]:
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for table_name, dataframe in dataframes.items():
            path = output_path / f"{table_name}.csv"
            dataframe.to_csv(path, index=False)
            paths.append(path)
        return paths

    def _generate_v2_transaction_data(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        master_dataframes: dict[str, pd.DataFrame],
        seed: int | None,
    ) -> tuple[dict[str, pd.DataFrame], ValidationReport]:
        report = ValidationReport()
        rng = random.Random(seed)
        faker = Faker()
        if seed is not None:
            faker.seed_instance(seed)

        table_by_role = {table.table_role: table for table in self.get_transaction_tables(schema, model_version="v2")}
        dataframes: dict[str, pd.DataFrame] = {}
        records: dict[str, list[dict[str, Any]]] = {}

        def save(role: str, role_records: list[dict[str, Any]]) -> None:
            table = table_by_role.get(role)
            if table is None:
                return
            records[role] = role_records
            dataframes[table.table_name] = self._records_to_dataframe(table, role_records, report)

        save("purchase_requisition", self._v2_purchase_requisitions(table_by_role["purchase_requisition"], plan, master_dataframes, rng, faker))
        save("purchase_req_line", self._v2_purchase_req_lines(table_by_role["purchase_req_line"], plan, master_dataframes, records, rng))
        save("rfq_header", self._v2_rfq_headers(table_by_role["rfq_header"], plan, records, rng, faker))
        save("rfq_line", self._v2_rfq_lines(table_by_role["rfq_line"], plan, records, rng))
        save("supplier_quotation", self._v2_supplier_quotations(table_by_role["supplier_quotation"], plan, master_dataframes, records, rng))
        save("supplier_quotation_line", self._v2_supplier_quotation_lines(table_by_role["supplier_quotation_line"], plan, master_dataframes, records, rng))
        save("purchase_order_header", self._v2_purchase_order_headers(table_by_role["purchase_order_header"], plan, records, rng))
        save("purchase_order_line", self._v2_purchase_order_lines(table_by_role["purchase_order_line"], plan, records, rng))
        save("po_schedule", self._v2_po_schedules(table_by_role["po_schedule"], plan, records, rng))
        save("shipment_header", self._v2_shipment_headers(table_by_role["shipment_header"], plan, records, rng))
        save("shipment_line", self._v2_shipment_lines(table_by_role["shipment_line"], plan, records, rng))
        save("goods_receipt_header", self._v2_goods_receipt_headers(table_by_role["goods_receipt_header"], plan, master_dataframes, records, rng))
        save("goods_receipt_line", self._v2_goods_receipt_lines(table_by_role["goods_receipt_line"], plan, records, rng))
        save("incoming_inspection", self._v2_incoming_inspections(table_by_role["incoming_inspection"], plan, records, rng, faker))
        save("inspection_result", self._v2_inspection_results(table_by_role["inspection_result"], plan, records, rng))
        save("inventory_transaction", self._v2_inventory_transactions(table_by_role["inventory_transaction"], plan, records, rng))
        save("inventory", self._v2_inventory(table_by_role["inventory"], plan, records, rng))
        save("supplier_invoice", self._v2_supplier_invoices(table_by_role["supplier_invoice"], plan, records, rng))
        save("payment_transaction", self._v2_payment_transactions(table_by_role["payment_transaction"], plan, records, rng))

        self._refresh_v2_statuses(records, dataframes, table_by_role, report)
        self._validate_v2_transaction_data(dataframes, schema, master_dataframes, report)
        return dataframes, report

    def _v2_purchase_requisitions(self, table, plan, master_dataframes, rng, faker):
        count = self._target_rows(table, plan)
        plants = master_dataframes["Plant"].to_dict("records")
        start = date(2025, 1, 1)
        records = []
        for row_id in range(1, count + 1):
            req_date = start + timedelta(days=rng.randint(0, 240))
            plant = plants[(row_id - 1) % len(plants)]
            records.append(
                {
                    "id": row_id,
                    "plant_id": plant["PlantID"],
                    "requisition_date": req_date,
                    "required_date": self._v2_add_days(req_date, rng.randint(12, 45)),
                    "requester_name": faker.name(),
                    "department": self._choice(["Production", "Maintenance", "Quality", "Engineering", "Warehouse", "Procurement"], rng),
                    "priority": self._weighted_choice(["Low", "Medium", "High", "Urgent"], [12, 55, 25, 8], rng),
                    "status": self._v2_varied_status(row_id, "ConvertedToRFQ", ["Submitted", "Approved", "Cancelled"], [0.05, 0.12, 0.02], rng),
                }
            )
        return records

    def _v2_purchase_req_lines(self, table, plan, master_dataframes, records, rng):
        count = self._target_rows(table, plan)
        headers = records["purchase_requisition"]
        component_df = master_dataframes["ComponentMaster"]
        components = list(component_df["ComponentID"])
        component_lookup = component_df.set_index("ComponentID")[["ComponentCategory", "StandardCost"]].to_dict("index")
        quantity_min, quantity_max = self._column_min_max(table, "RequestedQuantity", 1.0, 1000.0)
        rows = []
        for row_id in range(1, count + 1):
            header = headers[(row_id - 1) % len(headers)]
            component_id = components[(row_id - 1 + rng.randrange(len(components))) % len(components)]
            component = component_lookup.get(component_id, {})
            category = component.get("ComponentCategory")
            expected_unit_price = float(component.get("StandardCost", 100.0)) * 1.35
            rows.append(
                {
                    "id": row_id,
                    "requisition_id": header["id"],
                    "component_id": component_id,
                    "requested_quantity": generate_order_quantity(category, expected_unit_price, rng, quantity_min, quantity_max),
                    "required_date": header["required_date"],
                    "line_status": self._v2_varied_status(row_id, "ConvertedToRFQ", ["Open", "Approved", "Cancelled"], [0.04, 0.1, 0.02], rng),
                    "requisition_date": header["requisition_date"],
                    "plant_id": header["plant_id"],
                }
            )
        return rows

    def _v2_rfq_headers(self, table, plan, records, rng, faker):
        count = self._target_rows(table, plan)
        requisitions = records["purchase_requisition"]
        rows = []
        for row_id in range(1, count + 1):
            req = requisitions[(row_id - 1) % len(requisitions)]
            rfq_date = self._v2_add_days(req["requisition_date"], rng.randint(1, 8))
            rows.append(
                {
                    "id": row_id,
                    "requisition_id": req["id"],
                    "rfq_date": rfq_date,
                    "rfq_due_date": self._v2_add_days(rfq_date, rng.randint(7, 21)),
                    "buyer_name": faker.name(),
                    "rfq_status": self._v2_varied_status(row_id, "Closed", ["Sent", "Created", "Cancelled"], [0.18, 0.04, 0.02], rng),
                    "plant_id": req["plant_id"],
                    "requisition_date": req["requisition_date"],
                }
            )
        return rows

    def _v2_rfq_lines(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        rfqs = records["rfq_header"]
        req_lines = records["purchase_req_line"]
        req_by_id = {row["id"]: row for row in req_lines}
        rows = []
        for row_id in range(1, count + 1):
            rfq = rfqs[(row_id - 1) % len(rfqs)]
            candidates = [line for line in req_lines if line["requisition_id"] == rfq["requisition_id"]] or req_lines
            req_line = candidates[(row_id - 1) % len(candidates)]
            rows.append(
                {
                    "id": row_id,
                    "rfq_id": rfq["id"],
                    "requisition_line_id": req_line["id"],
                    "component_id": req_line["component_id"],
                    "rfq_quantity": round(min(req_line["requested_quantity"], req_line["requested_quantity"] * rng.uniform(0.9, 1.0)), 2),
                    "required_date": req_line["required_date"],
                    "line_status": "Awarded" if row_id <= 5400 else self._v2_varied_status(row_id, "Quoted", ["Open", "Closed"], [0.05, 0.15], rng),
                    "rfq_date": rfq["rfq_date"],
                    "plant_id": rfq["plant_id"],
                    "requested_quantity": req_by_id[req_line["id"]]["requested_quantity"],
                }
            )
        return rows

    def _v2_supplier_quotations(self, table, plan, master_dataframes, records, rng):
        count = self._target_rows(table, plan)
        rfqs = records["rfq_header"]
        rfq_lines = records["rfq_line"]
        supplier_components = master_dataframes["SupplierComponent"]
        supplier_by_component = supplier_components.groupby("ComponentID")["SupplierID"].apply(list).to_dict()
        rows = []
        for row_id in range(1, count + 1):
            rfq = rfqs[(row_id - 1) % len(rfqs)]
            rfq_component_ids = [line["component_id"] for line in rfq_lines if line["rfq_id"] == rfq["id"]]
            component_id = rfq_component_ids[(row_id - 1) % len(rfq_component_ids)] if rfq_component_ids else None
            suppliers = supplier_by_component.get(component_id) or list(master_dataframes["SupplierMaster"]["SupplierID"])
            quote_date = self._v2_add_days(rfq["rfq_date"], rng.randint(1, 7))
            rows.append(
                {
                    "id": row_id,
                    "rfq_id": rfq["id"],
                    "supplier_id": suppliers[(row_id - 1) % len(suppliers)],
                    "quotation_date": quote_date,
                    "valid_until_date": self._v2_add_days(quote_date, rng.randint(20, 60)),
                    "quotation_status": "Awarded" if row_id <= 1800 else self._v2_varied_status(row_id, "Rejected", ["Submitted", "UnderReview", "Expired"], [0.12, 0.08, 0.06], rng),
                    "currency_code": "USD",
                    "rfq_date": rfq["rfq_date"],
                    "plant_id": rfq["plant_id"],
                    "quoted_component_id": component_id,
                }
            )
        return rows

    def _v2_supplier_quotation_lines(self, table, plan, master_dataframes, records, rng):
        count = self._target_rows(table, plan)
        quotations = records["supplier_quotation"]
        rfq_lines = records["rfq_line"]
        supplier_component = master_dataframes["SupplierComponent"]
        component_contract = {
            (int(row.SupplierID), int(row.ComponentID)): (float(row.ContractPrice), int(row.LeadTimeDays))
            for row in supplier_component.itertuples(index=False)
        }
        eligible_components_by_supplier = supplier_component.groupby("SupplierID")["ComponentID"].apply(set).to_dict()
        quotations_by_rfq: dict[int, list[dict[str, Any]]] = {}
        for quote in quotations:
            quotations_by_rfq.setdefault(quote["rfq_id"], []).append(quote)
        award_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for rfq_line in rfq_lines:
            eligible_quotes = [
                quote
                for quote in quotations_by_rfq.get(rfq_line["rfq_id"], [])
                if rfq_line["component_id"] in eligible_components_by_supplier.get(quote["supplier_id"], set())
            ]
            if eligible_quotes:
                award_candidates.append((rfq_line, eligible_quotes[(rfq_line["id"] - 1) % len(eligible_quotes)]))
        awarded_rfq_line_ids: set[int] = set()
        rows = []
        for row_id in range(1, count + 1):
            if row_id <= min(5400, len(award_candidates)):
                rfq_line, quote = award_candidates[row_id - 1]
                awarded = 1
                awarded_rfq_line_ids.add(rfq_line["id"])
            else:
                quote = quotations[(row_id - 1) % len(quotations)]
                candidates = [line for line in rfq_lines if line["rfq_id"] == quote["rfq_id"] and line["id"] not in awarded_rfq_line_ids] or [
                    line for line in rfq_lines if line["rfq_id"] == quote["rfq_id"]
                ] or rfq_lines
                eligible_components = eligible_components_by_supplier.get(quote["supplier_id"], set())
                eligible_candidates = [line for line in candidates if line["component_id"] in eligible_components]
                if eligible_candidates:
                    candidates = eligible_candidates
                elif quote.get("quoted_component_id") is not None:
                    quoted_component_candidates = [line for line in rfq_lines if line["rfq_id"] == quote["rfq_id"] and line["component_id"] == quote["quoted_component_id"]]
                    if quoted_component_candidates:
                        candidates = quoted_component_candidates
                rfq_line = candidates[(row_id - 1) % len(candidates)]
                awarded = 0
            contract_price, lead_time = component_contract.get((quote["supplier_id"], rfq_line["component_id"]), (rng.uniform(10, 5000), rng.randint(3, 60)))
            unit_price = generate_quote_price(contract_price, rng)
            qty = round(min(rfq_line["rfq_quantity"], rfq_line["rfq_quantity"] * rng.uniform(0.96, 1.0)), 2)
            rows.append(
                {
                    "id": row_id,
                    "quotation_id": quote["id"],
                    "rfq_line_id": rfq_line["id"],
                    "component_id": rfq_line["component_id"],
                    "quoted_quantity": qty,
                    "quoted_unit_price": unit_price,
                    "quoted_line_amount": round(qty * unit_price, 2),
                    "lead_time_days": lead_time,
                    "awarded_flag": awarded,
                    "line_status": "Awarded" if awarded else "Rejected",
                    "supplier_id": quote["supplier_id"],
                    "rfq_quantity": qty,
                    "quotation_date": quote["quotation_date"],
                    "plant_id": quote["plant_id"],
                }
            )
        return rows

    def _v2_purchase_order_headers(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        quotations = records["supplier_quotation"]
        awarded_quotation_ids = {line["quotation_id"] for line in records.get("supplier_quotation_line", []) if line.get("awarded_flag") == 1}
        quotations = [quote for quote in quotations if quote["id"] in awarded_quotation_ids]
        rows = []
        for row_id, quote in enumerate(quotations[:count], start=1):
            order_date = self._v2_add_days(quote["quotation_date"], rng.randint(1, 8))
            rows.append(
                {
                    "id": row_id,
                    "supplier_id": quote["supplier_id"],
                    "plant_id": quote["plant_id"],
                    "quotation_id": quote["id"],
                    "order_date": order_date,
                    "expected_delivery_date": self._v2_add_days(order_date, rng.randint(15, 45)),
                    "po_status": self._v2_varied_status(row_id, "Closed", ["Sent", "Approved", "PartiallyReceived"], [0.12, 0.1, 0.2], rng),
                    "total_amount": 0.0,
                    "currency_code": "USD",
                    "quotation_date": quote["quotation_date"],
                }
            )
        return rows

    def _v2_purchase_order_lines(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        po_headers = records["purchase_order_header"]
        quote_lines = records["supplier_quotation_line"]
        awarded_by_quote: dict[int, list[dict[str, Any]]] = {}
        remaining_quote_quantity: dict[int, float] = {}
        for line in quote_lines:
            if line["awarded_flag"] == 1:
                awarded_by_quote.setdefault(line["quotation_id"], []).append(line)
                remaining_quote_quantity[line["id"]] = float(line["quoted_quantity"])
        rows = []
        totals: dict[int, float] = {}
        for row_id in range(1, count + 1):
            po = po_headers[(row_id - 1) % len(po_headers)]
            candidates = [
                line
                for line in (awarded_by_quote.get(po["quotation_id"]) or [line for line in quote_lines if line["awarded_flag"] == 1])
                if remaining_quote_quantity.get(line["id"], 0.0) > 0.0001
            ]
            if not candidates:
                continue
            qline = candidates[(row_id - 1) % len(candidates)]
            qty = round(min(float(qline["quoted_quantity"]), remaining_quote_quantity[qline["id"]]), 2)
            if qty <= 0:
                continue
            remaining_quote_quantity[qline["id"]] = round(remaining_quote_quantity[qline["id"]] - qty, 2)
            unit_price = qline["quoted_unit_price"]
            amount = round(qty * unit_price, 2)
            totals[po["id"]] = totals.get(po["id"], 0.0) + amount
            rows.append(
                {
                    "id": row_id,
                    "purchase_order_id": po["id"],
                    "quotation_line_id": qline["id"],
                    "component_id": qline["component_id"],
                    "ordered_quantity": qty,
                    "unit_price": unit_price,
                    "line_amount": amount,
                    "open_quantity": qty,
                    "line_status": "Open",
                    "order_date": po["order_date"],
                    "expected_delivery_date": po["expected_delivery_date"],
                    "supplier_id": po["supplier_id"],
                    "plant_id": po["plant_id"],
                }
            )
        for po in po_headers:
            po["total_amount"] = round(totals.get(po["id"], 0.0), 2)
        return rows

    def _v2_po_schedules(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        po_lines = records["purchase_order_line"]
        remaining = {line["id"]: float(line["ordered_quantity"]) for line in po_lines}
        rows = []
        candidate_lines = list(po_lines)
        for row_id in range(1, count + 1):
            available = [line for line in candidate_lines if remaining[line["id"]] > 0.01]
            if not available:
                break
            line = available[(row_id - 1) % len(available)]
            rem = remaining[line["id"]]
            split_line_count = max(count - len(po_lines), 0)
            if row_id <= len(po_lines) and row_id <= split_line_count:
                qty = round(max(1.0, rem * rng.uniform(0.45, 0.75)), 2)
            elif row_id <= len(po_lines):
                qty = rem
            else:
                qty = rem
            qty = round(min(qty, rem), 2)
            if qty <= 0:
                continue
            remaining[line["id"]] = round(rem - qty, 2)
            scheduled_date = self._v2_add_days(line["order_date"], rng.randint(5, 35))
            rows.append(
                {
                    "id": row_id,
                    "purchase_order_line_id": line["id"],
                    "scheduled_delivery_date": scheduled_date,
                    "scheduled_quantity": qty,
                    "schedule_status": "Scheduled",
                    "purchase_order_id": line["purchase_order_id"],
                    "component_id": line["component_id"],
                    "order_date": line["order_date"],
                    "expected_delivery_date": line["expected_delivery_date"],
                    "supplier_id": line["supplier_id"],
                    "plant_id": line["plant_id"],
                }
            )
        return rows

    def _v2_shipment_headers(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        po_headers = records["purchase_order_header"]
        try:
            carriers = self.name_generator.generate_carrier_names(40, plan.domain_profile, seed=rng.randint(1, 999999))
        except NameGenerationError:
            carriers = [f"US Regional Logistics {i}" for i in range(40)]
        rows = []
        for row_id in range(1, count + 1):
            po = po_headers[(row_id - 1) % len(po_headers)]
            delay = rng.randint(4, 12) if row_id % 9 == 0 else 0
            ship_date = self._v2_add_days(po["order_date"], rng.randint(8, 42) + delay)
            rows.append(
                {
                    "id": row_id,
                    "purchase_order_id": po["id"],
                    "supplier_id": po["supplier_id"],
                    "shipment_date": ship_date,
                    "carrier_name": carriers[(row_id - 1) % len(carriers)],
                    "tracking_number": f"V2TRK{row_id:08d}",
                    "shipment_status": "Shipped",
                    "order_date": po["order_date"],
                    "expected_delivery_date": po["expected_delivery_date"],
                    "plant_id": po["plant_id"],
                }
            )
        return rows

    def _v2_shipment_lines(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        shipments = records["shipment_header"]
        schedules = [s for s in records["po_schedule"] if s["purchase_order_id"] <= len(shipments)]
        remaining_schedule = {schedule["id"]: float(schedule["scheduled_quantity"]) for schedule in schedules}
        po_lines_by_id = {line["id"]: line for line in records["purchase_order_line"]}
        remaining_po = {line["id"]: float(line["ordered_quantity"]) for line in records["purchase_order_line"]}
        rows = []
        schedule_index = 0
        for row_id in range(1, count + 1):
            while schedule_index < len(schedules) and (
                remaining_schedule.get(schedules[schedule_index]["id"], 0.0) <= 0.0001
                or remaining_po.get(schedules[schedule_index]["purchase_order_line_id"], 0.0) <= 0.0001
            ):
                schedule_index += 1
            if schedule_index >= len(schedules):
                break
            schedule = schedules[schedule_index]
            schedule_index += 1
            shipment = shipments[(schedule["purchase_order_id"] - 1) % len(shipments)]
            multiplier = rng.uniform(0.45, 0.85) if row_id % 5 == 0 else rng.uniform(0.9, 1.0)
            schedule_remaining = remaining_schedule[schedule["id"]]
            po_remaining = remaining_po[schedule["purchase_order_line_id"]]
            max_shippable = min(schedule_remaining, po_remaining)
            shipped = round(max(0.01, max_shippable * multiplier), 2)
            shipped = min(shipped, max_shippable)
            if shipped <= 0:
                continue
            remaining_schedule[schedule["id"]] = round(schedule_remaining - shipped, 2)
            remaining_po[schedule["purchase_order_line_id"]] = round(po_remaining - shipped, 2)
            rows.append(
                {
                    "id": row_id,
                    "shipment_id": shipment["id"],
                    "po_schedule_id": schedule["id"],
                    "purchase_order_line_id": schedule["purchase_order_line_id"],
                    "component_id": schedule["component_id"],
                    "shipped_quantity": shipped,
                    "scheduled_quantity": schedule["scheduled_quantity"],
                    "shipment_date": shipment["shipment_date"],
                    "purchase_order_id": schedule["purchase_order_id"],
                    "supplier_id": shipment["supplier_id"],
                    "plant_id": shipment["plant_id"],
                    "ordered_quantity": po_lines_by_id[schedule["purchase_order_line_id"]]["ordered_quantity"],
                }
            )
        return rows

    def _v2_goods_receipt_headers(self, table, plan, master_dataframes, records, rng):
        count = self._target_rows(table, plan)
        shipment_ids_with_lines = {line["shipment_id"] for line in records.get("shipment_line", [])}
        shipments = [shipment for shipment in records["shipment_header"] if shipment["id"] in shipment_ids_with_lines] or records["shipment_header"]
        warehouses = master_dataframes["Warehouse"].to_dict("records")
        rows = []
        for row_id in range(1, count + 1):
            shipment = shipments[(row_id - 1) % len(shipments)]
            matching = [w for w in warehouses if w["PlantID"] == shipment["plant_id"]] or warehouses
            warehouse = matching[(row_id - 1) % len(matching)]
            receipt_date = self._v2_add_days(shipment["shipment_date"], rng.randint(1, 6))
            rows.append(
                {
                    "id": row_id,
                    "shipment_id": shipment["id"],
                    "plant_id": shipment["plant_id"],
                    "warehouse_id": warehouse["WarehouseID"],
                    "receipt_date": receipt_date,
                    "receipt_status": "Received",
                    "shipment_date": shipment["shipment_date"],
                    "purchase_order_id": shipment["purchase_order_id"],
                    "supplier_id": shipment["supplier_id"],
                }
            )
        return rows

    def _v2_goods_receipt_lines(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        receipts = records["goods_receipt_header"]
        shipment_lines = records["shipment_line"]
        receipt_by_shipment: dict[int, dict[str, Any]] = {}
        for receipt in receipts:
            receipt_by_shipment.setdefault(receipt["shipment_id"], receipt)
        remaining_shipment = {line["id"]: float(line["shipped_quantity"]) for line in shipment_lines}
        po_lines_by_id = {line["id"]: line for line in records["purchase_order_line"]}
        remaining_po = {line["id"]: float(line["ordered_quantity"]) for line in records["purchase_order_line"]}
        rows = []
        shipment_line_index = 0
        for row_id in range(1, count + 1):
            while shipment_line_index < len(shipment_lines) and (
                shipment_lines[shipment_line_index]["shipment_id"] not in receipt_by_shipment
                or remaining_shipment.get(shipment_lines[shipment_line_index]["id"], 0.0) <= 0.0001
                or remaining_po.get(shipment_lines[shipment_line_index]["purchase_order_line_id"], 0.0) <= 0.0001
            ):
                shipment_line_index += 1
            if shipment_line_index >= len(shipment_lines):
                break
            shipment_line = shipment_lines[shipment_line_index]
            shipment_line_index += 1
            receipt = receipt_by_shipment[shipment_line["shipment_id"]]
            shipment_remaining = remaining_shipment[shipment_line["id"]]
            po_remaining = remaining_po[shipment_line["purchase_order_line_id"]]
            max_receivable = min(shipment_remaining, po_remaining)
            short = round(max_receivable * rng.uniform(0.04, 0.2), 2) if row_id % 7 == 0 else 0.0
            received = round(max(max_receivable - short, 0), 2)
            if received <= 0:
                continue
            remaining_shipment[shipment_line["id"]] = round(shipment_remaining - received, 2)
            remaining_po[shipment_line["purchase_order_line_id"]] = round(po_remaining - received, 2)
            damaged = round(received * rng.uniform(0.01, 0.08), 2) if row_id % 11 == 0 and received > 0 else 0.0
            rows.append(
                {
                    "id": row_id,
                    "goods_receipt_id": receipt["id"],
                    "shipment_line_id": shipment_line["id"],
                    "purchase_order_line_id": shipment_line["purchase_order_line_id"],
                    "component_id": shipment_line["component_id"],
                    "shipped_quantity": shipment_line["shipped_quantity"],
                    "received_quantity": received,
                    "damaged_quantity": damaged,
                    "short_quantity": round(shipment_line["shipped_quantity"] - received, 2),
                    "receipt_date": receipt["receipt_date"],
                    "plant_id": receipt["plant_id"],
                    "warehouse_id": receipt["warehouse_id"],
                    "purchase_order_id": receipt["purchase_order_id"],
                    "supplier_id": receipt["supplier_id"],
                    "ordered_quantity": po_lines_by_id[shipment_line["purchase_order_line_id"]]["ordered_quantity"],
                }
            )
        return rows

    def _v2_incoming_inspections(self, table, plan, records, rng, faker):
        count = self._target_rows(table, plan)
        receipt_lines = records["goods_receipt_line"]
        rows = []
        for row_id in range(1, count + 1):
            line = receipt_lines[(row_id - 1) % len(receipt_lines)]
            inspection_date = self._v2_add_days(line["receipt_date"], rng.randint(0, 3))
            rows.append(
                {
                    "id": row_id,
                    "goods_receipt_line_id": line["id"],
                    "inspection_date": inspection_date,
                    "inspector_name": faker.name(),
                    "inspection_status": "Pending",
                    "received_quantity": line["received_quantity"],
                    "component_id": line["component_id"],
                    "plant_id": line["plant_id"],
                    "warehouse_id": line["warehouse_id"],
                    "receipt_date": line["receipt_date"],
                    "goods_receipt_id": line["goods_receipt_id"],
                    "goods_receipt_line_id": line["id"],
                    "purchase_order_line_id": line["purchase_order_line_id"],
                    "purchase_order_id": line["purchase_order_id"],
                    "supplier_id": line["supplier_id"],
                }
            )
        return rows

    def _v2_inspection_results(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        inspections = records["incoming_inspection"]
        try:
            tests = self.name_generator.generate_inspection_test_names(40, plan.domain_profile, seed=rng.randint(1, 999999))
        except NameGenerationError:
            tests = ["Electrical Test", "Dimensional Inspection", "Visual Inspection", "Functional Test"]
        receipt_lines_by_id = {row["id"]: row for row in records["goods_receipt_line"]}
        po_lines_by_id = {row["id"]: row for row in records["purchase_order_line"]}
        remaining_receipt = {line["id"]: float(line["received_quantity"]) for line in records["goods_receipt_line"]}
        remaining_po = {line["id"]: float(line["ordered_quantity"]) for line in records["purchase_order_line"]}
        rows = []
        inspection_index = 0
        for row_id in range(1, count + 1):
            while inspection_index < len(inspections) and (
                remaining_receipt.get(inspections[inspection_index]["goods_receipt_line_id"], 0.0) <= 0.0001
                or remaining_po.get(inspections[inspection_index]["purchase_order_line_id"], 0.0) <= 0.0001
            ):
                inspection_index += 1
            if inspection_index >= len(inspections):
                break
            inspection = inspections[inspection_index]
            inspection_index += 1
            receipt_remaining = remaining_receipt[inspection["goods_receipt_line_id"]]
            po_remaining = remaining_po[inspection["purchase_order_line_id"]]
            inspected = round(max(min(float(inspection["received_quantity"]), receipt_remaining, po_remaining), 0), 2)
            if row_id % 19 == 0 and inspected > 0:
                accepted = 0.0
                rejected = inspected
            elif row_id % 6 == 0 and inspected > 0:
                rejected = round(max(0.01, inspected * rng.uniform(0.02, 0.16)), 2)
                accepted = round(inspected - rejected, 2)
            else:
                rejected = 0.0
                accepted = inspected
            remaining_receipt[inspection["goods_receipt_line_id"]] = round(receipt_remaining - inspected, 2)
            remaining_po[inspection["purchase_order_line_id"]] = round(po_remaining - accepted, 2)
            status = "Failed" if rejected > 0 and accepted == 0 else "PartiallyRejected" if rejected > 0 else "Passed"
            reason = self._choice(V2_REJECTION_REASONS, rng) if rejected > 0 else "Not Applicable"
            rate = None if inspected == 0 else round((rejected / inspected) * 100, 2)
            receipt_line = receipt_lines_by_id[inspection["goods_receipt_line_id"]]
            po_line = po_lines_by_id[inspection["purchase_order_line_id"]]
            rows.append(
                {
                    "id": row_id,
                    "inspection_id": inspection["id"],
                    "test_name": tests[(row_id - 1) % len(tests)],
                    "inspected_quantity": inspected,
                    "accepted_quantity": accepted,
                    "rejected_quantity": rejected,
                    "rejection_rate_pct": rate,
                    "rejection_reason": reason,
                    "result_status": status,
                    "inspection_date": inspection["inspection_date"],
                    "component_id": inspection["component_id"],
                    "plant_id": inspection["plant_id"],
                    "warehouse_id": inspection["warehouse_id"],
                    "goods_receipt_id": inspection["goods_receipt_id"],
                    "goods_receipt_line_id": inspection["goods_receipt_line_id"],
                    "purchase_order_line_id": inspection["purchase_order_line_id"],
                    "purchase_order_id": inspection["purchase_order_id"],
                    "supplier_id": inspection["supplier_id"],
                    "received_quantity": receipt_line["received_quantity"],
                    "ordered_quantity": po_line["ordered_quantity"],
                }
            )
        return rows

    def _v2_inventory_transactions(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        results = [row for row in records["inspection_result"] if row["accepted_quantity"] > 0]
        inspections_by_id = {row["id"]: row for row in records["incoming_inspection"]}
        receipt_lines_by_id = {row["id"]: row for row in records["goods_receipt_line"]}
        po_lines_by_id = {row["id"]: row for row in records["purchase_order_line"]}
        po_headers_by_id = {row["id"]: row for row in records["purchase_order_header"]}
        statuses = ["Posted", "QualityAccepted", "ReceivedToInventory"]
        remaining_result = {row["id"]: float(row["accepted_quantity"]) for row in results}
        remaining_po = {line["id"]: float(line["ordered_quantity"]) for line in records["purchase_order_line"]}
        rows = []
        result_index = 0
        for row_id in range(1, count + 1):
            while result_index < len(results) and (
                remaining_result.get(results[result_index]["id"], 0.0) <= 0.0001
                or remaining_po.get(results[result_index]["purchase_order_line_id"], 0.0) <= 0.0001
            ):
                result_index += 1
            if result_index >= len(results):
                break
            result = results[result_index]
            result_index += 1
            inspection = inspections_by_id[result["inspection_id"]]
            receipt_line = receipt_lines_by_id[inspection["goods_receipt_line_id"]]
            po_line = po_lines_by_id[receipt_line["purchase_order_line_id"]]
            po_header = po_headers_by_id[po_line["purchase_order_id"]]
            result_remaining = remaining_result[result["id"]]
            po_remaining = remaining_po[po_line["id"]]
            transaction_quantity = round(min(float(result["accepted_quantity"]), result_remaining, po_remaining), 2)
            if transaction_quantity <= 0:
                continue
            remaining_result[result["id"]] = round(result_remaining - transaction_quantity, 2)
            remaining_po[po_line["id"]] = round(po_remaining - transaction_quantity, 2)
            unit_price = round(float(po_line["unit_price"]), 2)
            inventory_value = self._v2_multiply_money(transaction_quantity, unit_price)
            rows.append(
                {
                    "id": row_id,
                    "inspection_result_id": result["id"],
                    "goods_receipt_line_id": receipt_line["id"],
                    "purchase_order_line_id": po_line["id"],
                    "supplier_id": po_header["supplier_id"],
                    "component_id": receipt_line["component_id"],
                    "plant_id": receipt_line["plant_id"],
                    "warehouse_id": receipt_line["warehouse_id"],
                    "transaction_date": self._v2_add_days(result["inspection_date"], rng.randint(0, 2)),
                    "transaction_type": "StockIn",
                    "transaction_quantity": transaction_quantity,
                    "unit_price": unit_price,
                    "inventory_value": inventory_value,
                    "reference_document": f"PO-{po_line['purchase_order_id']:06d}-GRN-{receipt_line['goods_receipt_id']:06d}",
                    "inventory_status": statuses[(row_id - 1) % len(statuses)],
                    "inspection_date": result["inspection_date"],
                    "inspection_id": result["inspection_id"],
                    "goods_receipt_id": receipt_line["goods_receipt_id"],
                }
            )
        return rows

    def _v2_inventory(self, table, plan, records, rng):
        transactions = pd.DataFrame(records["inventory_transaction"])
        if transactions.empty:
            return []

        grouped = (
            transactions.groupby(["component_id", "plant_id", "warehouse_id"], as_index=False)
            .agg(
                on_hand_quantity=("transaction_quantity", "sum"),
                on_hand_value=("inventory_value", "sum"),
                last_transaction_date=("transaction_date", "max"),
            )
            .sort_values(["plant_id", "warehouse_id", "component_id"])
            .reset_index(drop=True)
        )

        rows = []
        for row_id, row in enumerate(grouped.itertuples(index=False), start=1):
            on_hand = round(float(row.on_hand_quantity), 2)
            on_hand_value = self._v2_round_money(float(row.on_hand_value))
            reserved = self._v2_reserved_quantity(on_hand, row_id, rng)
            available = round(on_hand - reserved, 2)
            average_unit_cost = on_hand_value / on_hand if on_hand > 0 else 0.0
            available_value = self._v2_round_money(available * average_unit_cost)
            rows.append(
                {
                    "id": row_id,
                    "component_id": int(row.component_id),
                    "plant_id": int(row.plant_id),
                    "warehouse_id": int(row.warehouse_id),
                    "on_hand_quantity": on_hand,
                    "reserved_quantity": reserved,
                    "available_quantity": available,
                    "on_hand_value": on_hand_value,
                    "available_value": available_value,
                    "last_transaction_date": row.last_transaction_date,
                    "last_updated_date": row.last_transaction_date,
                    "inventory_status": self._v2_inventory_status(on_hand, available),
                }
            )
        return rows

    def _v2_reserved_quantity(self, on_hand_quantity: float, row_id: int, rng: random.Random) -> float:
        if on_hand_quantity <= 0:
            return 0.0
        if row_id % 31 == 0:
            return round(on_hand_quantity, 2)
        if row_id % 13 == 0:
            return round(min(on_hand_quantity, on_hand_quantity * rng.uniform(0.90, 0.96)), 2)
        if row_id % 7 == 0:
            return 0.0
        return round(min(on_hand_quantity, on_hand_quantity * rng.uniform(0.0, 0.20)), 2)

    def _v2_inventory_status(self, on_hand_quantity: float, available_quantity: float) -> str:
        if on_hand_quantity <= 0:
            return "OutOfStock"
        if available_quantity <= 0:
            return "Hold"
        if available_quantity <= on_hand_quantity * 0.10:
            return "LowStock"
        return "Available"

    def _v2_round_money(self, value: float) -> float:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))

    def _v2_multiply_money(self, left: float, right: float) -> float:
        value = Decimal(str(left)) * Decimal(str(right))
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))

    def _v2_supplier_invoices(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        receipts = records["goods_receipt_header"]
        po_lines = records["purchase_order_line"]
        tax_min, tax_max = self._column_min_max(table, "TaxAmount", 0.0, 5000.0)
        freight_min, freight_max = self._column_min_max(table, "FreightAmount", 0.0, 3000.0)
        line_price = {row["id"]: row["unit_price"] for row in po_lines}
        receipt_lines_by_header: dict[int, list[dict[str, Any]]] = {}
        for line in records["goods_receipt_line"]:
            receipt_lines_by_header.setdefault(line["goods_receipt_id"], []).append(line)
        rows = []
        for row_id in range(1, count + 1):
            receipt = receipts[(row_id - 1) % len(receipts)]
            receipt_lines = receipt_lines_by_header.get(receipt["id"], [])
            invoice_amount = round(sum(line["received_quantity"] * line_price.get(line["purchase_order_line_id"], 1.0) for line in receipt_lines), 2)
            invoice_amount = max(invoice_amount, 1.0)
            tax = round(min(max(invoice_amount * rng.uniform(0.02, 0.08), tax_min), tax_max), 2)
            freight = round(min(max(rng.uniform(40, 800), freight_min), freight_max), 2)
            invoice_date = self._v2_add_days(receipt["receipt_date"], rng.randint(1, 12))
            total = round(invoice_amount + tax + freight, 2)
            rows.append(
                {
                    "id": row_id,
                    "purchase_order_id": receipt["purchase_order_id"],
                    "supplier_id": receipt["supplier_id"],
                    "goods_receipt_id": receipt["id"],
                    "invoice_date": invoice_date,
                    "due_date": self._v2_add_days(invoice_date, self._choice([15, 30, 45, 60], rng)),
                    "invoice_status": "Submitted",
                    "invoice_amount": invoice_amount,
                    "tax_amount": tax,
                    "freight_amount": freight,
                    "total_invoice_amount": total,
                    "currency_code": "USD",
                    "receipt_date": receipt["receipt_date"],
                }
            )
        return rows

    def _v2_payment_transactions(self, table, plan, records, rng):
        count = self._target_rows(table, plan)
        invoices = records["supplier_invoice"]
        payment_min, payment_max = self._column_min_max(table, "PaymentAmount", 0.0, 1000000.0)
        methods = ["ACH", "Wire Transfer", "Check", "Credit Transfer"]
        rows = []
        for row_id in range(1, count + 1):
            invoice = invoices[(row_id - 1) % len(invoices)]
            max_payable = min(float(invoice["total_invoice_amount"]), payment_max)
            roll = rng.random()
            if roll < 0.1:
                amount = payment_min
                status = "Pending"
            elif roll < 0.32:
                amount = round(min(float(invoice["total_invoice_amount"]) * rng.uniform(0.25, 0.85), max_payable), 2)
                if amount >= float(invoice["total_invoice_amount"]) and float(invoice["total_invoice_amount"]) > payment_max:
                    amount = payment_max
                status = "PartiallyPaid"
            elif roll < 0.35:
                amount = payment_min
                status = "Failed"
            else:
                amount = round(max_payable, 2)
                status = "Paid" if amount >= float(invoice["total_invoice_amount"]) else "PartiallyPaid"
            rows.append(
                {
                    "id": row_id,
                    "supplier_invoice_id": invoice["id"],
                    "supplier_id": invoice["supplier_id"],
                    "payment_date": self._v2_add_days(invoice["invoice_date"], rng.randint(1, 45)),
                    "payment_amount": amount,
                    "payment_method": methods[(row_id - 1) % len(methods)],
                    "payment_status": status,
                    "currency_code": "USD",
                    "invoice_date": invoice["invoice_date"],
                    "total_invoice_amount": invoice["total_invoice_amount"],
                }
            )
        return rows

    def _refresh_mutated_context_tables(
        self,
        tables_by_role: dict[str, TableContract],
        context: ProcurementGenerationContext,
        dataframes: dict[str, pd.DataFrame],
        report: ValidationReport,
    ) -> None:
        """Rebuild headers that are updated after their child rows are generated."""

        for role in ("purchase_order_header", "quality_inspection_header"):
            table = tables_by_role.get(role)
            if table is None:
                continue
            records = getattr(context, self._context_attr_for_role(role))
            dataframes[table.table_name] = self._records_to_dataframe(table, records, report)

    def _refresh_v2_statuses(
        self,
        records: dict[str, list[dict[str, Any]]],
        dataframes: dict[str, pd.DataFrame],
        table_by_role: dict[str, TableContract],
        report: ValidationReport,
    ) -> None:
        tolerance = 0.0001

        scheduled_by_po_line: dict[int, float] = {}
        shipped_by_schedule: dict[int, float] = {}
        shipped_by_po_line: dict[int, float] = {}
        received_by_shipment_line: dict[int, float] = {}
        received_by_po_line: dict[int, float] = {}
        accepted_by_po_line: dict[int, float] = {}
        stock_in_by_po_line: dict[int, float] = {}

        for schedule in records.get("po_schedule", []):
            scheduled_by_po_line[schedule["purchase_order_line_id"]] = scheduled_by_po_line.get(schedule["purchase_order_line_id"], 0.0) + float(schedule["scheduled_quantity"])
        for line in records.get("shipment_line", []):
            shipped_by_schedule[line["po_schedule_id"]] = shipped_by_schedule.get(line["po_schedule_id"], 0.0) + float(line["shipped_quantity"])
            shipped_by_po_line[line["purchase_order_line_id"]] = shipped_by_po_line.get(line["purchase_order_line_id"], 0.0) + float(line["shipped_quantity"])
        for line in records.get("goods_receipt_line", []):
            received_by_shipment_line[line["shipment_line_id"]] = received_by_shipment_line.get(line["shipment_line_id"], 0.0) + float(line["received_quantity"])
            received_by_po_line[line["purchase_order_line_id"]] = received_by_po_line.get(line["purchase_order_line_id"], 0.0) + float(line["received_quantity"])
        for result in records.get("inspection_result", []):
            accepted_by_po_line[result["purchase_order_line_id"]] = accepted_by_po_line.get(result["purchase_order_line_id"], 0.0) + float(result["accepted_quantity"])
        for txn in records.get("inventory_transaction", []):
            stock_in_by_po_line[txn["purchase_order_line_id"]] = stock_in_by_po_line.get(txn["purchase_order_line_id"], 0.0) + float(txn["transaction_quantity"])

        for schedule in records.get("po_schedule", []):
            shipped = shipped_by_schedule.get(schedule["id"], 0.0)
            scheduled = float(schedule["scheduled_quantity"])
            if shipped <= tolerance:
                schedule["schedule_status"] = "Scheduled" if schedule["id"] % 3 else "Planned"
            elif shipped + tolerance < scheduled:
                schedule["schedule_status"] = "PartiallyShipped"
            elif schedule.get("scheduled_delivery_date") and any(
                line["po_schedule_id"] == schedule["id"] and line.get("shipment_date") and line["shipment_date"] > schedule["scheduled_delivery_date"]
                for line in records.get("shipment_line", [])
            ):
                schedule["schedule_status"] = "Delayed"
            else:
                schedule["schedule_status"] = "Shipped"

        receipt_by_shipment: dict[int, list[dict[str, Any]]] = {}
        for receipt in records.get("goods_receipt_header", []):
            receipt_by_shipment.setdefault(receipt["shipment_id"], []).append(receipt)
        shipped_by_shipment: dict[int, float] = {}
        received_by_shipment: dict[int, float] = {}
        for line in records.get("shipment_line", []):
            shipped_by_shipment[line["shipment_id"]] = shipped_by_shipment.get(line["shipment_id"], 0.0) + float(line["shipped_quantity"])
        for line in records.get("goods_receipt_line", []):
            receipt = next((row for row in records.get("goods_receipt_header", []) if row["id"] == line["goods_receipt_id"]), None)
            if receipt is not None:
                received_by_shipment[receipt["shipment_id"]] = received_by_shipment.get(receipt["shipment_id"], 0.0) + float(line["received_quantity"])
        for shipment in records.get("shipment_header", []):
            shipped = shipped_by_shipment.get(shipment["id"], 0.0)
            received = received_by_shipment.get(shipment["id"], 0.0)
            if shipped <= tolerance:
                shipment["shipment_status"] = "Shipped"
            elif received <= tolerance:
                shipment["shipment_status"] = "Delayed" if shipment["shipment_date"] > shipment["expected_delivery_date"] else ("InTransit" if shipment["id"] % 2 else "Shipped")
            elif received + tolerance < shipped:
                shipment["shipment_status"] = "PartiallyDelivered"
            else:
                shipment["shipment_status"] = "Delivered"

        grl_by_receipt: dict[int, list[dict[str, Any]]] = {}
        for line in records.get("goods_receipt_line", []):
            grl_by_receipt.setdefault(line["goods_receipt_id"], []).append(line)
        for receipt in records.get("goods_receipt_header", []):
            lines = grl_by_receipt.get(receipt["id"], [])
            if any(line["damaged_quantity"] > 0 for line in lines):
                receipt["receipt_status"] = "Damaged"
            elif any(line["short_quantity"] > 0 for line in lines):
                receipt["receipt_status"] = "ShortReceived"
            elif lines and sum(float(line["received_quantity"]) for line in lines) + tolerance < sum(float(line["shipped_quantity"]) for line in lines):
                receipt["receipt_status"] = "Partial"
            else:
                receipt["receipt_status"] = "Closed" if receipt["id"] % 5 == 0 else "Received"

        result_by_inspection = {result["inspection_id"]: result for result in records.get("inspection_result", [])}
        for result in records.get("inspection_result", []):
            if result.get("rejected_quantity", 0) > 0 and result.get("rejection_reason") in {None, "", "Not Applicable"}:
                result["rejection_reason"] = V2_REJECTION_REASONS[(result["id"] - 1) % len(V2_REJECTION_REASONS)]
        for inspection in records.get("incoming_inspection", []):
            result = result_by_inspection.get(inspection["id"])
            if result is None:
                inspection["inspection_status"] = "Pending"
            elif result["result_status"] == "Passed":
                inspection["inspection_status"] = "Passed"
            elif result["result_status"] == "Failed":
                inspection["inspection_status"] = "Failed"
            else:
                inspection["inspection_status"] = "PartiallyRejected"

        awarded_by_quotation: dict[int, int] = {}
        for line in records.get("supplier_quotation_line", []):
            awarded = int(line.get("awarded_flag", 0) == 1)
            awarded_by_quotation[line["quotation_id"]] = awarded_by_quotation.get(line["quotation_id"], 0) + awarded
            line["line_status"] = "Awarded" if awarded else "Rejected"
        for quotation in records.get("supplier_quotation", []):
            if awarded_by_quotation.get(quotation["id"], 0) > 0:
                quotation["quotation_status"] = "Awarded"
            elif quotation["quotation_status"] == "Awarded":
                quotation["quotation_status"] = "Rejected"

        for line in records.get("purchase_order_line", []):
            ordered = float(line["ordered_quantity"])
            scheduled = scheduled_by_po_line.get(line["id"], 0.0)
            shipped = shipped_by_po_line.get(line["id"], 0.0)
            received = received_by_po_line.get(line["id"], 0.0)
            stock_in = stock_in_by_po_line.get(line["id"], 0.0)
            line["open_quantity"] = round(max(ordered - stock_in, 0.0), 2)
            if scheduled <= tolerance:
                line["line_status"] = "Open"
            elif shipped <= tolerance:
                line["line_status"] = "Scheduled"
            elif stock_in + tolerance >= ordered:
                line["line_status"] = "Closed"
            elif received > tolerance or stock_in > tolerance:
                line["line_status"] = "PartiallyReceived"
            else:
                line["line_status"] = "PartiallyShipped"

        po_lines_by_header: dict[int, list[dict[str, Any]]] = {}
        for line in records.get("purchase_order_line", []):
            po_lines_by_header.setdefault(line["purchase_order_id"], []).append(line)
        for po in records.get("purchase_order_header", []):
            lines = po_lines_by_header.get(po["id"], [])
            total_ordered = sum(float(line["ordered_quantity"]) for line in lines)
            total_scheduled = sum(scheduled_by_po_line.get(line["id"], 0.0) for line in lines)
            total_shipped = sum(shipped_by_po_line.get(line["id"], 0.0) for line in lines)
            total_received = sum(received_by_po_line.get(line["id"], 0.0) for line in lines)
            total_stock_in = sum(stock_in_by_po_line.get(line["id"], 0.0) for line in lines)
            if total_scheduled <= tolerance:
                po["po_status"] = "Approved" if po["id"] % 2 else "Sent"
            elif total_shipped <= tolerance:
                po["po_status"] = "Sent"
            elif total_stock_in + tolerance >= total_ordered and total_ordered > tolerance:
                po["po_status"] = "Closed"
            elif total_received > tolerance or total_stock_in > tolerance:
                po["po_status"] = "PartiallyReceived"
            else:
                po["po_status"] = "Sent"

        invoice_payments: dict[int, float] = {}
        for payment in records.get("payment_transaction", []):
            invoice_total = float(payment["total_invoice_amount"])
            amount = float(payment["payment_amount"])
            if amount <= tolerance:
                payment["payment_status"] = "Failed" if payment["id"] % 5 == 0 else "Pending"
            elif amount + 0.01 < invoice_total:
                payment["payment_status"] = "PartiallyPaid"
            else:
                payment["payment_status"] = "Paid"
            invoice_payments[payment["supplier_invoice_id"]] = invoice_payments.get(payment["supplier_invoice_id"], 0.0) + amount
        for invoice in records.get("supplier_invoice", []):
            total_paid = invoice_payments.get(invoice["id"], 0.0)
            invoice_total = float(invoice["total_invoice_amount"])
            if total_paid <= tolerance:
                invoice["invoice_status"] = "Submitted" if invoice["id"] % 2 else "Approved"
            elif total_paid + 0.01 < invoice_total:
                invoice["invoice_status"] = "PartiallyPaid"
            else:
                invoice["invoice_status"] = "Paid"

        for role in (
            "po_schedule",
            "supplier_quotation",
            "supplier_quotation_line",
            "shipment_header",
            "goods_receipt_header",
            "incoming_inspection",
            "inspection_result",
            "purchase_order_header",
            "purchase_order_line",
            "supplier_invoice",
            "payment_transaction",
        ):
            table = table_by_role.get(role)
            if table is not None and role in records:
                dataframe = self._records_to_dataframe(table, records[role], report)
                if role == "inspection_result" and {"RejectedQuantity", "RejectionReason"}.issubset(dataframe.columns):
                    invalid_reason_mask = (dataframe["RejectedQuantity"] > 0) & dataframe["RejectionReason"].fillna("").isin(["", "Not Applicable"])
                    replacement_index = 0
                    for row_index in dataframe.index[invalid_reason_mask]:
                        dataframe.at[row_index, "RejectionReason"] = V2_REJECTION_REASONS[replacement_index % len(V2_REJECTION_REASONS)]
                        replacement_index += 1
                dataframes[table.table_name] = dataframe

    def validate_generated_transaction_data(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        master_dataframes: dict[str, pd.DataFrame],
        report: ValidationReport,
    ) -> None:
        """Run Phase 9 basic transaction validation."""

        all_dataframes = {**master_dataframes, **dataframes}
        for table in self.get_transaction_tables(schema):
            dataframe = dataframes.get(table.table_name)
            if dataframe is None:
                report.add_error(
                    table_name=table.table_name,
                    message="Transaction table DataFrame was not generated.",
                    suggested_fix="Generate one DataFrame for each transaction TableRole present in metadata.",
                )
                continue
            target_rows = self._target_rows(table, None)
            if table.table_role != "inventory_balance" and len(dataframe) != target_rows:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Generated row count {len(dataframe)} does not match target {target_rows}.",
                    suggested_fix="Generate exactly TargetRows for transaction tables except natural inventory balance grouping.",
                )
            if table.table_role == "inventory_balance" and len(dataframe) != target_rows:
                report.add_warning(
                    table_name=table.table_name,
                    message=f"InventoryBalance generated {len(dataframe)} grouped rows; metadata target is {target_rows}.",
                    suggested_fix="This is acceptable when natural inventory groups differ from TargetRows.",
                )
            for column in table.columns:
                if column.column_name not in dataframe.columns:
                    report.add_error(
                        table_name=table.table_name,
                        column_name=column.column_name,
                        message="Metadata column missing from generated transaction DataFrame.",
                        suggested_fix="Generate every metadata column.",
                    )
                    continue
                series = dataframe[column.column_name]
                if column.key_type == "PK":
                    if series.isna().any() or not series.is_unique:
                        report.add_error(
                            table_name=table.table_name,
                            column_name=column.column_name,
                            message="PK must be unique and non-null.",
                            suggested_fix="Generate unique non-null sequence IDs.",
                        )
                if column.key_type == "FK":
                    self._validate_fk(table, column, series, all_dataframes, report)
                if column.nullable == "No" and series.isna().any():
                    report.add_error(
                        table_name=table.table_name,
                        column_name=column.column_name,
                        message="Nullable = No column contains null values.",
                        suggested_fix="Populate required transaction columns.",
                    )
                if column.allowed_values:
                    invalid = sorted(set(series.dropna()) - set(column.allowed_values))
                    if invalid:
                        report.add_error(
                            table_name=table.table_name,
                            column_name=column.column_name,
                            message=f"Generated values outside AllowedValues: {', '.join(map(str, invalid))}.",
                            suggested_fix="Use only metadata AllowedValues.",
                        )
                if "name" in column.column_name.lower() or "description" in column.column_name.lower():
                    if any(ARTIFICIAL_NUMERIC_SUFFIX_PATTERN.search(str(value)) for value in series.dropna()):
                        report.add_error(
                            table_name=table.table_name,
                            column_name=column.column_name,
                            message="Generated text contains artificial numeric suffix.",
                            suggested_fix="Use meaningful references instead of numeric suffixes.",
                        )

        self._validate_receipt_warehouse_plant_alignment(dataframes, master_dataframes, schema, report)
        self._validate_business_invariants(dataframes, schema, report)

    def _generate_purchase_requisition_headers(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        master_by_role: dict[str, pd.DataFrame],
        context: ProcurementGenerationContext,
        rng: random.Random,
        faker: Faker,
        report: ValidationReport,
    ) -> list[dict[str, Any]]:
        count = self._target_rows(table, plan)
        plants = master_by_role.get("plant_dimension", pd.DataFrame())
        plant_ids = self._column_values(plants, "PlantID") or [None]
        records = []
        start_date = self._date_min(table) or date(2025, 1, 1)
        for row_id in range(1, count + 1):
            req_date = start_date + timedelta(days=rng.randint(0, 240))
            plant_id = plant_ids[(row_id - 1) % len(plant_ids)]
            records.append(
                {
                    "id": row_id,
                    "plant_id": plant_id,
                    "requisition_date": req_date,
                    "required_date": req_date + timedelta(days=rng.randint(7, 30)),
                    "priority": self._weighted_choice(["Low", "Medium", "High", "Urgent"], [10, 55, 28, 7], rng),
                    "status": "Approved",
                    "department": self._choice(["Production", "Maintenance", "Quality", "Procurement"], rng),
                    "description": "Material purchase request",
                    "requested_by": faker.name(),
                }
            )
        return records

    def _generate_purchase_requisition_lines(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        materials = master_by_role.get("material_dimension", pd.DataFrame())
        material_ids = self._column_values(materials, "RawMaterialID") or self._column_values(materials, "MaterialID") or [None]
        headers = context.requisition_headers
        records = []
        for row_id in range(1, count + 1):
            header = headers[(row_id - 1) % len(headers)]
            material_id = self._choice(material_ids, rng)
            requested_qty = rng.randint(20, 500)
            records.append(
                {
                    "id": row_id,
                    "requisition_id": header["id"],
                    "raw_material_id": material_id,
                    "requested_quantity": requested_qty,
                    "required_date": header["required_date"],
                    "line_status": "Approved",
                    "plant_id": header["plant_id"],
                    "requisition_date": header["requisition_date"],
                }
            )
        return records

    def _generate_purchase_order_headers(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        vendors = master_by_role.get("vendor_dimension", pd.DataFrame())
        vendor_ids = self._column_values(vendors, "VendorID") or [None]
        req_headers = context.requisition_headers
        records = []
        for row_id in range(1, count + 1):
            req = req_headers[(row_id - 1) % len(req_headers)]
            order_date = req["requisition_date"] + timedelta(days=rng.randint(0, 7))
            expected_date = order_date + timedelta(days=rng.randint(7, 21))
            records.append(
                {
                    "id": row_id,
                    "vendor_id": self._choice(vendor_ids, rng),
                    "plant_id": req["plant_id"],
                    "requisition_id": req["id"],
                    "order_date": order_date,
                    "expected_delivery_date": expected_date,
                    "status": "Sent",
                    "po_status": "Sent",
                    "total_amount": 0.0,
                }
            )
        return records

    def _generate_purchase_order_lines(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        po_headers = context.purchase_order_headers
        req_lines = context.requisition_lines
        records = []
        for row_id in range(1, count + 1):
            po = po_headers[(row_id - 1) % len(po_headers)]
            matching_req_lines = [line for line in req_lines if line["requisition_id"] == po["requisition_id"]]
            if not matching_req_lines:
                matching_req_lines = req_lines
            req_line = matching_req_lines[(row_id - 1) % len(matching_req_lines)]
            requested_qty = req_line["requested_quantity"]
            ordered_qty = max(1, int(requested_qty * rng.uniform(0.9, 1.05)))
            unit_price = round(rng.uniform(10.0, 250.0), 2)
            line_amount = round(ordered_qty * unit_price, 2)
            records.append(
                {
                    "id": row_id,
                    "purchase_order_id": po["id"],
                    "requisition_line_id": req_line["id"],
                    "raw_material_id": req_line["raw_material_id"],
                    "ordered_quantity": ordered_qty,
                    "unit_price": unit_price,
                    "line_amount": line_amount,
                    "open_quantity": ordered_qty,
                    "line_status": "Open",
                    "order_date": po["order_date"],
                    "expected_delivery_date": po["expected_delivery_date"],
                    "plant_id": po["plant_id"],
                    "vendor_id": po["vendor_id"],
                }
            )
        totals: dict[int, float] = {}
        for line in records:
            totals[line["purchase_order_id"]] = totals.get(line["purchase_order_id"], 0.0) + line["line_amount"]
        for po in po_headers:
            po["total_amount"] = round(totals.get(po["id"], 0.0), 2)
        return records

    def _generate_shipment_headers(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        po_headers = context.purchase_order_headers
        try:
            carriers = self.name_generator.generate_carrier_names(min(max(count, 1), 30), plan.domain_profile, seed=rng.randint(1, 999999))
        except NameGenerationError:
            carriers = self.name_generator.generate_faker_company_names(min(max(count, 1), 30), seed=rng.randint(1, 999999))
        records = []
        for row_id in range(1, count + 1):
            po = po_headers[(row_id - 1) % len(po_headers)]
            delay_extra = rng.randint(1, 8) if row_id % 5 == 0 else 0
            ship_date = po["order_date"] + timedelta(days=rng.randint(2, 20) + delay_extra)
            records.append(
                {
                    "id": row_id,
                    "purchase_order_id": po["id"],
                    "vendor_id": po["vendor_id"],
                    "shipment_date": ship_date,
                    "carrier_name": carriers[(row_id - 1) % len(carriers)],
                    "tracking_number": f"TRK{ship_date:%Y%m%d}{row_id:06d}",
                    "shipment_status": "Shipped",
                    "status": "Shipped",
                    "expected_delivery_date": po["expected_delivery_date"],
                }
            )
        return records

    def _generate_shipment_lines(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        shipment_headers = context.shipment_headers
        po_lines = context.purchase_order_lines
        shipped_so_far = {line["id"]: 0 for line in po_lines}
        records = []
        for row_id in range(1, count + 1):
            shipment = shipment_headers[(row_id - 1) % len(shipment_headers)]
            matching_po_lines = [line for line in po_lines if line["purchase_order_id"] == shipment["purchase_order_id"]]
            if not matching_po_lines:
                matching_po_lines = po_lines
            po_line = matching_po_lines[(row_id - 1) % len(matching_po_lines)]
            remaining = max(po_line["ordered_quantity"] - shipped_so_far[po_line["id"]], 1)
            if row_id % 4 == 0:
                shipped_qty = max(1, int(remaining * rng.uniform(0.35, 0.75)))
            else:
                shipped_qty = remaining
            shipped_qty = min(shipped_qty, remaining)
            shipped_so_far[po_line["id"]] += shipped_qty
            records.append(
                {
                    "id": row_id,
                    "shipment_id": shipment["id"],
                    "purchase_order_line_id": po_line["id"],
                    "raw_material_id": po_line["raw_material_id"],
                    "shipped_quantity": shipped_qty,
                    "ordered_quantity": po_line["ordered_quantity"],
                    "shipment_date": shipment["shipment_date"],
                    "purchase_order_id": po_line["purchase_order_id"],
                    "plant_id": po_line["plant_id"],
                    "vendor_id": po_line["vendor_id"],
                }
            )
        for line in po_lines:
            shipped = shipped_so_far[line["id"]]
            line["open_quantity"] = max(line["ordered_quantity"] - shipped, 0)
            line["line_status"] = "Closed" if line["open_quantity"] == 0 else "PartiallyReceived"
        return records

    def _generate_goods_receipt_headers(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        shipments = context.shipment_headers
        warehouses = master_by_role.get("warehouse_dimension", pd.DataFrame())
        warehouse_rows = warehouses.to_dict(orient="records") if not warehouses.empty else []
        records = []
        for row_id in range(1, count + 1):
            shipment = shipments[(row_id - 1) % len(shipments)]
            plant_id = self._plant_for_po(context, shipment.get("purchase_order_id"))
            matching_warehouses = [warehouse for warehouse in warehouse_rows if warehouse.get("PlantID") == plant_id]
            if not matching_warehouses and warehouse_rows:
                report.add_error(
                    table_name=table.table_name,
                    column_name="WarehouseID",
                    message=f"No generated warehouse belongs to PlantID {plant_id}.",
                    suggested_fix="Generate at least one Warehouse row for every receiving PlantID.",
                )
                matching_warehouses = warehouse_rows
            warehouse = matching_warehouses[(row_id - 1) % len(matching_warehouses)] if matching_warehouses else {}
            receipt_date = shipment["shipment_date"] + timedelta(days=rng.randint(1, 10))
            records.append(
                {
                    "id": row_id,
                    "shipment_id": shipment["id"],
                    "plant_id": plant_id,
                    "warehouse_id": warehouse.get("WarehouseID"),
                    "receipt_date": receipt_date,
                    "receipt_status": "Received",
                    "status": "Received",
                }
            )
        return records

    def _generate_goods_receipt_lines(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        receipt_headers = context.goods_receipt_headers
        shipment_lines = context.shipment_lines
        records = []
        for row_id in range(1, count + 1):
            receipt = receipt_headers[(row_id - 1) % len(receipt_headers)]
            matching_shipment_lines = [line for line in shipment_lines if line["shipment_id"] == receipt["shipment_id"]]
            if not matching_shipment_lines:
                matching_shipment_lines = shipment_lines
            shipment_line = matching_shipment_lines[(row_id - 1) % len(matching_shipment_lines)]
            short_qty = rng.randint(1, max(1, int(shipment_line["shipped_quantity"] * 0.2))) if row_id % 7 == 0 else 0
            received_qty = max(shipment_line["shipped_quantity"] - short_qty, 1)
            damaged_qty = rng.randint(0, max(0, int(received_qty * 0.05))) if row_id % 11 == 0 else 0
            records.append(
                {
                    "id": row_id,
                    "goods_receipt_id": receipt["id"],
                    "shipment_line_id": shipment_line["id"],
                    "purchase_order_line_id": shipment_line["purchase_order_line_id"],
                    "raw_material_id": shipment_line["raw_material_id"],
                    "received_quantity": received_qty,
                    "damaged_quantity": damaged_qty,
                    "short_quantity": shipment_line["shipped_quantity"] - received_qty,
                    "shipped_quantity": shipment_line["shipped_quantity"],
                    "receipt_date": receipt["receipt_date"],
                    "plant_id": receipt["plant_id"],
                    "warehouse_id": receipt["warehouse_id"],
                }
            )
        return records

    def _generate_quality_inspection_headers(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        receipt_lines = context.goods_receipt_lines
        records = []
        for row_id in range(1, count + 1):
            receipt_line = receipt_lines[(row_id - 1) % len(receipt_lines)]
            inspection_date = receipt_line["receipt_date"] + timedelta(days=rng.randint(0, 3))
            records.append(
                {
                    "id": row_id,
                    "goods_receipt_line_id": receipt_line["id"],
                    "goods_receipt_id": receipt_line["goods_receipt_id"],
                    "inspection_date": inspection_date,
                    "inspector_name": faker.name(),
                    "inspection_status": "Passed",
                    "status": "Passed",
                    "received_quantity": receipt_line["received_quantity"],
                    "raw_material_id": receipt_line["raw_material_id"],
                    "plant_id": receipt_line["plant_id"],
                    "warehouse_id": receipt_line["warehouse_id"],
                }
            )
        return records

    def _generate_quality_inspection_lines(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        inspections = context.quality_inspection_headers
        try:
            tests = self.name_generator.generate_inspection_test_names(
                min(max(count, 1), 30),
                plan.domain_profile,
                seed=rng.randint(1, 999999),
            )
        except NameGenerationError:
            tests = ["Visual Inspection", "Dimensional Check", "Certificate Review", "Packaging Check", "Functional Test"]
        rejection_reasons = ["Surface defect", "Dimension variance", "Packaging damage", "Supplier deviation", "Moisture issue"]
        records = []
        for row_id in range(1, count + 1):
            inspection = inspections[(row_id - 1) % len(inspections)]
            inspected_qty = max(int(inspection["received_quantity"]), 1)
            if row_id % 17 == 0:
                rejected_qty = max(1, int(inspected_qty * rng.uniform(0.35, 0.75)))
            elif row_id % 6 == 0:
                rejected_qty = max(1, int(inspected_qty * rng.uniform(0.02, 0.12)))
            else:
                rejected_qty = 0
            rejected_qty = min(rejected_qty, inspected_qty)
            accepted_qty = inspected_qty - rejected_qty
            status = "Failed" if accepted_qty == 0 else "PartiallyRejected" if rejected_qty else "Passed"
            inspection["inspection_status"] = status
            inspection["status"] = status
            records.append(
                {
                    "id": row_id,
                    "inspection_id": inspection["id"],
                    "test_name": tests[(row_id - 1) % len(tests)],
                    "inspected_quantity": inspected_qty,
                    "accepted_quantity": accepted_qty,
                    "rejected_quantity": rejected_qty,
                    "rejection_reason": self._choice(rejection_reasons, rng) if rejected_qty else "",
                    "result_status": status,
                    "status": status,
                    "inspection_date": inspection["inspection_date"],
                    "goods_receipt_line_id": inspection["goods_receipt_line_id"],
                    "raw_material_id": inspection["raw_material_id"],
                    "plant_id": inspection["plant_id"],
                    "warehouse_id": inspection["warehouse_id"],
                }
            )
        return records

    def _generate_inventory_transactions(self, table, plan, master_by_role, context, rng, faker, report):
        count = self._target_rows(table, plan)
        inspection_lines = [line for line in context.quality_inspection_lines if line["accepted_quantity"] > 0]
        if not inspection_lines:
            inspection_lines = context.quality_inspection_lines
        records = []
        for row_id in range(1, count + 1):
            inspection_line = inspection_lines[(row_id - 1) % len(inspection_lines)]
            transaction_date = inspection_line["inspection_date"] + timedelta(days=rng.randint(0, 2))
            records.append(
                {
                    "id": row_id,
                    "inspection_line_id": inspection_line["id"],
                    "goods_receipt_line_id": inspection_line["goods_receipt_line_id"],
                    "raw_material_id": inspection_line["raw_material_id"],
                    "plant_id": inspection_line["plant_id"],
                    "warehouse_id": inspection_line["warehouse_id"],
                    "transaction_date": transaction_date,
                    "transaction_type": "Receipt",
                    "transaction_quantity": inspection_line["accepted_quantity"],
                    "quantity": inspection_line["accepted_quantity"],
                    "reference_document": f"QI-{inspection_line['id']:06d}",
                }
            )
        return records

    def _generate_inventory_balances(self, table, plan, master_by_role, context, rng, faker, report):
        grouped: dict[tuple[Any, Any, Any], float] = {}
        latest_date: dict[tuple[Any, Any, Any], date] = {}
        for txn in context.inventory_transactions:
            key = (txn["raw_material_id"], txn["plant_id"], txn["warehouse_id"])
            grouped[key] = grouped.get(key, 0) + txn["transaction_quantity"]
            latest_date[key] = max(latest_date.get(key, txn["transaction_date"]), txn["transaction_date"])
        records = []
        for row_id, (key, quantity) in enumerate(grouped.items(), start=1):
            raw_material_id, plant_id, warehouse_id = key
            records.append(
                {
                    "id": row_id,
                    "raw_material_id": raw_material_id,
                    "plant_id": plant_id,
                    "warehouse_id": warehouse_id,
                    "on_hand_quantity": quantity,
                    "available_quantity": quantity,
                    "last_updated_date": latest_date[key],
                    "status": "Active",
                }
            )
        return records

    def _records_to_dataframe(self, table: TableContract, records: list[dict[str, Any]], report: ValidationReport) -> pd.DataFrame:
        data = {}
        for column in table.columns:
            data[column.column_name] = [
                self._value_for_column(table, column, record, index, report)
                for index, record in enumerate(records, start=1)
            ]
        return pd.DataFrame(data)

    def _value_for_column(self, table: TableContract, column: ColumnContract, record: dict[str, Any], index: int, report: ValidationReport) -> Any:
        if column.key_type == "PK" or column.generation_type == "sequence_id":
            return record.get("id", index)
        semantic_key = self._semantic_key(column.column_name)
        if semantic_key in record:
            value = record[semantic_key]
        elif column.generation_type == "calculated" and column.nullable == "Yes":
            return None
        elif column.generation_type == "calculated":
            value = self._fallback_calculated_value(column, record)
        elif column.generation_type in {"status", "category"}:
            value = self._status_or_category_value(column, record)
        elif column.generation_type == "faker_person":
            value = record.get("inspector_name") or record.get("requested_by")
        elif column.generation_type == "integer_range":
            value = record.get(semantic_key, 1)
        elif column.generation_type == "decimal_range":
            value = record.get(semantic_key, 1.0)
        elif column.generation_type in {"date_range", "date_offset"}:
            value = record.get(semantic_key)
        else:
            value = record.get(semantic_key)

        if value is None and column.nullable == "No":
            value = self._required_fallback_value(column, index)
        if column.allowed_values and str(value) not in {str(item) for item in column.allowed_values}:
            value = self._closest_allowed_value(value, column.allowed_values)
        return value

    def _semantic_key(self, column_name: str) -> str:
        name = column_name.lower().replace("_", "")
        mappings = [
            ("suppliercomponentid", "supplier_component_id"),
            ("supplierinvoiceid", "supplier_invoice_id"),
            ("supplierid", "supplier_id"),
            ("componentid", "component_id"),
            ("inspectionresultid", "inspection_result_id"),
            ("rfqlineid", "rfq_line_id"),
            ("rfqid", "rfq_id"),
            ("quotationlineid", "quotation_line_id"),
            ("quotationid", "quotation_id"),
            ("poscheduleid", "po_schedule_id"),
            ("requisitionlineid", "requisition_line_id"),
            ("requisitionid", "requisition_id"),
            ("purchaseorderlineid", "purchase_order_line_id"),
            ("purchaseorderid", "purchase_order_id"),
            ("shipmentlineid", "shipment_line_id"),
            ("shipmentid", "shipment_id"),
            ("goodsreceiptlineid", "goods_receipt_line_id"),
            ("receiptlineid", "goods_receipt_line_id"),
            ("goodsreceiptid", "goods_receipt_id"),
            ("receiptid", "goods_receipt_id"),
            ("inspectionlineid", "inspection_line_id"),
            ("inspectionid", "inspection_id"),
            ("inventorytransactionid", "inventory_transaction_id"),
            ("inventoryid", "inventory_id"),
            ("inventorybalanceid", "inventory_balance_id"),
            ("rawmaterialid", "raw_material_id"),
            ("materialid", "raw_material_id"),
            ("vendorid", "vendor_id"),
            ("plantid", "plant_id"),
            ("warehouseid", "warehouse_id"),
            ("requestedquantity", "requested_quantity"),
            ("rfqquantity", "rfq_quantity"),
            ("quotedquantity", "quoted_quantity"),
            ("quotedunitprice", "quoted_unit_price"),
            ("quotedlineamount", "quoted_line_amount"),
            ("scheduledquantity", "scheduled_quantity"),
            ("orderedquantity", "ordered_quantity"),
            ("shippedquantity", "shipped_quantity"),
            ("receivedquantity", "received_quantity"),
            ("damagedquantity", "damaged_quantity"),
            ("shortquantity", "short_quantity"),
            ("inspectedquantity", "inspected_quantity"),
            ("acceptedquantity", "accepted_quantity"),
            ("rejectedquantity", "rejected_quantity"),
            ("transactionquantity", "transaction_quantity"),
            ("onhandquantity", "on_hand_quantity"),
            ("reservedquantity", "reserved_quantity"),
            ("availablequantity", "available_quantity"),
            ("inventoryvalue", "inventory_value"),
            ("onhandvalue", "on_hand_value"),
            ("availablevalue", "available_value"),
            ("unitprice", "unit_price"),
            ("lineamount", "line_amount"),
            ("openquantity", "open_quantity"),
            ("totalinvoiceamount", "total_invoice_amount"),
            ("totalamount", "total_amount"),
            ("lasttransactiondate", "last_transaction_date"),
            ("lastupdateddate", "last_updated_date"),
            ("requisitiondate", "requisition_date"),
            ("requireddate", "required_date"),
            ("orderdate", "order_date"),
            ("expecteddeliverydate", "expected_delivery_date"),
            ("shipmentdate", "shipment_date"),
            ("receiptdate", "receipt_date"),
            ("inspectiondate", "inspection_date"),
            ("transactiondate", "transaction_date"),
            ("inventorypostingdate", "transaction_date"),
            ("postatus", "po_status"),
            ("rfqstatus", "rfq_status"),
            ("quotationstatus", "quotation_status"),
            ("schedulestatus", "schedule_status"),
            ("shipmentstatus", "shipment_status"),
            ("receiptstatus", "receipt_status"),
            ("inspectionstatus", "inspection_status"),
            ("resultstatus", "result_status"),
            ("invoicestatus", "invoice_status"),
            ("paymentstatus", "payment_status"),
            ("inventorystatus", "inventory_status"),
            ("linestatus", "line_status"),
            ("status", "status"),
            ("priority", "priority"),
            ("department", "department"),
            ("carriername", "carrier_name"),
            ("trackingnumber", "tracking_number"),
            ("inspectorname", "inspector_name"),
            ("testname", "test_name"),
            ("rejectionreason", "rejection_reason"),
            ("rejectionratepct", "rejection_rate_pct"),
            ("referencedocument", "reference_document"),
            ("transactiontype", "transaction_type"),
            ("paymentamount", "payment_amount"),
            ("paymentmethod", "payment_method"),
            ("invoiceamount", "invoice_amount"),
            ("taxamount", "tax_amount"),
            ("freightamount", "freight_amount"),
            ("invoicedate", "invoice_date"),
            ("rfqduedate", "rfq_due_date"),
            ("duedate", "due_date"),
            ("paymentdate", "payment_date"),
            ("currencycode", "currency_code"),
            ("rfqdate", "rfq_date"),
            ("buyername", "buyer_name"),
            ("quotationdate", "quotation_date"),
            ("validuntildate", "valid_until_date"),
            ("awardedflag", "awarded_flag"),
            ("leadtime", "lead_time_days"),
            ("scheduleddeliverydate", "scheduled_delivery_date"),
            ("requestername", "requester_name"),
            ("description", "description"),
            ("requestedby", "requested_by"),
        ]
        for token, semantic in mappings:
            if token in name:
                return semantic
        return name

    def _validate_business_invariants(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract, report: ValidationReport) -> None:
        by_role = self._dataframes_by_role(dataframes, schema)
        pol = by_role.get("purchase_order_line")
        sl = by_role.get("shipment_line")
        grl = by_role.get("goods_receipt_line")
        qil = by_role.get("quality_inspection_line")
        it = by_role.get("inventory_transaction")
        ib = by_role.get("inventory_balance")
        qih = by_role.get("quality_inspection_header")
        grh = by_role.get("goods_receipt_header")
        sh = by_role.get("shipment_header")
        poh = by_role.get("purchase_order_header")
        prh = by_role.get("purchase_requisition_header")

        self._validate_quantity_join(sl, pol, "PurchaseOrderLineID", "ShippedQuantity", "OrderedQuantity", "<=", report)
        self._validate_quantity_join(grl, sl, "ShipmentLineID", "ReceivedQuantity", "ShippedQuantity", "<=", report)
        if qil is not None and {"AcceptedQuantity", "RejectedQuantity", "InspectedQuantity"}.issubset(qil.columns):
            invalid = qil[(qil["AcceptedQuantity"] + qil["RejectedQuantity"]) != qil["InspectedQuantity"]]
            if not invalid.empty:
                report.add_error(message="AcceptedQuantity + RejectedQuantity must equal InspectedQuantity.", suggested_fix="Generate inspection quantities as a closed equation.")
        if it is not None and qil is not None and "InspectionLineID" in it.columns:
            merged = it.merge(qil, on="InspectionLineID", suffixes=("_txn", "_qi"))
            txn_col = "TransactionQuantity" if "TransactionQuantity" in merged.columns else "Quantity"
            if txn_col in merged.columns and "AcceptedQuantity" in merged.columns:
                if not (merged[txn_col] == merged["AcceptedQuantity"]).all():
                    report.add_error(message="Inventory transaction quantity must equal accepted quantity.", suggested_fix="Post only accepted inspection quantity to inventory.")
        if ib is not None and it is not None and {"RawMaterialID", "PlantID", "WarehouseID"}.issubset(ib.columns):
            qty_col = "TransactionQuantity" if "TransactionQuantity" in it.columns else "Quantity"
            if qty_col in it.columns:
                grouped = it.groupby(["RawMaterialID", "PlantID", "WarehouseID"], dropna=False)[qty_col].sum().reset_index()
                merged = ib.merge(grouped, on=["RawMaterialID", "PlantID", "WarehouseID"], how="left")
                if "OnHandQuantity" in merged.columns and not (merged["OnHandQuantity"] == merged[qty_col].fillna(0)).all():
                    report.add_error(message="InventoryBalance.OnHandQuantity must equal grouped inventory transactions.", suggested_fix="Aggregate transaction quantity by material, plant, and warehouse.")

        self._validate_date_order(prh, poh, "RequisitionID", "RequisitionDate", "OrderDate", report)
        self._validate_date_order(poh, sh, "PurchaseOrderID", "OrderDate", "ShipmentDate", report)
        self._validate_date_order(sh, grh, "ShipmentID", "ShipmentDate", "ReceiptDate", report)
        self._validate_date_order(grl, qih, "GoodsReceiptLineID", "ReceiptDate", "InspectionDate", report)
        self._validate_date_order(qil, it, "InspectionLineID", "InspectionDate", "TransactionDate", report)

        self._validate_plant_lineage(prh, poh, sh, grh, grl, qih, qil, it, report)

        for role, dataframe in by_role.items():
            for column_name in dataframe.columns:
                if "quantity" in column_name.lower() or column_name.lower().endswith("qty"):
                    numeric = pd.to_numeric(dataframe[column_name], errors="coerce")
                    if (numeric.dropna() < 0).any():
                        report.add_error(table_name=role, column_name=column_name, message="Negative quantity generated.", suggested_fix="Quantities must be non-negative.")

    def _validate_quantity_join(self, left, right, key, left_qty, right_qty, operator, report) -> None:
        if left is None or right is None or key not in left.columns or key not in right.columns:
            return
        if left_qty not in left.columns or right_qty not in right.columns:
            return
        right_subset = right[[key, right_qty]].rename(columns={right_qty: "__right_quantity"})
        merged = left.merge(right_subset, on=key, how="left")
        if operator == "<=" and not (merged[left_qty] <= merged["__right_quantity"]).all():
            report.add_error(message=f"{left_qty} must be <= {right_qty}.", suggested_fix="Respect procurement quantity lifecycle.")

    def _validate_receipt_warehouse_plant_alignment(
        self,
        transaction_dataframes: dict[str, pd.DataFrame],
        master_dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        report: ValidationReport,
    ) -> None:
        transaction_by_role = self._dataframes_by_role(transaction_dataframes, schema)
        master_by_role = self._dataframes_by_role(master_dataframes, schema)
        grh = transaction_by_role.get("goods_receipt_header")
        warehouses = master_by_role.get("warehouse_dimension")
        if grh is None or warehouses is None:
            return
        if not {"WarehouseID", "PlantID"}.issubset(grh.columns) or not {"WarehouseID", "PlantID"}.issubset(warehouses.columns):
            return
        merged = grh.merge(warehouses[["WarehouseID", "PlantID"]], on="WarehouseID", how="left", suffixes=("_receipt", "_warehouse"))
        invalid = merged[merged["PlantID_receipt"] != merged["PlantID_warehouse"]]
        if not invalid.empty:
            report.add_error(
                table_name="GoodsReceiptHeader",
                column_name="WarehouseID",
                message="GoodsReceiptHeader.WarehouseID must belong to the same PlantID as the receipt lifecycle.",
                suggested_fix="Select receiving warehouses from the linked PO/Requisition plant only.",
            )

    def _validate_plant_lineage(self, prh, poh, sh, grh, grl, qih, qil, it, report) -> None:
        if prh is not None and poh is not None and {"RequisitionID", "PlantID"}.issubset(prh.columns) and {"RequisitionID", "PlantID"}.issubset(poh.columns):
            merged = poh.merge(prh[["RequisitionID", "PlantID"]], on="RequisitionID", how="left", suffixes=("_po", "_req"))
            if not (merged["PlantID_po"] == merged["PlantID_req"]).all():
                report.add_error(
                    table_name="PurchaseOrderHeader",
                    column_name="PlantID",
                    message="PurchaseOrderHeader.PlantID must match linked PurchaseRequisitionHeader.PlantID.",
                    suggested_fix="Carry PlantID forward from the linked requisition header.",
                )

        if grh is not None and sh is not None and poh is not None and {"ShipmentID", "PlantID"}.issubset(grh.columns):
            merged = (
                grh.merge(sh[["ShipmentID", "PurchaseOrderID"]], on="ShipmentID", how="left")
                .merge(poh[["PurchaseOrderID", "PlantID"]], on="PurchaseOrderID", how="left", suffixes=("_receipt", "_po"))
            )
            if not (merged["PlantID_receipt"] == merged["PlantID_po"]).all():
                report.add_error(
                    table_name="GoodsReceiptHeader",
                    column_name="PlantID",
                    message="GoodsReceiptHeader.PlantID must match the linked PurchaseOrderHeader.PlantID.",
                    suggested_fix="Resolve receipt PlantID through ShipmentHeader -> PurchaseOrderHeader lineage.",
                )

        if it is not None and qil is not None and qih is not None and grh is not None and "InspectionLineID" in it.columns:
            required = {"InspectionLineID", "InspectionID"}
            if required.issubset(qil.columns) and {"InspectionID", "GoodsReceiptLineID"}.issubset(qih.columns):
                merged = (
                    it.merge(qil[["InspectionLineID", "InspectionID"]], on="InspectionLineID", how="left")
                    .merge(qih[["InspectionID", "GoodsReceiptLineID"]], on="InspectionID", how="left")
                )
                if grl is not None and {"GoodsReceiptLineID", "GoodsReceiptID"}.issubset(grl.columns):
                    merged = merged.merge(grl[["GoodsReceiptLineID", "GoodsReceiptID"]], on="GoodsReceiptLineID", how="left")
                    merged = merged.merge(
                        grh[["GoodsReceiptID", "PlantID", "WarehouseID"]],
                        on="GoodsReceiptID",
                        how="left",
                        suffixes=("_txn", "_receipt"),
                    )
                    if {"PlantID_txn", "PlantID_receipt", "WarehouseID_txn", "WarehouseID_receipt"}.issubset(merged.columns):
                        invalid = merged[
                            (merged["PlantID_txn"] != merged["PlantID_receipt"])
                            | (merged["WarehouseID_txn"] != merged["WarehouseID_receipt"])
                        ]
                        if not invalid.empty:
                            report.add_error(
                                table_name="InventoryTransaction",
                                message="InventoryTransaction PlantID/WarehouseID must match the linked receipt lineage.",
                                suggested_fix="Carry PlantID and WarehouseID from GoodsReceiptHeader through inspection lineage.",
                            )

    def _validate_date_order(self, earlier, later, key, earlier_col, later_col, report) -> None:
        if earlier is None or later is None or key not in earlier.columns or key not in later.columns:
            return
        if earlier_col not in earlier.columns or later_col not in later.columns:
            return
        merged = later.merge(earlier[[key, earlier_col]], on=key, how="left")
        if not (pd.to_datetime(merged[later_col]) >= pd.to_datetime(merged[earlier_col])).all():
            report.add_error(message=f"{earlier_col} must be <= {later_col}.", suggested_fix="Maintain procurement lifecycle date order.")

    def _validate_fk(self, table, column, series, all_dataframes, report) -> None:
        parent = all_dataframes.get(column.related_table or "")
        if parent is None or not column.related_column or column.related_column not in parent.columns:
            report.add_error(table_name=table.table_name, column_name=column.column_name, message="FK parent table/column missing.", suggested_fix="Generate parent before child.")
            return
        invalid = sorted(set(series.dropna()) - set(parent[column.related_column].dropna()))
        if invalid:
            report.add_error(table_name=table.table_name, column_name=column.column_name, message=f"FK values do not exist in parent: {invalid[:5]}.", suggested_fix="Use valid parent keys only.")

    def _validate_v2_transaction_data(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        master_dataframes: dict[str, pd.DataFrame],
        report: ValidationReport,
    ) -> None:
        expected_tables = {schema.tables_by_role[role].table_name for role in []} if False else None
        all_dataframes = {**master_dataframes, **dataframes}
        lifecycle_exhaustion_roles = {
            "purchase_order_header",
            "purchase_order_line",
            "po_schedule",
            "shipment_line",
            "goods_receipt_line",
            "incoming_inspection",
            "inspection_result",
            "inventory_transaction",
            "inventory",
        }
        for table in self.get_transaction_tables(schema, model_version="v2"):
            dataframe = dataframes.get(table.table_name)
            if dataframe is None:
                report.add_error(table_name=table.table_name, message="V2 transaction table DataFrame was not generated.", suggested_fix="Generate every v2 transaction lifecycle table.")
                continue
            if len(dataframe) != table.target_rows:
                if table.table_role == "inventory":
                    report.add_warning(
                        table_name=table.table_name,
                        message=f"Inventory generated {len(dataframe)} grouped rows; metadata target is {table.target_rows}.",
                        suggested_fix="This is acceptable because Inventory is derived from natural InventoryTransaction groups.",
                    )
                elif table.table_role == "inventory_transaction" and len(dataframe) < table.target_rows:
                    report.add_warning(
                        table_name=table.table_name,
                        message=f"InventoryTransaction generated {len(dataframe)} StockIn rows; metadata target is {table.target_rows}.",
                        suggested_fix="This is acceptable when accepted inspection quantities are exhausted before the target row count.",
                    )
                elif table.table_role in lifecycle_exhaustion_roles and len(dataframe) < table.target_rows:
                    report.add_warning(
                        table_name=table.table_name,
                        message=f"{table.table_name} generated {len(dataframe)} lifecycle-valid rows; metadata target is {table.target_rows}.",
                        suggested_fix="This is acceptable when upstream quoted/ordered quantity is exhausted before the target row count.",
                    )
                else:
                    report.add_error(table_name=table.table_name, message=f"Generated row count {len(dataframe)} does not match target {table.target_rows}.", suggested_fix="Generate the v2 metadata TargetRows count.")
            for column in table.columns:
                if column.column_name not in dataframe.columns:
                    report.add_error(table_name=table.table_name, column_name=column.column_name, message="Metadata column missing from generated transaction DataFrame.", suggested_fix="Generate every metadata column.")
                    continue
                series = dataframe[column.column_name]
                if column.key_type == "PK" and (series.isna().any() or not series.is_unique):
                    report.add_error(table_name=table.table_name, column_name=column.column_name, message="PK must be unique and non-null.", suggested_fix="Generate unique non-null sequence IDs.")
                if column.key_type == "FK":
                    self._validate_fk(table, column, series, all_dataframes, report)
                if column.nullable == "No" and series.isna().any():
                    report.add_error(table_name=table.table_name, column_name=column.column_name, message="Nullable = No column contains null values.", suggested_fix="Populate required v2 transaction columns.")
                if column.allowed_values:
                    invalid = sorted({str(value) for value in series.dropna()} - {str(value) for value in column.allowed_values})
                    if invalid:
                        report.add_error(table_name=table.table_name, column_name=column.column_name, message=f"Generated values outside AllowedValues: {', '.join(invalid)}.", suggested_fix="Use only metadata AllowedValues.")
                if column.column_name == "TransactionType":
                    continue
                if column.generation_type == "status" and len(column.allowed_values) > 1 and len(dataframe) >= 10 and series.nunique(dropna=True) <= 1:
                    report.add_warning(table_name=table.table_name, column_name=column.column_name, message="Status column has low diversity for v2 transaction data.", suggested_fix="Derive statuses from lifecycle facts.")

        self._validate_v2_core_invariants(dataframes, master_dataframes, report)

    def _validate_v2_core_invariants(self, data: dict[str, pd.DataFrame], master: dict[str, pd.DataFrame], report: ValidationReport) -> None:
        self._v2_assert_subset(data["PurchaseReqLine"], "RequisitionID", data["PurchaseRequisition"], "RequisitionID", "PurchaseReqLine", report)
        self._v2_assert_subset(data["RFQHeader"], "RequisitionID", data["PurchaseRequisition"], "RequisitionID", "RFQHeader", report)
        self._v2_assert_subset(data["RFQLine"], "RFQID", data["RFQHeader"], "RFQID", "RFQLine", report)
        self._v2_assert_subset(data["SupplierQuotation"], "SupplierID", master["SupplierMaster"], "SupplierID", "SupplierQuotation", report)
        self._v2_assert_subset(data["SupplierQuotationLn"], "QuotationID", data["SupplierQuotation"], "QuotationID", "SupplierQuotationLn", report)
        self._v2_assert_subset(data["PurchaseOrderLine"], "QuotationLineID", data["SupplierQuotationLn"], "QuotationLineID", "PurchaseOrderLine", report)
        self._v2_assert_subset(data["PaymentTransaction"], "SupplierInvoiceID", data["SupplierInvoice"], "SupplierInvoiceID", "PaymentTransaction", report)

        rfq_line_component = data["RFQLine"].set_index("RFQLineID")["ComponentID"]
        rfq_qty = data["RFQLine"].merge(
            data["PurchaseReqLine"][["RequisitionLineID", "RequestedQuantity"]],
            on="RequisitionLineID",
            how="left",
        )
        if not (rfq_qty["RFQQuantity"] <= rfq_qty["RequestedQuantity"] + 0.0001).all():
            report.add_error(table_name="RFQLine", column_name="RFQQuantity", message="RFQQuantity exceeds requested quantity.", suggested_fix="Cap RFQ quantity by linked PurchaseReqLine.RequestedQuantity.")

        quoted = data["SupplierQuotationLn"].join(rfq_line_component.rename("ExpectedComponentID"), on="RFQLineID")
        if not (quoted["ComponentID"] == quoted["ExpectedComponentID"]).all():
            report.add_error(table_name="SupplierQuotationLn", column_name="ComponentID", message="Quoted component must match RFQLine component.", suggested_fix="Carry ComponentID from RFQLine.")
        quoted_qty = data["SupplierQuotationLn"].merge(data["RFQLine"][["RFQLineID", "RFQQuantity"]], on="RFQLineID", how="left")
        if not (quoted_qty["QuotedQuantity"] <= quoted_qty["RFQQuantity"] + 0.0001).all():
            report.add_error(table_name="SupplierQuotationLn", column_name="QuotedQuantity", message="QuotedQuantity exceeds RFQQuantity.", suggested_fix="Cap quoted quantity by linked RFQLine.RFQQuantity.")

        awarded = data["SupplierQuotationLn"][data["SupplierQuotationLn"]["AwardedFlag"] == 1]
        po_lines = data["PurchaseOrderLine"].merge(awarded[["QuotationLineID", "QuotedUnitPrice", "QuotedQuantity"]], on="QuotationLineID", how="left")
        if po_lines["QuotedUnitPrice"].isna().any():
            report.add_error(table_name="PurchaseOrderLine", column_name="QuotationLineID", message="PO line must come from awarded SupplierQuotationLn.", suggested_fix="Use only AwardedFlag=1 quotation lines for PO lines.")
        if not (abs(po_lines["UnitPrice"] - po_lines["QuotedUnitPrice"]) <= 0.01).all():
            report.add_error(table_name="PurchaseOrderLine", column_name="UnitPrice", message="PO UnitPrice must match awarded quote price.", suggested_fix="Copy QuotedUnitPrice to UnitPrice.")
        if not (po_lines["OrderedQuantity"] <= po_lines["QuotedQuantity"] + 0.0001).all():
            report.add_error(table_name="PurchaseOrderLine", column_name="OrderedQuantity", message="OrderedQuantity exceeds awarded QuotedQuantity.", suggested_fix="Cap PO quantity by awarded quotation quantity.")
        ordered_by_quote = data["PurchaseOrderLine"].groupby("QuotationLineID")["OrderedQuantity"].sum().reset_index()
        ordered_by_quote = ordered_by_quote.merge(data["SupplierQuotationLn"][["QuotationLineID", "QuotedQuantity"]], on="QuotationLineID", how="left")
        if not (ordered_by_quote["OrderedQuantity"] <= ordered_by_quote["QuotedQuantity"] + 0.0001).all():
            report.add_error(table_name="PurchaseOrderLine", column_name="OrderedQuantity", message="Cumulative OrderedQuantity exceeds awarded QuotedQuantity for a QuotationLineID.", suggested_fix="Track remaining quoted quantity by QuotationLineID before creating PO lines.")

        sched = data["POSchedule"].groupby("PurchaseOrderLineID")["ScheduledQuantity"].sum().reset_index()
        sched = sched.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")
        if not (sched["ScheduledQuantity"] <= sched["OrderedQuantity"] + 0.0001).all():
            report.add_error(table_name="POSchedule", column_name="ScheduledQuantity", message="Scheduled quantity exceeds ordered quantity.", suggested_fix="Cap schedules by remaining ordered quantity.")

        shipped = data["ShipmentLine"].merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID")
        if not (shipped["ShippedQuantity"] <= shipped["ScheduledQuantity"] + 0.0001).all():
            report.add_error(table_name="ShipmentLine", column_name="ShippedQuantity", message="Shipped quantity exceeds scheduled quantity.", suggested_fix="Cap shipment quantities by schedule.")
        shipped_schedule = data["ShipmentLine"].groupby("POScheduleID")["ShippedQuantity"].sum().reset_index()
        shipped_schedule = shipped_schedule.merge(data["POSchedule"][["POScheduleID", "ScheduledQuantity"]], on="POScheduleID")
        if not (shipped_schedule["ShippedQuantity"] <= shipped_schedule["ScheduledQuantity"] + 0.0001).all():
            report.add_error(table_name="ShipmentLine", column_name="ShippedQuantity", message="Cumulative shipped quantity exceeds scheduled quantity.", suggested_fix="Track remaining scheduled quantity by POScheduleID.")
        shipped_po = data["ShipmentLine"].groupby("PurchaseOrderLineID")["ShippedQuantity"].sum().reset_index()
        shipped_po = shipped_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")
        if not (shipped_po["ShippedQuantity"] <= shipped_po["OrderedQuantity"] + 0.0001).all():
            report.add_error(table_name="ShipmentLine", column_name="ShippedQuantity", message="Cumulative shipped quantity exceeds ordered quantity.", suggested_fix="Track remaining ordered quantity by PurchaseOrderLineID.")

        receipts = data["GoodsReceiptLine"]
        if not (receipts["ReceivedQuantity"] <= receipts["ShippedQuantity"] + 0.0001).all():
            report.add_error(table_name="GoodsReceiptLine", column_name="ReceivedQuantity", message="Received quantity exceeds shipped quantity.", suggested_fix="Cap received quantity by shipped quantity.")
        receipt_shipment = receipts.groupby("ShipmentLineID")["ReceivedQuantity"].sum().reset_index()
        receipt_shipment = receipt_shipment.merge(data["ShipmentLine"][["ShipmentLineID", "ShippedQuantity"]], on="ShipmentLineID")
        if not (receipt_shipment["ReceivedQuantity"] <= receipt_shipment["ShippedQuantity"] + 0.0001).all():
            report.add_error(table_name="GoodsReceiptLine", column_name="ReceivedQuantity", message="Cumulative received quantity exceeds shipped quantity.", suggested_fix="Track remaining shipped quantity by ShipmentLineID.")
        receipt_po = receipts.groupby("PurchaseOrderLineID")["ReceivedQuantity"].sum().reset_index()
        receipt_po = receipt_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")
        if not (receipt_po["ReceivedQuantity"] <= receipt_po["OrderedQuantity"] + 0.0001).all():
            report.add_error(table_name="GoodsReceiptLine", column_name="ReceivedQuantity", message="Cumulative received quantity exceeds ordered quantity.", suggested_fix="Track remaining ordered quantity by PurchaseOrderLineID.")
        if not (abs(receipts["ShortQuantity"] - (receipts["ShippedQuantity"] - receipts["ReceivedQuantity"])) <= 0.0001).all():
            report.add_error(table_name="GoodsReceiptLine", column_name="ShortQuantity", message="ShortQuantity must equal ShippedQuantity - ReceivedQuantity.", suggested_fix="Calculate short quantity from receipt quantities.")

        results = data["InspectionResult"]
        inspection_received = (
            results.merge(data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID"]], on="InspectionID", how="left")
            .merge(data["GoodsReceiptLine"][["GoodsReceiptLineID", "ReceivedQuantity", "PurchaseOrderLineID"]], on="GoodsReceiptLineID", how="left")
        )
        if not (inspection_received["InspectedQuantity"] <= inspection_received["ReceivedQuantity"] + 0.0001).all():
            report.add_error(table_name="InspectionResult", column_name="InspectedQuantity", message="InspectedQuantity exceeds received quantity.", suggested_fix="Cap inspected quantity by GoodsReceiptLine.ReceivedQuantity.")
        if not (abs((results["AcceptedQuantity"] + results["RejectedQuantity"]) - results["InspectedQuantity"]) <= 0.0001).all():
            report.add_error(table_name="InspectionResult", message="AcceptedQuantity + RejectedQuantity must equal InspectedQuantity.", suggested_fix="Generate closed inspection quantities.")
        accepted_po = inspection_received.groupby("PurchaseOrderLineID")["AcceptedQuantity"].sum().reset_index()
        accepted_po = accepted_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")
        if not (accepted_po["AcceptedQuantity"] <= accepted_po["OrderedQuantity"] + 0.0001).all():
            report.add_error(table_name="InspectionResult", column_name="AcceptedQuantity", message="Cumulative accepted quantity exceeds ordered quantity.", suggested_fix="Track remaining ordered quantity before accepting inspection results.")
        zero_reject = results[results["RejectedQuantity"] == 0]
        if not zero_reject["RejectionReason"].fillna("").isin(["", "Not Applicable"]).all():
            report.add_error(table_name="InspectionResult", column_name="RejectionReason", message="RejectionReason must be blank or Not Applicable when RejectedQuantity is 0.", suggested_fix="Only populate rejection reason for rejected quantities.")
        rejected = results[results["RejectedQuantity"] > 0]
        if not rejected.empty and rejected["RejectionReason"].fillna("").isin(["", "Not Applicable"]).any():
            report.add_error(table_name="InspectionResult", column_name="RejectionReason", message="Rejected rows must have a real rejection reason.", suggested_fix="Populate varied rejection reasons when RejectedQuantity is positive.")
        if not rejected.empty and rejected["RejectionReason"].nunique(dropna=True) <= 1:
            report.add_warning(table_name="InspectionResult", column_name="RejectionReason", message="RejectionReason has low variety for rejected rows.", suggested_fix="Use varied EV quality rejection reasons.")

        inv = data["InventoryTransaction"].merge(results[["InspectionResultID", "AcceptedQuantity"]], on="InspectionResultID")
        if not (abs(inv["TransactionQuantity"] - inv["AcceptedQuantity"]) <= 0.0001).all():
            report.add_error(table_name="InventoryTransaction", column_name="TransactionQuantity", message="Inventory transaction quantity must equal accepted quantity.", suggested_fix="Post only accepted inspection quantity.")
        stock_in_po = data["InventoryTransaction"].groupby("PurchaseOrderLineID")["TransactionQuantity"].sum().reset_index()
        stock_in_po = stock_in_po.merge(data["PurchaseOrderLine"][["PurchaseOrderLineID", "OrderedQuantity"]], on="PurchaseOrderLineID")
        if not (stock_in_po["TransactionQuantity"] <= stock_in_po["OrderedQuantity"] + 0.0001).all():
            report.add_error(table_name="InventoryTransaction", column_name="TransactionQuantity", message="Cumulative StockIn quantity exceeds ordered quantity.", suggested_fix="Track remaining ordered quantity by PurchaseOrderLineID before creating InventoryTransaction rows.")
        if set(inv["TransactionType"].dropna()) != {"StockIn"}:
            report.add_error(table_name="InventoryTransaction", column_name="TransactionType", message="InventoryTransaction.TransactionType must be StockIn for v2 procurement inbound postings.", suggested_fix="Use StockIn for accepted supplier receipts entering inventory.")
        if not (inv["InventoryValue"] >= 0).all():
            report.add_error(table_name="InventoryTransaction", column_name="InventoryValue", message="InventoryValue must not be negative.", suggested_fix="Calculate non-negative stock-in value from accepted quantity and unit price.")
        if not (abs(inv["InventoryValue"] - (inv["TransactionQuantity"] * inv["UnitPrice"]).round(2)) <= 0.0100001).all():
            report.add_error(table_name="InventoryTransaction", column_name="InventoryValue", message="InventoryValue must equal TransactionQuantity * UnitPrice.", suggested_fix="Calculate InventoryValue from the posted quantity and PO unit price.")

        inspection_lineage = results[["InspectionResultID", "InspectionID"]].merge(
            data["IncomingInspection"][["InspectionID", "GoodsReceiptLineID", "InspectionDate"]],
            on="InspectionID",
        )
        inv_lineage = data["InventoryTransaction"].merge(inspection_lineage, on="InspectionResultID")
        if not (inv_lineage["GoodsReceiptLineID_x"] == inv_lineage["GoodsReceiptLineID_y"]).all():
            report.add_error(table_name="InventoryTransaction", column_name="GoodsReceiptLineID", message="GoodsReceiptLineID must match the inspection lineage.", suggested_fix="Carry GoodsReceiptLineID from IncomingInspection.")
        if not (pd.to_datetime(inv_lineage["TransactionDate"]) >= pd.to_datetime(inv_lineage["InspectionDate"])).all():
            report.add_error(table_name="InventoryTransaction", column_name="TransactionDate", message="InventoryTransaction.TransactionDate must be >= InspectionDate.", suggested_fix="Post accepted inventory on or after inspection.")

        receipt_lineage = data["InventoryTransaction"].merge(
            data["GoodsReceiptLine"][["GoodsReceiptLineID", "PurchaseOrderLineID", "ComponentID", "GoodsReceiptID"]],
            on="GoodsReceiptLineID",
            suffixes=("_txn", "_receipt"),
        )
        if not (receipt_lineage["PurchaseOrderLineID_txn"] == receipt_lineage["PurchaseOrderLineID_receipt"]).all():
            report.add_error(table_name="InventoryTransaction", column_name="PurchaseOrderLineID", message="PurchaseOrderLineID must match GoodsReceiptLine lineage.", suggested_fix="Carry PurchaseOrderLineID from GoodsReceiptLine.")
        if not (receipt_lineage["ComponentID_txn"] == receipt_lineage["ComponentID_receipt"]).all():
            report.add_error(table_name="InventoryTransaction", column_name="ComponentID", message="InventoryTransaction component must match GoodsReceiptLine component.", suggested_fix="Carry ComponentID from the received line.")

        po_supplier = data["PurchaseOrderLine"][["PurchaseOrderLineID", "PurchaseOrderID", "UnitPrice"]].merge(
            data["PurchaseOrderHdr"][["PurchaseOrderID", "SupplierID"]],
            on="PurchaseOrderID",
        )
        inv_po = data["InventoryTransaction"].merge(po_supplier, on="PurchaseOrderLineID", suffixes=("_txn", "_po"))
        if not (inv_po["SupplierID_txn"] == inv_po["SupplierID_po"]).all():
            report.add_error(table_name="InventoryTransaction", column_name="SupplierID", message="SupplierID must match PO supplier lineage.", suggested_fix="Derive SupplierID from PurchaseOrderHdr through the PO line.")
        if not (abs(inv_po["UnitPrice_txn"] - inv_po["UnitPrice_po"]) <= 0.01).all():
            report.add_error(table_name="InventoryTransaction", column_name="UnitPrice", message="UnitPrice must match PurchaseOrderLine.UnitPrice.", suggested_fix="Copy UnitPrice from the PO line.")

        self._validate_v2_inventory_balance_snapshot(data, master, report)

        invoice = data["SupplierInvoice"].merge(data["GoodsReceiptHeader"][["GoodsReceiptID", "ReceiptDate"]], on="GoodsReceiptID")
        if not (pd.to_datetime(invoice["InvoiceDate"]) >= pd.to_datetime(invoice["ReceiptDate"])).all():
            report.add_error(table_name="SupplierInvoice", column_name="InvoiceDate", message="InvoiceDate must be >= ReceiptDate.", suggested_fix="Create invoices after goods receipt.")
        payment = data["PaymentTransaction"].merge(data["SupplierInvoice"][["SupplierInvoiceID", "InvoiceDate", "TotalInvoiceAmount"]], on="SupplierInvoiceID")
        if not (pd.to_datetime(payment["PaymentDate"]) >= pd.to_datetime(payment["InvoiceDate"])).all():
            report.add_error(table_name="PaymentTransaction", column_name="PaymentDate", message="PaymentDate must be >= InvoiceDate.", suggested_fix="Create payments after invoice.")
        if not (payment["PaymentAmount"] <= payment["TotalInvoiceAmount"] + 0.0001).all():
            report.add_error(table_name="PaymentTransaction", column_name="PaymentAmount", message="PaymentAmount exceeds TotalInvoiceAmount.", suggested_fix="Cap payments by invoice total.")

        for table_name in ("SupplierQuotation", "PurchaseOrderHdr", "SupplierInvoice", "PaymentTransaction"):
            if "CurrencyCode" in data[table_name].columns and set(data[table_name]["CurrencyCode"].dropna()) != {"USD"}:
                report.add_error(table_name=table_name, column_name="CurrencyCode", message="CurrencyCode must be USD in v2 transactions.", suggested_fix="Use USD only.")

        warehouse_lookup = master["Warehouse"].set_index("WarehouseID")["PlantID"]
        for table_name in ("GoodsReceiptHeader", "InventoryTransaction"):
            merged = data[table_name].join(warehouse_lookup.rename("WarehousePlantID"), on="WarehouseID")
            if not (merged["PlantID"] == merged["WarehousePlantID"]).all():
                report.add_error(table_name=table_name, column_name="WarehouseID", message="WarehouseID must belong to the same PlantID.", suggested_fix="Use warehouses from the current plant.")

    def _validate_v2_inventory_balance_snapshot(self, data: dict[str, pd.DataFrame], master: dict[str, pd.DataFrame], report: ValidationReport) -> None:
        if "InventoryBalance" in data:
            report.add_error(table_name="InventoryBalance", message="InventoryBalance must not be generated for Procurement v2.", suggested_fix="Generate Inventory, not InventoryBalance.")
        inventory = data.get("Inventory")
        transactions = data.get("InventoryTransaction")
        if inventory is None:
            report.add_error(table_name="Inventory", message="Inventory table DataFrame was not generated.", suggested_fix="Generate Inventory after InventoryTransaction.")
            return
        if transactions is None or transactions.empty:
            report.add_error(table_name="InventoryTransaction", message="Inventory cannot be calculated without InventoryTransaction rows.", suggested_fix="Generate InventoryTransaction before Inventory.")
            return
        if inventory.empty:
            report.add_error(table_name="Inventory", message="Inventory table has no rows.", suggested_fix="Create one Inventory row per transaction component/plant/warehouse group.")
            return

        grouped = (
            transactions.groupby(["ComponentID", "PlantID", "WarehouseID"], as_index=False)
            .agg(
                ExpectedOnHandQuantity=("TransactionQuantity", "sum"),
                ExpectedOnHandValue=("InventoryValue", "sum"),
                ExpectedLastTransactionDate=("TransactionDate", "max"),
            )
        )
        merged = inventory.merge(grouped, on=["ComponentID", "PlantID", "WarehouseID"], how="outer", indicator=True)
        if len(inventory) != len(grouped) or not merged["_merge"].eq("both").all():
            report.add_error(table_name="Inventory", message="Inventory rows must match distinct InventoryTransaction ComponentID/PlantID/WarehouseID groups.", suggested_fix="Build Inventory directly from grouped InventoryTransaction records.")
            return

        if inventory["InventoryID"].isna().any() or not inventory["InventoryID"].is_unique:
            report.add_error(table_name="Inventory", column_name="InventoryID", message="InventoryID must be unique and non-null.", suggested_fix="Generate unique Inventory sequence IDs.")
        for column_name, parent_table, parent_column in [
            ("ComponentID", "ComponentMaster", "ComponentID"),
            ("PlantID", "Plant", "PlantID"),
            ("WarehouseID", "Warehouse", "WarehouseID"),
        ]:
            if not set(inventory[column_name].dropna()).issubset(set(master[parent_table][parent_column].dropna())):
                report.add_error(table_name="Inventory", column_name=column_name, message="Inventory FK contains invalid parent references.", suggested_fix="Use valid master keys for Inventory.")

        warehouse_lookup = master["Warehouse"].set_index("WarehouseID")["PlantID"]
        warehouse_aligned = inventory.join(warehouse_lookup.rename("WarehousePlantID"), on="WarehouseID")
        if not (warehouse_aligned["PlantID"] == warehouse_aligned["WarehousePlantID"]).all():
            report.add_error(table_name="Inventory", column_name="WarehouseID", message="Inventory.WarehouseID must belong to Inventory.PlantID.", suggested_fix="Use warehouses from the same plant.")

        if not (abs(merged["OnHandQuantity"] - merged["ExpectedOnHandQuantity"]) <= 0.0001).all():
            report.add_error(table_name="Inventory", column_name="OnHandQuantity", message="Inventory.OnHandQuantity must equal grouped InventoryTransaction quantity.", suggested_fix="Sum TransactionQuantity by ComponentID, PlantID, WarehouseID.")
        if "OnHandValue" in inventory.columns and not (abs(merged["OnHandValue"] - merged["ExpectedOnHandValue"]) <= 0.01).all():
            report.add_error(table_name="Inventory", column_name="OnHandValue", message="Inventory.OnHandValue must equal grouped InventoryTransaction value.", suggested_fix="Sum InventoryValue by ComponentID, PlantID, WarehouseID.")
        if not (inventory[["OnHandQuantity", "ReservedQuantity", "AvailableQuantity"]] >= 0).all().all():
            report.add_error(table_name="Inventory", message="Inventory quantities must not be negative.", suggested_fix="Keep OnHand, Reserved, and Available quantities at or above zero.")
        if {"OnHandValue", "AvailableValue"}.issubset(inventory.columns) and not (inventory[["OnHandValue", "AvailableValue"]] >= 0).all().all():
            report.add_error(table_name="Inventory", message="Inventory values must not be negative.", suggested_fix="Keep OnHandValue and AvailableValue at or above zero.")
        if not (inventory["ReservedQuantity"] <= inventory["OnHandQuantity"] + 0.0001).all():
            report.add_error(table_name="Inventory", column_name="ReservedQuantity", message="ReservedQuantity must not exceed OnHandQuantity.", suggested_fix="Cap reserved inventory by on-hand inventory.")
        if not (abs(inventory["AvailableQuantity"] - (inventory["OnHandQuantity"] - inventory["ReservedQuantity"])) <= 0.0001).all():
            report.add_error(table_name="Inventory", column_name="AvailableQuantity", message="AvailableQuantity must equal OnHandQuantity - ReservedQuantity.", suggested_fix="Calculate available inventory from on-hand and reserved quantities.")
        if {"OnHandValue", "AvailableValue"}.issubset(inventory.columns):
            average_cost = inventory["OnHandValue"].where(inventory["OnHandQuantity"] > 0, 0) / inventory["OnHandQuantity"].where(inventory["OnHandQuantity"] > 0, 1)
            expected_available_value = (inventory["AvailableQuantity"] * average_cost).round(2)
            if not (abs(inventory["AvailableValue"] - expected_available_value) <= 0.01).all():
                report.add_error(table_name="Inventory", column_name="AvailableValue", message="AvailableValue must equal AvailableQuantity multiplied by average unit cost.", suggested_fix="Calculate AvailableValue from AvailableQuantity and grouped average cost.")
            if not (inventory["AvailableValue"] <= inventory["OnHandValue"] + 0.01).all():
                report.add_error(table_name="Inventory", column_name="AvailableValue", message="AvailableValue must not exceed OnHandValue.", suggested_fix="Cap available stock value by on-hand stock value.")
        if not (pd.to_datetime(merged["LastTransactionDate"]) == pd.to_datetime(merged["ExpectedLastTransactionDate"])).all():
            report.add_error(table_name="Inventory", column_name="LastTransactionDate", message="LastTransactionDate must equal max InventoryTransaction.TransactionDate for the group.", suggested_fix="Use grouped max TransactionDate.")
        if not (pd.to_datetime(inventory["LastUpdatedDate"]) >= pd.to_datetime(inventory["LastTransactionDate"])).all():
            report.add_error(table_name="Inventory", column_name="LastUpdatedDate", message="LastUpdatedDate must be >= LastTransactionDate.", suggested_fix="Set LastUpdatedDate to LastTransactionDate or a later refresh date.")

        expected_status = inventory.apply(lambda row: self._v2_inventory_status(float(row["OnHandQuantity"]), float(row["AvailableQuantity"])), axis=1)
        if not (inventory["InventoryStatus"] == expected_status).all():
            report.add_error(table_name="Inventory", column_name="InventoryStatus", message="InventoryStatus does not match quantity logic.", suggested_fix="Derive status from OnHandQuantity and AvailableQuantity.")

    def _v2_assert_subset(self, child, child_col, parent, parent_col, table_name, report) -> None:
        if not set(child[child_col].dropna()).issubset(set(parent[parent_col].dropna())):
            report.add_error(table_name=table_name, column_name=child_col, message="FK relationship contains invalid parent references.", suggested_fix="Use valid parent keys only.")

    def _v2_varied_status(self, row_id: int, primary: str, alternates: list[str], probabilities: list[float], rng: random.Random) -> str:
        if row_id <= len(alternates):
            return alternates[row_id - 1]
        roll = rng.random()
        cumulative = 0.0
        for value, probability in zip(alternates, probabilities):
            cumulative += probability
            if roll < cumulative:
                return value
        return primary

    def _v2_add_days(self, value: date, days: int) -> date:
        return min(value + timedelta(days=days), date(2025, 12, 31))

    def _column_min_max(self, table: TableContract, column_name: str, default_min: float, default_max: float) -> tuple[float, float]:
        for column in table.columns:
            if column.column_name == column_name:
                minimum = float(column.min_value) if column.min_value is not None else default_min
                maximum = float(column.max_value) if column.max_value is not None else default_max
                return minimum, maximum
        return default_min, default_max

    def _dataframes_by_role(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract) -> dict[str, pd.DataFrame]:
        output = {}
        for table in schema.tables.values():
            if table.table_name in dataframes:
                output[table.table_role] = dataframes[table.table_name]
        return output

    def _target_rows(self, table: TableContract, plan: LLMGenerationPlan | None) -> int:
        if plan is not None:
            for row_count in plan.row_count_plan:
                if row_count.table_name == table.table_name:
                    return row_count.target_rows
        return table.target_rows

    def _column_values(self, dataframe: pd.DataFrame, preferred_column: str) -> list[Any]:
        if dataframe is None or dataframe.empty:
            return []
        if preferred_column in dataframe.columns:
            return list(dataframe[preferred_column].dropna())
        return []

    def _date_min(self, table: TableContract) -> date | None:
        for column in table.columns:
            if "date" in column.column_name.lower() and column.min_value:
                return pd.to_datetime(column.min_value).date()
        return None

    def _choice(self, values: list[Any], rng: random.Random) -> Any:
        return values[rng.randrange(len(values))]

    def _weighted_choice(self, values: list[Any], weights: list[int], rng: random.Random) -> Any:
        return rng.choices(values, weights=weights, k=1)[0]

    def _plant_for_po(self, context: ProcurementGenerationContext, purchase_order_id: Any) -> Any:
        for po in context.purchase_order_headers:
            if po["id"] == purchase_order_id:
                return po["plant_id"]
        return None

    def _fallback_calculated_value(self, column: ColumnContract, record: dict[str, Any]) -> Any:
        key = self._semantic_key(column.column_name)
        if key in record:
            return record[key]
        if "amount" in column.column_name.lower():
            return 0.0
        if "quantity" in column.column_name.lower():
            return 0
        return None

    def _status_or_category_value(self, column: ColumnContract, record: dict[str, Any]) -> Any:
        key = self._semantic_key(column.column_name)
        value = record.get(key) or record.get("status")
        if column.allowed_values:
            return self._closest_allowed_value(value, column.allowed_values)
        return value or "Active"

    def _closest_allowed_value(self, value: Any, allowed: list[str]) -> str:
        if value in allowed:
            return value
        text = str(value or "").lower()
        preferences = {
            "approved": ["Approved", "ConvertedToPO", "Closed", "Active"],
            "sent": ["Sent", "Open", "Active"],
            "shipped": ["Shipped", "InTransit", "Open", "Active"],
            "received": ["Received", "Closed", "Active"],
            "passed": ["Passed", "Completed", "Active"],
            "partiallyrejected": ["PartiallyRejected", "Rejected", "Failed", "Passed"],
            "failed": ["Failed", "Rejected", "PartiallyRejected"],
            "closed": ["Closed", "Received", "Completed", "Active"],
            "receipt": ["Receipt", "StockIn", "QualityRelease"],
        }
        for key, candidates in preferences.items():
            if key in text:
                for candidate in candidates:
                    if candidate in allowed:
                        return candidate
        return allowed[0]

    def _required_fallback_value(self, column: ColumnContract, index: int) -> Any:
        name = column.column_name.lower()
        if "date" in name:
            return date(2025, 1, 1)
        if "quantity" in name or name.endswith("qty") or "id" in name:
            return 1
        if "amount" in name or "price" in name or "cost" in name:
            return 1.0
        if "status" in name:
            return column.allowed_values[0] if column.allowed_values else "Active"
        return f"REF-{index:06d}"

    def _context_attr_for_role(self, role: str) -> str:
        return {
            "purchase_requisition_header": "requisition_headers",
            "purchase_requisition_line": "requisition_lines",
            "purchase_order_header": "purchase_order_headers",
            "purchase_order_line": "purchase_order_lines",
            "shipment_header": "shipment_headers",
            "shipment_line": "shipment_lines",
            "goods_receipt_header": "goods_receipt_headers",
            "goods_receipt_line": "goods_receipt_lines",
            "quality_inspection_header": "quality_inspection_headers",
            "quality_inspection_line": "quality_inspection_lines",
            "inventory_transaction": "inventory_transactions",
            "inventory_balance": "inventory_balances",
        }[role]


def format_transaction_generation_report(
    dataframes: dict[str, pd.DataFrame],
    report: ValidationReport,
    output_folder: str | Path | None = None,
    model_version: str | None = None,
) -> str:
    lines = [
        "Transaction data generation completed.",
    ]
    if model_version is not None:
        lines.append(f"Model version: {model_version}")
    lines.append(f"Transaction tables generated: {len(dataframes)}")
    for table_name, dataframe in dataframes.items():
        lines.append(f"{table_name} rows: {len(dataframe)}")
    lines.extend(
        [
            f"Validation errors: {len(report.errors)}",
            f"Validation warnings: {len(report.warnings)}",
        ]
    )
    if output_folder is not None:
        lines.append(f"Output folder: {output_folder}")
    lines.append(f"Generation status: {'passed' if report.is_valid else 'failed'}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, issue in enumerate(report.warnings, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))
    return "\n".join(lines)


def generate_master_and_transaction_data(
    schema: SchemaContract,
    plan: LLMGenerationPlan,
    seed: int | None = None,
    model_version: str = "v1",
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], ValidationReport]:
    master_generator = ProcurementMasterDataGenerator()
    master_data, master_report = master_generator.generate_master_data(schema, plan, seed=seed, model_version=model_version)
    if not master_report.is_valid:
        return master_data, {}, master_report
    transaction_generator = ProcurementTransactionGenerator()
    transaction_data, transaction_report = transaction_generator.generate_transaction_data(
        schema,
        plan,
        master_data,
        seed=seed,
        model_version=model_version,
    )
    return master_data, transaction_data, transaction_report


def _format_issue(index: int, table_name: str | None, column_name: str | None, message: str, suggested_fix: str) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines
