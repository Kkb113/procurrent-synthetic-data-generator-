from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD_PATH = ROOT / "input" / "procurement_v2_erd.mmd"
VALID_PLAN_PATH = ROOT / "input" / "sample_generation_plan_v2_valid.json"
INVALID_PLAN_PATH = ROOT / "input" / "sample_generation_plan_v2_invalid.json"

V2_TABLES = {
    "SupplierMaster",
    "SupplierComponent",
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "PurchaseRequisition",
    "PurchaseReqLine",
    "RFQHeader",
    "RFQLine",
    "SupplierQuotation",
    "SupplierQuotationLn",
    "PurchaseOrderHdr",
    "PurchaseOrderLine",
    "POSchedule",
    "ShipmentHdr",
    "ShipmentLine",
    "GoodsReceiptHeader",
    "GoodsReceiptLine",
    "IncomingInspection",
    "InspectionResult",
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
}


def test_valid_v2_plan_passes_semantic_validation() -> None:
    result = _validate(_valid_plan())

    assert result.report.is_valid
    assert len(result.report.errors) == 0


def test_valid_v2_plan_has_24_roles() -> None:
    plan = _valid_plan()

    assert {mapping.table_name for mapping in plan.table_role_mapping} == V2_TABLES
    assert len({mapping.table_role for mapping in plan.table_role_mapping}) == 24
    assert any(mapping.table_role == "inventory" for mapping in plan.table_role_mapping)


def test_inventory_balance_in_generation_order_fails() -> None:
    data = _valid_plan_data()
    data["generation_order"].append("InventoryBalance")

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "InventoryBalance in generation_order")


def test_inventory_balance_in_formula_rules_fails() -> None:
    data = _valid_plan_data()
    data["formula_rules"].append(
        {
            "rule_id": "bad_inventory_balance",
            "rule_type": "aggregate",
            "target_table": "InventoryBalance",
            "target_column": "OnHandQuantity",
            "operation": "sum",
            "input_columns": [],
            "source_table": "InventoryTransaction",
            "source_column": "TransactionQuantity",
            "relationship_key": None,
            "group_by_columns": ["ComponentID"],
            "formula": "SUM(TransactionQuantity)",
            "denominator_column": None,
            "denominator_guard": False,
            "tolerance_type": "absolute",
            "tolerance_value": 0.0001,
            "description": None,
        }
    )

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "InventoryBalance in formula_rules")


def test_inventory_balance_role_fails() -> None:
    data = _valid_plan_data()
    data["table_role_mapping"].append(
        {
            "table_name": "InventoryBalance",
            "table_role": "inventory_balance",
            "area": "Inventory",
            "confidence": "high",
            "reasoning": None,
        }
    )

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "InventoryBalance or inventory_balance role")


def test_missing_v2_table_from_generation_order_fails() -> None:
    data = _valid_plan_data()
    data["generation_order"].remove("PaymentTransaction")

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "missing from generation_order")


def test_duplicate_v2_table_in_generation_order_fails() -> None:
    data = _valid_plan_data()
    data["generation_order"][-1] = "SupplierMaster"

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "Duplicate generation_order table")


def test_fk_parent_after_child_order_fails() -> None:
    data = _valid_plan_data()
    data["generation_order"].remove("PaymentTransaction")
    data["generation_order"].insert(0, "PaymentTransaction")

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "FK dependency order violation")


def test_wrong_v2_role_mapping_fails() -> None:
    data = _valid_plan_data()
    data["table_role_mapping"][0]["table_role"] = "purchase_order_header"

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "metadata role is supplier_master")


def test_currency_code_non_usd_rule_is_flagged() -> None:
    data = _valid_plan_data()
    _column_rule(data, "ComponentMaster", "CurrencyCode")["allowed_values"] = ["EUR"]

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "CurrencyCode generation must be USD-only")


def test_non_usa_country_rule_is_flagged() -> None:
    data = _valid_plan_data()
    _column_rule(data, "Plant", "PlantCountry")["allowed_values"] = ["Canada"]

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "country generation must be USA-only")


def test_missing_warehouse_location_generation_rule_produces_warning() -> None:
    data = _valid_plan_data()
    data["column_generation_rules"] = [
        rule
        for rule in data["column_generation_rules"]
        if not (rule["table_name"] == "Warehouse" and rule["column_name"] == "WarehouseLocation")
    ]

    result = _validate_data(data)

    assert result.report.is_valid
    assert _has_warning(result, "Warehouse location column_generation_rule")


def test_v2_key_formula_rules_validate() -> None:
    result = _validate(_valid_plan())

    assert result.report.is_valid
    assert result.summary.accepted_formula_rules >= 8
    assert not _has_warning(result, "Procurement v2 key formula rule is missing")


def test_v2_plan_includes_refined_inventory_transaction_columns_and_stockin() -> None:
    data = _valid_plan_data()

    for column_name in [
        "GoodsReceiptLineID",
        "PurchaseOrderLineID",
        "SupplierID",
        "UnitPrice",
        "InventoryValue",
        "InventoryStatus",
    ]:
        assert _column_rule(data, "InventoryTransaction", column_name)

    transaction_type = _column_rule(data, "InventoryTransaction", "TransactionType")
    assert transaction_type["allowed_values"] == ["StockIn"]
    assert _status_rule(data, "InventoryTransaction", "TransactionType")["status_values"] == ["StockIn"]
    assert _formula_rule(data, "InventoryTransaction", "InventoryValue")["input_columns"] == ["TransactionQuantity", "UnitPrice"]


def test_v2_plan_includes_inventory_value_rules() -> None:
    data = _valid_plan_data()

    assert _column_rule(data, "Inventory", "OnHandValue")
    assert _column_rule(data, "Inventory", "AvailableValue")
    assert any(rule["rule_id"] == "V2_INVENTORY_ON_HAND_VALUE" for rule in data["validation_rules"])
    assert any(rule["rule_id"] == "V2_INVENTORY_AVAILABLE_VALUE" for rule in data["validation_rules"])


def test_v2_formula_tolerance_none_for_money_warns() -> None:
    data = _valid_plan_data()
    formula = _formula_rule(data, "PurchaseOrderLine", "LineAmount")
    formula["tolerance_type"] = "none"
    formula["tolerance_value"] = 0.0

    result = _validate_data(data)

    assert result.report.is_valid
    assert _has_warning(result, "Money formula uses tolerance_type none or zero tolerance")


def test_v2_status_rule_invalid_value_fails() -> None:
    data = _valid_plan_data()
    _status_rule(data, "PurchaseOrderHdr", "POStatus")["status_values"] = ["CompleteX"]

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "invalid v2 status values")


def test_v2_status_rule_missing_for_key_status_column_warns() -> None:
    data = _valid_plan_data()
    data["status_rules"] = [
        rule
        for rule in data["status_rules"]
        if not (rule["table_name"] == "PurchaseOrderHdr" and rule["status_column"] == "POStatus")
    ]

    result = _validate_data(data)

    assert result.report.is_valid
    assert _has_warning(result, "key lifecycle status column is missing a status_rule")


def test_v2_domain_profile_missing_ev_material_categories_warns() -> None:
    data = _valid_plan_data()
    data["domain_profile"]["material_categories"] = [
        {"category_name": "Generic Supplies", "material_examples": ["Bolt"], "specification_patterns": []}
    ]

    result = _validate_data(data)

    assert result.report.is_valid
    assert _has_warning(result, "EV-component-specific")


def test_v2_date_rule_missing_date_column_fails() -> None:
    data = _valid_plan_data()
    data["date_rules"][0]["later_column"] = "MissingDate"

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "Referenced column MissingDate")


def test_v2_quantity_rule_non_numeric_column_fails() -> None:
    data = _valid_plan_data()
    data["quantity_rules"][0]["left_table"] = "SupplierMaster"
    data["quantity_rules"][0]["left_column"] = "SupplierName"

    result = _validate_data(data)

    assert not result.report.is_valid
    assert _has_error(result, "not numeric-compatible")


def test_v2_global_currency_validation_rule_is_allowed() -> None:
    data = _valid_plan_data()
    data["validation_rules"].append(
        {
            "rule_id": "GLOBAL_USD_ONLY",
            "rule_type": "status_check",
            "table_name": None,
            "column_name": "CurrencyCode",
            "condition": "All CurrencyCode values must be USD.",
            "severity": "error",
            "description": "Global USD-only validation rule.",
        }
    )

    result = _validate_data(data)

    assert result.report.is_valid


def test_v2_global_country_validation_rule_is_allowed() -> None:
    data = _valid_plan_data()
    data["validation_rules"].append(
        {
            "rule_id": "GLOBAL_USA_ONLY",
            "rule_type": "status_check",
            "table_name": None,
            "column_name": "SupplierCountry",
            "condition": "PlantCountry, WarehouseCountry, and SupplierCountry must be USA.",
            "severity": "error",
            "description": "Global USA-only country validation rule.",
        }
    )

    result = _validate_data(data)

    assert result.report.is_valid


def test_invalid_v2_sample_plan_fails() -> None:
    load_result = load_llm_plan_json(INVALID_PLAN_PATH)
    assert load_result.report.is_valid
    assert load_result.plan is not None

    result = _validate(load_result.plan)

    assert not result.report.is_valid
    assert len(result.report.errors) > 0


def _schema_and_relationships():
    schema_result = load_metadata_schema(METADATA_PATH)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None
    return schema_result.schema, parse_mermaid_erd_file(ERD_PATH)


def _valid_plan() -> LLMGenerationPlan:
    load_result = load_llm_plan_json(VALID_PLAN_PATH)
    assert load_result.report.is_valid
    assert load_result.plan is not None
    return load_result.plan


def _valid_plan_data() -> dict[str, object]:
    return deepcopy(json.loads(VALID_PLAN_PATH.read_text(encoding="utf-8")))


def _validate(plan: LLMGenerationPlan):
    schema, relationships = _schema_and_relationships()
    return validate_generation_plan(plan, schema, relationships, model_version="v2")


def _validate_data(data: dict[str, object]):
    return _validate(LLMGenerationPlan.model_validate(data))


def _has_error(result, text: str) -> bool:
    return any(text in issue.message for issue in result.report.errors)


def _has_warning(result, text: str) -> bool:
    return any(text in issue.message for issue in result.report.warnings)


def _column_rule(data: dict[str, object], table_name: str, column_name: str) -> dict[str, object]:
    return next(
        rule
        for rule in data["column_generation_rules"]
        if rule["table_name"] == table_name and rule["column_name"] == column_name
    )


def _formula_rule(data: dict[str, object], table_name: str, column_name: str) -> dict[str, object]:
    return next(
        rule
        for rule in data["formula_rules"]
        if rule["target_table"] == table_name and rule["target_column"] == column_name
    )


def _status_rule(data: dict[str, object], table_name: str, column_name: str) -> dict[str, object]:
    return next(
        rule
        for rule in data["status_rules"]
        if rule["table_name"] == table_name and rule["status_column"] == column_name
    )
