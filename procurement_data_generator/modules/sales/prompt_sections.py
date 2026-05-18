"""Sales-specific LLM planning prompt sections."""

from __future__ import annotations

from collections.abc import Sequence

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.modules.contracts import PromptSection
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES


def get_sales_prompt_sections(
    schema: SchemaContract | None = None,
    relationships: Sequence[RelationshipContract] | None = None,
    scenario: str | None = None,
) -> tuple[PromptSection, ...]:
    """Return Sales v1 planning guidance.

    Sales execution is not implemented in Sales Phase 1. These sections exist
    so the module boundary is ready for later prompt assembly work.
    """

    return (
        PromptSection(
            section_id="sales.v1.lifecycle",
            title="Sales v1 Order-to-Cash Guidance",
            content=_lifecycle_content(),
        ),
        PromptSection(
            section_id="sales.v1.traceability",
            title="Sales v1 Finished Goods and Traceability Guidance",
            content=_traceability_content(),
        ),
        PromptSection(
            section_id="sales.v1.profile",
            title="Sales v1 Industry Profile Vocabulary Guidance",
            content=_profile_content(),
        ),
    )


def _lifecycle_content() -> str:
    table_list = "\n".join(f"- {table_name}" for table_name in SALES_V1_EXPECTED_TABLES)
    return "\n".join(
        [
            "Sales v1 represents Order-to-Cash planning only in this phase.",
            "Sales lifecycle: Customer -> SalesOrder -> Reservation -> Pick -> Shipment -> Invoice -> Payment -> optional Return.",
            "Sales v1 tables:",
            table_list,
            "",
            "SalesCreditMemo is excluded from Sales v1; returns are operationally represented by SalesReturnHeader and SalesReturnLine.",
            "Quantity lifecycle guidance for later implementation: OrderedQuantity >= ReservedQuantity >= PickedQuantity >= ShippedQuantity >= InvoiceQuantity.",
            "Python must still validate, generate, calculate, reconcile, and enforce Sales business rules in later phases.",
        ]
    )


def _traceability_content() -> str:
    return "\n".join(
        [
            "Sales starts from Production FinishedGoodsInventory and must not directly consume raw Procurement Inventory.",
            "SalesInventoryReservation should reserve available finished goods from FinishedGoodsInventory.",
            "SalesShipmentLine should act as the finished-goods outbound ledger.",
            "Sales COGS planning should use FinishedGoodsReceipt.UnitCost, with ProductionCostSummary.UnitProductionCost as a validation cross-check.",
            "SalesShipmentTraceability connects customer shipments back through FinishedGoodsReceipt, ProductionBatch, ProductionGenealogy, MaterialIssueLine, InventoryReceiptDetail, InventoryTransaction where available, SupplierMaster, ComponentMaster, and ProductMaster.",
        ]
    )


def _profile_content() -> str:
    return "\n".join(
        [
            "Customer and channel vocabulary should be industry-profile-driven.",
            "For food manufacturing, customer and channel examples include Grocery Retailer, Distributor, Foodservice, Convenience Store, E-commerce, and Regional Wholesaler.",
            "Do not hardcode EV, automotive, dealer, or fleet vocabulary as generic Sales behavior.",
        ]
    )

