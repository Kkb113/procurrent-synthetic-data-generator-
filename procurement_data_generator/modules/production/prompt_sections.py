"""Production-specific LLM prompt sections."""

from __future__ import annotations

from collections.abc import Sequence

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.modules.contracts import PromptSection
from procurement_data_generator.modules.production.role_catalog import PRODUCTION_V1_EXPECTED_TABLES


def get_production_prompt_sections(
    schema: SchemaContract | None = None,
    relationships: Sequence[RelationshipContract] | None = None,
    scenario: str | None = None,
) -> tuple[PromptSection, ...]:
    return (
        PromptSection(
            section_id="production.v1.lifecycle",
            title="Production v1 Lifecycle Guidance",
            content=_lifecycle_content(),
        ),
        PromptSection(
            section_id="production.v1.traceability",
            title="Production v1 Procurement Integration and Traceability",
            content=_traceability_content(),
        ),
    )


def _lifecycle_content() -> str:
    table_list = "\n".join(f"- {table_name}" for table_name in PRODUCTION_V1_EXPECTED_TABLES)
    return "\n".join(
        [
            "Production v1 is a Production Execution module within MES context.",
            "Production planning should use the current simplified operating scope: one Plant, one Warehouse, and ShiftCode A only.",
            "Production v1 tables:",
            table_list,
            "",
            "Production lifecycle:",
            "ProductMaster -> BOMHeader -> BOMLine -> WorkCenter -> RoutingHeader -> RoutingOperation -> ProductionShift -> ProductionOrderHdr -> ProductionOrderLine -> ProductionMaterialRequirement -> MaterialIssueHeader -> MaterialIssueLine -> ProductionBatch -> OperationExecution -> ProductionQualityInspection -> ProductionQualityResult -> ScrapReworkEvent -> FinishedGoodsReceipt -> FinishedGoodsInventory -> ProductionGenealogy -> ProductionCostSummary",
            "- ProductionOrderHdr and ProductionOrderLine describe released manufacturing work.",
            "- BOMHeader and BOMLine define component requirements for products.",
            "- RoutingHeader and RoutingOperation define operation sequence through WorkCenter resources.",
            "- ProductionMaterialRequirement should be derived from ProductionOrderLine and BOMLine.",
            "- MaterialIssueHeader and MaterialIssueLine represent production material issue and consumption.",
            "- OperationExecution should follow routing operations and shift context.",
            "- ProductionQualityInspection and ProductionQualityResult capture quality outcomes.",
            "- ScrapReworkEvent captures scrap and rework details where lifecycle facts support them.",
            "- FinishedGoodsReceipt records completed good quantity.",
            "- FinishedGoodsInventory rolls up finished goods receipts.",
            "- ProductionCostSummary rolls up material, labor, overhead, scrap, total, and unit production cost.",
        ]
    )


def _traceability_content() -> str:
    return "\n".join(
        [
            "Production v1 consumes upstream Procurement data and should not rewrite Procurement outputs.",
            "Required upstream Procurement context includes ComponentMaster, Plant, Warehouse, Inventory, InventoryTransaction, InventoryReceiptDetail, and SupplierMaster.",
            "- Material issue quantities must not exceed available Procurement inventory.",
            "- MaterialIssueLine should reference Inventory, InventoryTransaction, and InventoryReceiptDetail where metadata provides those columns.",
            "- ProductionGenealogy traces finished goods back to MaterialIssueLine, InventoryReceiptDetail, InventoryTransaction, ComponentMaster, and SupplierMaster.",
            "- FinishedGoodsReceipt should connect ProductionBatch and ProductionOrderLine to ProductMaster.",
            "- FinishedGoodsInventory should roll up FinishedGoodsReceipt by product and location.",
            "- Cost summary formulas should preserve material cost, labor cost, overhead cost, scrap cost, total production cost, and unit production cost relationships.",
            "Production full generic runner execution remains deferred to Phase 8; this section is planning guidance only.",
        ]
    )
