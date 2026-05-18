"""Procurement module plugin adapter."""

from __future__ import annotations

from typing import Any, Sequence

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.modules.contracts import PromptSection, UpstreamRequirement
from procurement_data_generator.modules.procurement.data_quality import ProcurementDataQualityEngine
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.prompt_sections import get_procurement_prompt_sections
from procurement_data_generator.modules.procurement.role_catalog import get_procurement_role_catalog
from procurement_data_generator.modules.procurement.role_validator import validate_procurement_roles
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator
from procurement_data_generator.modules.procurement.validation_rules import get_procurement_validation_rules


class ProcurementModulePlugin:
    """Thin adapter over the existing Procurement v2 implementation."""

    module_id = "procurement"
    module_name = "Procurement"
    module_version = "v2"

    @property
    def supported_table_roles(self) -> tuple[str, ...]:
        return tuple(self.get_role_catalog())

    def get_role_catalog(self):
        return get_procurement_role_catalog(self.module_version)

    def validate_roles(
        self,
        schema: SchemaContract,
        report: ValidationReport | None = None,
        model_version: str | None = None,
    ):
        return validate_procurement_roles(schema, report=report, model_version=model_version or self.module_version)

    def get_prompt_sections(
        self,
        schema: SchemaContract | None = None,
        relationships: Sequence[RelationshipContract] | None = None,
        scenario: str | None = None,
    ) -> tuple[PromptSection, ...]:
        return get_procurement_prompt_sections(schema=schema, relationships=relationships, scenario=scenario)

    def validate_plan(
        self,
        plan: LLMGenerationPlan,
        schema: SchemaContract,
        relationships: Sequence[RelationshipContract],
    ):
        return validate_generation_plan(plan, schema, list(relationships), model_version=self.module_version)

    def create_master_generator(self, **kwargs: Any) -> ProcurementMasterDataGenerator:
        return ProcurementMasterDataGenerator(**kwargs)

    def create_transaction_generator(self, **kwargs: Any) -> ProcurementTransactionGenerator:
        return ProcurementTransactionGenerator(**kwargs)

    def create_data_quality_engine(self) -> ProcurementDataQualityEngine:
        return ProcurementDataQualityEngine()

    def get_validation_rules(self) -> tuple[str, ...]:
        return get_procurement_validation_rules()

    def run_pipeline(self, **kwargs: Any):
        raise NotImplementedError("Procurement generic execution is handled by ProcurementPipelineRunner compatibility orchestration.")

    def get_upstream_requirements(self) -> tuple[UpstreamRequirement, ...]:
        return ()
