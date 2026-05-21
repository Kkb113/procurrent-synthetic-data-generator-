"""Deterministic synthesis from industry scenario hints to executable plans."""

from __future__ import annotations

from typing import Any

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.llm.industry_scenario_contract import IndustryScenarioPlan
from procurement_data_generator.modules.production.role_catalog import PRODUCTION_V1_EXPECTED_TABLES


class PlanSynthesizer:
    """Build the strict internal plan using metadata, ERD, and scenario hints.

    The LLM owns only the small ``IndustryScenarioPlan``. Exact table names,
    column names, row counts, lifecycle order, and executable rule shapes stay
    in deterministic Python.
    """

    def synthesize(
        self,
        schema: SchemaContract,
        relationships: list[RelationshipContract],
        scenario: IndustryScenarioPlan,
        model_version: str = "v2",
    ) -> LLMGenerationPlan:
        module = "production" if model_version == "production_v1" else "procurement"
        plan_payload = {
            "module": module,
            "business_summary": scenario.business_summary,
            "domain_profile": self._domain_profile(scenario),
            "table_role_mapping": [self._table_role_mapping(table) for table in schema.ordered_tables],
            "generation_order": self._generation_order(schema, model_version),
            "row_count_plan": [self._row_count_plan(table) for table in schema.ordered_tables],
            "column_generation_rules": [
                self._column_generation_rule(table, column)
                for table in schema.ordered_tables
                for column in table.columns
            ],
            "formula_rules": [],
            "date_rules": self._date_rules(schema),
            "quantity_rules": [],
            "status_rules": [
                self._status_rule(table, column)
                for table in schema.ordered_tables
                for column in table.columns
                if self._is_status_column(column)
            ],
            "validation_rules": self._validation_rules(model_version),
            "assumptions": self._assumptions(scenario),
            "warnings": list(scenario.warnings),
        }
        return LLMGenerationPlan.model_validate(plan_payload)

    def _domain_profile(self, scenario: IndustryScenarioPlan) -> dict[str, Any]:
        component_terms = scenario.procurement.component_categories or scenario.procurement.raw_material_terms
        if not component_terms:
            component_terms = ["Manufacturing Components", "Raw Materials", "Packaging Materials"]
        material_categories = [
            {
                "category_name": term,
                "material_examples": scenario.procurement.raw_material_terms[:5] or [term],
                "specification_patterns": scenario.procurement.inspection_or_quality_hints[:5],
            }
            for term in component_terms[:8]
        ]
        return {
            "industry": scenario.industry_name,
            "business_context": scenario.business_summary,
            "vendor_categories": scenario.procurement.supplier_types
            or ["Component Supplier", "Raw Material Supplier", "Packaging Supplier"],
            "material_categories": material_categories,
            "warehouse_types": ["Raw Material Warehouse", "Finished Goods Warehouse"],
            "plant_locations": scenario.shared.geography_terms or ["USA"],
            "carrier_name_patterns": scenario.sales.sales_channels or ["DIRECT", "DISTRIBUTOR"],
            "inspection_test_categories": scenario.procurement.inspection_or_quality_hints
            or scenario.shared.regulatory_or_quality_terms
            or ["incoming inspection", "quality inspection"],
        }

    def _table_role_mapping(self, table: TableContract) -> dict[str, Any]:
        return {
            "table_name": table.table_name,
            "table_role": table.table_role,
            "area": table.area,
            "confidence": "high",
            "reasoning": "Derived from validated metadata, not from LLM table-name output.",
        }

    def _generation_order(self, schema: SchemaContract, model_version: str) -> list[str]:
        if model_version == "production_v1" and set(schema.tables) == set(PRODUCTION_V1_EXPECTED_TABLES):
            return list(PRODUCTION_V1_EXPECTED_TABLES)
        return [table.table_name for table in schema.ordered_tables]

    def _row_count_plan(self, table: TableContract) -> dict[str, Any]:
        return {
            "table_name": table.table_name,
            "target_rows": table.target_rows,
            "source": "metadata",
            "reasoning": "TargetRows from validated metadata.",
        }

    def _column_generation_rule(self, table: TableContract, column: ColumnContract) -> dict[str, Any]:
        nullable_strategy = "nullable_allowed" if column.nullable == "Yes" else "never_null"
        return {
            "table_name": table.table_name,
            "column_name": column.column_name,
            "generation_type": column.generation_type,
            "strategy": self._strategy_for_column(column),
            "allowed_values": self._allowed_values_for_column(column),
            "min_value": self._safe_scalar(column.min_value),
            "max_value": self._safe_scalar(column.max_value),
            "nullable_strategy": nullable_strategy,
            "depends_on_columns": [],
            "notes": "Synthesized from metadata by Python.",
        }

    def _strategy_for_column(self, column: ColumnContract) -> str:
        if column.generation_type == "sequence_id":
            return "Generate deterministic sequential identifiers."
        if column.generation_type == "foreign_key":
            target = f"{column.related_table}.{column.related_column}" if column.related_table and column.related_column else "the parent table"
            return f"Select valid keys from {target} after parent generation."
        if column.generation_type == "status":
            return "Derive status values from lifecycle facts and metadata allowed values."
        if column.generation_type == "category":
            return "Choose deterministic category values from metadata allowed values and domain defaults."
        if column.generation_type == "calculated":
            return "Calculate deterministically in Python generation/formula stages."
        if column.generation_type in {"integer_range", "decimal_range"}:
            return "Generate deterministic numeric values within metadata min/max bounds."
        if column.generation_type in {"date_range", "date_offset"}:
            return "Generate lifecycle-consistent dates within configured metadata ranges."
        return f"Generate deterministic {column.generation_type} values using metadata and domain profile hints."

    def _allowed_values_for_column(self, column: ColumnContract) -> list[str]:
        if column.generation_type not in {"category", "status"}:
            return []
        return list(column.allowed_values)

    def _date_rules(self, schema: SchemaContract) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        for table in schema.ordered_tables:
            date_columns = [
                column.column_name
                for column in table.columns
                if self._is_date_column(column)
            ]
            if len(date_columns) < 2:
                continue
            rules.append(
                {
                    "rule_id": f"{table.table_name}_{date_columns[0]}_before_{date_columns[-1]}",
                    "earlier_table": table.table_name,
                    "earlier_column": date_columns[0],
                    "later_table": table.table_name,
                    "later_column": date_columns[-1],
                    "min_offset_days": 0,
                    "max_offset_days": 365,
                    "description": "Python synthesized lifecycle date ordering guidance from metadata date columns.",
                }
            )
        return rules

    def _is_date_column(self, column: ColumnContract) -> bool:
        data_type = column.data_type.strip().lower()
        return data_type.startswith(("date", "datetime", "datetime2", "timestamp"))

    def _is_status_column(self, column: ColumnContract) -> bool:
        return column.generation_type == "status" and bool(column.allowed_values)

    def _status_rule(self, table: TableContract, column: ColumnContract) -> dict[str, Any]:
        return {
            "rule_id": f"{table.table_name}_{column.column_name}_status_from_lifecycle",
            "table_name": table.table_name,
            "status_column": column.column_name,
            "status_values": list(column.allowed_values),
            "derivation_logic": "Derive from lifecycle facts and generated quantities/dates, not random assignment.",
            "description": "Python synthesized lifecycle status guidance.",
        }

    def _validation_rules(self, model_version: str) -> list[dict[str, Any]]:
        rules = [
            {
                "rule_id": "global_currency_usd",
                "rule_type": "validation",
                "condition": "CurrencyCode = USD when metadata defines USD currency.",
                "severity": "warning",
                "description": "Currency consistency theme.",
            },
            {
                "rule_id": "global_country_usa",
                "rule_type": "validation",
                "condition": "Country = USA for US-scoped supplier, plant, and warehouse locations when metadata requires it.",
                "severity": "warning",
                "description": "Country consistency theme.",
            },
            {
                "rule_id": "status_diversity",
                "rule_type": "validation",
                "condition": "status diversity should reflect lifecycle state, not random assignment.",
                "severity": "warning",
                "description": "Lifecycle status theme.",
            },
            {
                "rule_id": "payment_amount_invoice_total",
                "rule_type": "validation",
                "condition": "payment amount <= invoice total.",
                "severity": "warning",
                "description": "Payment reconciliation theme.",
            },
        ]
        if model_version == "production_v1":
            rules.extend(self._production_v1_validation_themes())
        return rules

    def _production_v1_validation_themes(self) -> list[dict[str, Any]]:
        conditions = [
            "2025-only date scope for production execution dates.",
            "RequiredQuantity = PlannedQuantity * ComponentQuantity.",
            "ScrapAdjustedQuantity = RequiredQuantity * (1 + ScrapFactorPct / 100).",
            "IssueValue = IssuedQuantity * UnitCost.",
            "PassedQuantity + FailedQuantity = TestedQuantity.",
            "ReceiptValue = GoodQuantity * UnitCost.",
            "FinishedGoodsInventory OnHandQuantity rolls up from FinishedGoodsReceipt GoodQuantity.",
            "TotalProductionCost = MaterialCost + LaborCost + OverheadCost + ScrapCost.",
            "UnitProductionCost = TotalProductionCost / GoodQuantity.",
            "Production consumes Procurement Inventory.",
            "MaterialIssueLine references InventoryTransaction.",
            "MaterialIssueLine references InventoryReceiptDetail.",
            "ProductionGenealogy traces MaterialIssueLine InventoryReceiptDetail InventoryTransaction ComponentMaster SupplierMaster.",
            "UOM precision: countable materials use integer quantities; bulk materials may use decimal quantities.",
        ]
        return [
            {
                "rule_id": f"production_theme_{index}",
                "rule_type": "validation",
                "condition": condition,
                "severity": "warning",
                "description": "Production v1 semantic validation theme synthesized by Python.",
            }
            for index, condition in enumerate(conditions, start=1)
        ]

    def _assumptions(self, scenario: IndustryScenarioPlan) -> list[str]:
        assumptions = list(scenario.assumptions)
        assumptions.append("Executable table and column references are synthesized from validated metadata by Python.")
        assumptions.append("Row counts are sourced from metadata TargetRows; LLM row-count guesses are not used.")
        assumptions.append("Lifecycle formulas, reconciliation, and validation remain Python-owned deterministic behavior.")
        return assumptions

    def _safe_scalar(self, value: Any) -> str | int | float | None:
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            if isinstance(value, float) and value != value:
                return None
            return value
        return str(value)
