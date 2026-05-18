from __future__ import annotations

from copy import deepcopy

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.llm.plan_normalizer import normalize_column_generation_dependencies
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan


def test_invalid_cross_table_depends_on_columns_get_normalized() -> None:
    result = normalize_column_generation_dependencies(_plan(), _schema())
    rule = result.plan.column_generation_rules[0]

    assert rule.table_name == "IncomingInspection"
    assert rule.column_name == "InspectorName"
    assert rule.depends_on_columns == []
    assert len(result.warnings) == 1
    assert result.warnings[0].table_name == "IncomingInspection"
    assert result.warnings[0].column_name == "InspectorName"
    assert result.warnings[0].removed_dependency == "PlantID"


def test_original_plan_remains_unchanged_after_normalization() -> None:
    plan = _plan()

    normalize_column_generation_dependencies(plan, _schema())

    assert plan.column_generation_rules[0].depends_on_columns == ["PlantID"]


def test_formula_rules_are_not_normalized() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"][0]["input_columns"] = ["MissingFormulaColumn"]
    plan = LLMGenerationPlan.model_validate(plan_data)

    result = normalize_column_generation_dependencies(plan, _schema())

    assert result.plan.formula_rules[0].input_columns == ["MissingFormulaColumn"]


def test_date_aggregate_formula_alias_gets_normalized() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"].append(
        {
            "rule_id": "inventory_last_txn_date",
            "rule_type": "aggregate",
            "target_table": "Inventory",
            "target_column": "LastTransactionDate",
            "operation": "max",
            "input_columns": ["TransactionDate"],
            "source_table": "InventoryTransaction",
            "source_column": "TransactionDate",
            "relationship_key": None,
            "group_by_columns": ["ComponentID", "PlantID", "WarehouseID"],
            "formula": "MAX(InventoryTransaction.TransactionDate)",
            "denominator_column": None,
            "denominator_guard": True,
            "tolerance_type": "absolute",
            "tolerance_value": 0.0,
            "description": "Set last transaction date to the latest transaction date in the inventory group.",
        }
    )
    plan = LLMGenerationPlan.model_validate(plan_data)

    result = normalize_column_generation_dependencies(plan, _schema_with_live_aliases())

    assert [rule.rule_id for rule in result.plan.formula_rules] == ["inspection_id_echo"]
    assert any(warning.normalization_type == "formula_rules" for warning in result.warnings)


def test_cross_table_date_rule_alias_gets_normalized() -> None:
    plan_data = _plan_data()
    plan_data["date_rules"].append(
        {
            "rule_id": "rfq_after_requisition",
            "earlier_table": "RFQHeader",
            "earlier_column": "RequisitionDate",
            "later_table": "RFQHeader",
            "later_column": "RFQDate",
            "min_offset_days": 0,
            "max_offset_days": 30,
            "description": "RFQ date must follow requisition date.",
        }
    )
    plan = LLMGenerationPlan.model_validate(plan_data)

    result = normalize_column_generation_dependencies(plan, _schema_with_live_aliases())

    assert result.plan.date_rules == []
    assert any(warning.normalization_type == "date_rules" for warning in result.warnings)


def test_semantic_validation_uses_normalized_depends_on_columns() -> None:
    normalized = normalize_column_generation_dependencies(_plan(), _schema())
    validation = validate_generation_plan(normalized.plan, _schema(), [], model_version="v2")

    assert not any("depends_on_columns" in issue.message for issue in validation.report.errors)


def _plan() -> LLMGenerationPlan:
    return LLMGenerationPlan.model_validate(_plan_data())


def _plan_data() -> dict:
    return deepcopy(
        {
            "module": "procurement",
            "business_summary": "Incoming inspection plan.",
            "domain_profile": {
                "industry": "General manufacturing",
                "business_context": "Inspection planning.",
                "vendor_categories": ["Industrial"],
                "material_categories": [
                    {
                        "category_name": "Raw Materials",
                        "material_examples": ["Industrial Sheet Metal"],
                        "specification_patterns": ["Grade A"],
                    }
                ],
                "warehouse_types": ["Quality Hold"],
                "plant_locations": ["Bengaluru"],
                "carrier_name_patterns": [],
                "inspection_test_categories": ["Visual Inspection"],
            },
            "table_role_mapping": [
                {
                    "table_name": "IncomingInspection",
                    "table_role": "incoming_inspection",
                    "area": "Quality",
                    "confidence": "high",
                    "reasoning": None,
                }
            ],
            "generation_order": ["IncomingInspection"],
            "row_count_plan": [
                {
                    "table_name": "IncomingInspection",
                    "target_rows": 1,
                    "source": "metadata",
                    "reasoning": None,
                }
            ],
            "column_generation_rules": [
                {
                    "table_name": "IncomingInspection",
                    "column_name": "InspectorName",
                    "generation_type": "faker_person",
                    "strategy": "Generate inspector names.",
                    "allowed_values": [],
                    "min_value": None,
                    "max_value": None,
                    "nullable_strategy": "never_null",
                    "depends_on_columns": ["PlantID"],
                    "notes": None,
                }
            ],
            "formula_rules": [
                {
                    "rule_id": "inspection_id_echo",
                    "rule_type": "row_level",
                    "target_table": "IncomingInspection",
                    "target_column": "InspectionID",
                    "operation": "add",
                    "input_columns": ["InspectionID", "InspectionID"],
                    "source_table": None,
                    "source_column": None,
                    "relationship_key": None,
                    "group_by_columns": [],
                    "formula": "InspectionID + InspectionID",
                    "denominator_column": None,
                    "denominator_guard": False,
                    "tolerance_type": "none",
                    "tolerance_value": None,
                    "description": None,
                }
            ],
            "date_rules": [],
            "quantity_rules": [],
            "status_rules": [],
            "validation_rules": [],
            "assumptions": [],
            "warnings": [],
        }
    )


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "IncomingInspection": TableContract(
                table_name="IncomingInspection",
                process_order=1,
                area="Quality",
                table_role="incoming_inspection",
                target_rows=1,
                columns=[
                    ColumnContract(
                        column_name="InspectionID",
                        data_type="int",
                        key_type="PK",
                        nullable="No",
                        generation_type="sequence_id",
                    ),
                    ColumnContract(
                        column_name="InspectorName",
                        data_type="varchar(100)",
                        key_type=None,
                        nullable="No",
                        generation_type="faker_person",
                    ),
                ],
            )
        }
    )


def _schema_with_live_aliases() -> SchemaContract:
    tables = dict(_schema().tables)
    tables["Inventory"] = TableContract(
        table_name="Inventory",
        process_order=2,
        area="Inventory",
        table_role="inventory",
        target_rows=1,
        columns=[
            ColumnContract(
                column_name="LastTransactionDate",
                data_type="date",
                key_type=None,
                nullable="No",
                generation_type="calculated",
            ),
        ],
    )
    tables["InventoryTransaction"] = TableContract(
        table_name="InventoryTransaction",
        process_order=3,
        area="Inventory",
        table_role="inventory_transaction",
        target_rows=1,
        columns=[
            ColumnContract(
                column_name="TransactionDate",
                data_type="date",
                key_type=None,
                nullable="No",
                generation_type="date_range",
            ),
        ],
    )
    tables["PurchaseRequisition"] = TableContract(
        table_name="PurchaseRequisition",
        process_order=4,
        area="Procurement",
        table_role="purchase_requisition",
        target_rows=1,
        columns=[
            ColumnContract(
                column_name="RequisitionDate",
                data_type="date",
                key_type=None,
                nullable="No",
                generation_type="date_range",
            ),
        ],
    )
    tables["RFQHeader"] = TableContract(
        table_name="RFQHeader",
        process_order=5,
        area="Procurement",
        table_role="rfq_header",
        target_rows=1,
        columns=[
            ColumnContract(
                column_name="RFQDate",
                data_type="date",
                key_type=None,
                nullable="No",
                generation_type="date_range",
            ),
        ],
    )
    return SchemaContract(tables=tables)
