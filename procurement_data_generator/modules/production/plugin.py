"""Production module plugin adapter."""

from __future__ import annotations

from typing import Any, Sequence

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.modules.contracts import PromptSection, UpstreamRequirement
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.reconciler_rules import UPSTREAM_TABLES
from procurement_data_generator.modules.production.role_catalog import get_production_role_catalog
from procurement_data_generator.modules.production.role_validator import validate_production_roles
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator


class ProductionModulePlugin:
    """Thin adapter over the existing Production v1 implementation."""

    module_id = "production"
    module_name = "Production"
    module_version = "v1"
    _plan_model_version = "production_v1"

    @property
    def supported_table_roles(self) -> tuple[str, ...]:
        return tuple(self.get_role_catalog())

    def get_role_catalog(self):
        return get_production_role_catalog(self._plan_model_version)

    def validate_roles(
        self,
        schema: SchemaContract,
        report: ValidationReport | None = None,
        model_version: str | None = None,
    ):
        return validate_production_roles(schema, report=report, model_version=model_version or self._plan_model_version)

    def get_prompt_sections(
        self,
        schema: SchemaContract | None = None,
        relationships: Sequence[RelationshipContract] | None = None,
        scenario: str | None = None,
    ) -> tuple[PromptSection, ...]:
        return (
            PromptSection(
                section_id="production_v1_prompt",
                title="Production v1 Prompt Guidance",
                content="Production v1 prompt guidance is currently provided by the existing production fixtures and validators.",
            ),
        )

    def validate_plan(
        self,
        plan: LLMGenerationPlan,
        schema: SchemaContract,
        relationships: Sequence[RelationshipContract],
    ):
        return validate_generation_plan(plan, schema, list(relationships), model_version=self._plan_model_version)

    def create_master_generator(self, **kwargs: Any) -> ProductionMasterDataGenerator:
        return ProductionMasterDataGenerator(**kwargs)

    def create_transaction_generator(self, **kwargs: Any) -> ProductionTransactionGenerator:
        return ProductionTransactionGenerator(**kwargs)

    def create_data_quality_engine(self):
        raise NotImplementedError(
            "Production v1 uses validate_production_generated_data instead of a reusable data quality engine. "
            "Phase 2 can introduce a common quality adapter if needed."
        )

    def get_upstream_requirements(self) -> tuple[UpstreamRequirement, ...]:
        return (
            UpstreamRequirement(
                module_id="procurement",
                table_names=UPSTREAM_TABLES,
                required=True,
                description="Production v1 consumes Procurement inventory and receipt lineage tables.",
            ),
        )
