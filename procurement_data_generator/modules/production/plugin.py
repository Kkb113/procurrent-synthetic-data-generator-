"""Production module plugin adapter."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.config import GenerationConfig, OperatingScope
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.modules.contracts import PromptSection, UpstreamRequirement
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import SQLServerLoader
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.prompt_sections import get_production_prompt_sections
from procurement_data_generator.modules.production.reconciler_rules import UPSTREAM_TABLES
from procurement_data_generator.modules.production.role_catalog import get_production_role_catalog
from procurement_data_generator.modules.production.role_validator import validate_production_roles
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator
from procurement_data_generator.modules.production.validation_rules import get_production_validation_rules


SQLLoaderFactory = Callable[[DatabaseConfig], SQLServerLoader]


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
        return get_production_prompt_sections(schema=schema, relationships=relationships, scenario=scenario)

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

    def get_validation_rules(self) -> tuple[str, ...]:
        return get_production_validation_rules()

    def run_pipeline(
        self,
        *,
        metadata_path: str,
        erd_path: str,
        scenario_path: str,
        plan_path: str,
        output_folder: str,
        seed: int | None = None,
        upstream_data_path: str | None = None,
        run_id: str | None = None,
        load_sql: bool = False,
        allow_unvalidated_sql_load: bool = False,
        if_table_exists: str = "replace",
        sql_loader_factory: SQLLoaderFactory | None = None,
        allow_demo_fallback: bool = False,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ):
        """Run Production v1 through the existing Production pipeline implementation."""

        from scripts.run_production_pipeline import run_production_pipeline

        effective_upstream = Path(upstream_data_path) if upstream_data_path else None
        fallback_used = False
        if effective_upstream is None and allow_demo_fallback:
            effective_upstream = self._write_demo_upstream_data(Path(output_folder), operating_scope, generation_config)
            fallback_used = True
        if effective_upstream is None:
            raise ValueError(
                "Production requires Procurement upstream data. Run modules=['procurement','production'] "
                "or provide upstream_data / allow_demo_fallback=True."
            )

        result = run_production_pipeline(
            metadata_path=metadata_path,
            erd_path=erd_path,
            scenario_path=scenario_path,
            plan_path=plan_path,
            upstream_data_path=effective_upstream,
            output_root=output_folder,
            seed=seed,
            run_id=run_id,
            load_sql=load_sql,
            allow_unvalidated_sql_load=allow_unvalidated_sql_load,
            if_table_exists=if_table_exists,
            sql_loader_factory=sql_loader_factory,
            operating_scope=operating_scope,
            generation_config=generation_config,
        )
        if fallback_used:
            return replace(
                result,
                warnings=[
                    *result.warnings,
                    "Production generic pipeline used explicit demo fallback upstream data.",
                ],
            )
        return result

    def get_upstream_requirements(self) -> tuple[UpstreamRequirement, ...]:
        return (
            UpstreamRequirement(
                module_id="procurement",
                table_names=UPSTREAM_TABLES,
                required=True,
                description="Production v1 consumes Procurement inventory and receipt lineage tables.",
            ),
        )

    def _write_demo_upstream_data(
        self,
        output_folder: Path,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> Path:
        output_path = output_folder / "_demo_upstream"
        output_path.mkdir(parents=True, exist_ok=True)
        context = self.create_transaction_generator(
            operating_scope=operating_scope,
            generation_config=generation_config,
        ).load_upstream_data(None, None)
        frames: dict[str, pd.DataFrame] = {
            "ComponentMaster": context.component_master,
            "Plant": context.plant,
            "Warehouse": context.warehouse,
            "Inventory": context.inventory,
            "InventoryTransaction": context.inventory_transaction,
            "InventoryReceiptDetail": context.inventory_receipt_detail,
            "SupplierMaster": context.supplier_master,
        }
        for table_name, dataframe in frames.items():
            dataframe.to_csv(output_path / f"{table_name}.csv", index=False)
        return output_path
