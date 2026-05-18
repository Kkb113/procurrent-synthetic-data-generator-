"""Sales module plugin skeleton."""

from __future__ import annotations

from typing import Any, Sequence

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.modules.contracts import PromptSection, UpstreamRequirement
from procurement_data_generator.modules.sales.master_generator import SalesMasterDataGenerator
from procurement_data_generator.modules.sales.prompt_sections import get_sales_prompt_sections
from procurement_data_generator.modules.sales.role_catalog import get_sales_role_catalog
from procurement_data_generator.modules.sales.role_validator import validate_sales_roles
from procurement_data_generator.modules.sales.transaction_generator import SalesTransactionGenerator
from procurement_data_generator.modules.sales.validation_rules import get_sales_validation_rules


SALES_EXECUTION_NOT_IMPLEMENTED = (
    "Sales module is registered but execution is not implemented yet. "
    "Sales execution starts in a later Sales phase."
)


class SalesModulePlugin:
    """Registered Sales / Order-to-Cash module boundary."""

    module_id = "sales"
    module_name = "Sales"
    module_version = "v1"

    @property
    def supported_table_roles(self) -> tuple[str, ...]:
        return tuple(self.get_role_catalog())

    def get_role_catalog(self):
        return get_sales_role_catalog(self.module_version)

    def validate_roles(
        self,
        schema: SchemaContract,
        report: ValidationReport | None = None,
        model_version: str | None = None,
    ):
        return validate_sales_roles(schema, report=report, model_version=model_version or self.module_version)

    def get_prompt_sections(
        self,
        schema: SchemaContract | None = None,
        relationships: Sequence[RelationshipContract] | None = None,
        scenario: str | None = None,
    ) -> tuple[PromptSection, ...]:
        return get_sales_prompt_sections(schema=schema, relationships=relationships, scenario=scenario)

    def validate_plan(
        self,
        plan: LLMGenerationPlan,
        schema: SchemaContract,
        relationships: Sequence[RelationshipContract],
    ):
        raise NotImplementedError("Sales plan validation is not implemented yet.")

    def create_master_generator(self, **kwargs: Any) -> SalesMasterDataGenerator:
        return SalesMasterDataGenerator(**kwargs)

    def create_transaction_generator(self, **kwargs: Any) -> SalesTransactionGenerator:
        return SalesTransactionGenerator(**kwargs)

    def create_data_quality_engine(self):
        raise NotImplementedError("Sales data quality validation is not implemented yet.")

    def get_validation_rules(self) -> tuple[str, ...]:
        return get_sales_validation_rules()

    def run_pipeline(self, **kwargs: Any):
        raise NotImplementedError(SALES_EXECUTION_NOT_IMPLEMENTED)

    def get_upstream_requirements(self) -> tuple[UpstreamRequirement, ...]:
        return (
            UpstreamRequirement(
                module_id="production",
                table_names=(
                    "ProductMaster",
                    "FinishedGoodsInventory",
                    "FinishedGoodsReceipt",
                    "ProductionBatch",
                    "ProductionGenealogy",
                    "ProductionCostSummary",
                    "MaterialIssueLine",
                ),
                required=True,
                description="Sales v1 starts from Production finished goods inventory and traceability outputs.",
            ),
            UpstreamRequirement(
                module_id="procurement",
                table_names=(
                    "SupplierMaster",
                    "ComponentMaster",
                    "InventoryReceiptDetail",
                    "InventoryTransaction",
                ),
                required=True,
                description="Sales v1 traceability follows Production genealogy back to Procurement suppliers and components.",
            ),
        )
