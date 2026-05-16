"""Generic MES module plugin contracts.

Plugins are thin adapters around existing module implementations. They expose
capabilities to the application without moving generation or validation logic
out of the owning module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport


@dataclass(frozen=True)
class PromptSection:
    """A module-owned planning prompt section."""

    section_id: str
    title: str
    content: str


@dataclass(frozen=True)
class UpstreamRequirement:
    """An upstream module/table dependency needed by a module."""

    module_id: str
    table_names: tuple[str, ...]
    required: bool = True
    description: str = ""


@runtime_checkable
class MESModulePlugin(Protocol):
    """Adapter contract implemented by each MES module."""

    module_id: str
    module_name: str
    module_version: str

    @property
    def supported_table_roles(self) -> tuple[str, ...]:
        """Return the table roles supported by this module."""

    def get_role_catalog(self) -> Mapping[str, Any]:
        """Return the module role catalog."""

    def validate_roles(
        self,
        schema: SchemaContract,
        report: ValidationReport | None = None,
        model_version: str | None = None,
    ) -> Any:
        """Validate metadata table roles for this module."""

    def get_prompt_sections(
        self,
        schema: SchemaContract | None = None,
        relationships: Sequence[RelationshipContract] | None = None,
        scenario: str | None = None,
    ) -> tuple[PromptSection, ...]:
        """Return module-specific prompt sections when available."""

    def validate_plan(
        self,
        plan: LLMGenerationPlan,
        schema: SchemaContract,
        relationships: Sequence[RelationshipContract],
    ) -> Any:
        """Validate a structured LLM plan for this module."""

    def create_master_generator(self, **kwargs: Any) -> Any:
        """Create the module's master/setup data generator."""

    def create_transaction_generator(self, **kwargs: Any) -> Any:
        """Create the module's transaction/execution data generator."""

    def create_data_quality_engine(self) -> Any:
        """Create the module's data quality engine when one exists."""

    def get_upstream_requirements(self) -> tuple[UpstreamRequirement, ...]:
        """Return upstream module dependencies for integrated generation."""
