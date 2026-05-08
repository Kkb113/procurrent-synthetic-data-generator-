from __future__ import annotations

from copy import deepcopy

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan


def test_valid_plan_passes_phase6_validation() -> None:
    result = validate_generation_plan(_plan(), _schema(), _relationships())

    assert result.report.is_valid
    assert result.summary.accepted_formula_rules == 2
    assert result.summary.rejected_formula_rules == 0


def test_unknown_table_in_table_role_mapping_fails() -> None:
    plan_data = _plan_data()
    plan_data["table_role_mapping"][0]["table_name"] = "UnknownVendor"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "does not exist in metadata")


def test_wrong_role_mapping_fails() -> None:
    plan_data = _plan_data()
    plan_data["table_role_mapping"][1]["table_role"] = "shipment_header"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "metadata role is purchase_order_header")


def test_duplicate_table_in_generation_order_fails() -> None:
    plan_data = _plan_data()
    plan_data["generation_order"][1] = "Vendor"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "Duplicate generation_order table")


def test_missing_metadata_table_from_generation_order_fails() -> None:
    plan_data = _plan_data()
    plan_data["generation_order"] = plan_data["generation_order"][:-1]

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "missing from generation_order")


def test_fk_parent_after_child_generation_order_fails() -> None:
    plan_data = _plan_data()
    plan_data["generation_order"] = ["PurchaseOrderHeader", "Vendor", "PurchaseOrderLine", "ShipmentLine"]

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "FK dependency order violation")


def test_row_count_source_metadata_but_target_differs_fails() -> None:
    plan_data = _plan_data()
    plan_data["row_count_plan"][0]["target_rows"] = 99

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "source is metadata")


def test_row_count_llm_adjusted_without_reasoning_fails() -> None:
    plan_data = _plan_data()
    plan_data["row_count_plan"][0]["source"] = "llm_adjusted"
    plan_data["row_count_plan"][0]["target_rows"] = 12
    plan_data["row_count_plan"][0]["reasoning"] = None

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "requires reasoning")


def test_column_generation_rule_unknown_column_fails() -> None:
    plan_data = _plan_data()
    plan_data["column_generation_rules"][0]["column_name"] = "MissingColumn"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "unknown column")


def test_formula_rule_unknown_target_column_fails() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"][0]["target_column"] = "MissingAmount"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert result.summary.rejected_formula_rules >= 1
    assert _has_issue(result, "target_column")


def test_formula_rule_numeric_operation_on_non_numeric_column_fails() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"][0] = {
        "rule_id": "bad_text_math",
        "rule_type": "row_level",
        "target_table": "Vendor",
        "target_column": "VendorName",
        "operation": "multiply",
        "input_columns": ["VendorName"],
        "source_table": None,
        "source_column": None,
        "relationship_key": None,
        "group_by_columns": [],
        "formula": "VendorName * 2",
        "denominator_column": None,
        "denominator_guard": False,
        "tolerance_type": "none",
        "tolerance_value": None,
        "description": None,
    }

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "numeric-compatible")


def test_aggregate_formula_missing_relationship_key_fails() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"][1]["relationship_key"] = None
    plan_data["formula_rules"][1]["group_by_columns"] = []

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "requires relationship_key")


def test_date_rule_non_date_column_fails() -> None:
    plan_data = _plan_data()
    plan_data["date_rules"] = [
        {
            "rule_id": "bad_date",
            "earlier_table": "Vendor",
            "earlier_column": "VendorName",
            "later_table": "PurchaseOrderHeader",
            "later_column": "OrderDate",
            "min_offset_days": 0,
            "max_offset_days": 5,
            "description": None,
        }
    ]

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "not date-compatible")


def test_quantity_rule_non_numeric_column_fails() -> None:
    plan_data = _plan_data()
    plan_data["quantity_rules"][0]["left_column"] = "CarrierName"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "not numeric-compatible")


def test_status_rule_missing_status_column_fails() -> None:
    plan_data = _plan_data()
    plan_data["status_rules"][0]["status_column"] = "MissingStatus"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert _has_issue(result, "Referenced column MissingStatus")


def test_duplicate_formula_rule_id_fails() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"][1]["rule_id"] = plan_data["formula_rules"][0]["rule_id"]

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert not result.report.is_valid
    assert result.summary.rejected_formula_rules >= 1
    assert _has_issue(result, "Duplicate formula rule_id")


def test_domain_profile_missing_material_categories_warns() -> None:
    plan_data = _plan_data()
    plan_data["domain_profile"]["material_categories"] = []

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert result.report.is_valid
    assert any("material_categories is empty" in issue.message for issue in result.report.warnings)


def test_valid_formula_rules_are_counted_as_accepted() -> None:
    result = validate_generation_plan(_plan(), _schema(), _relationships())

    assert result.summary.accepted_formula_rules == 2


def test_invalid_formula_rules_are_counted_as_rejected() -> None:
    plan_data = _plan_data()
    plan_data["formula_rules"][0]["target_column"] = "MissingAmount"

    result = validate_generation_plan(_plan(plan_data), _schema(), _relationships())

    assert result.summary.rejected_formula_rules == 1


def _has_issue(result, text: str) -> bool:
    return any(text in issue.message for issue in [*result.report.errors, *result.report.warnings])


def _plan(plan_data: dict[str, object] | None = None) -> LLMGenerationPlan:
    return LLMGenerationPlan.model_validate(plan_data or _plan_data())


def _plan_data() -> dict[str, object]:
    return deepcopy(
        {
            "module": "procurement",
            "business_summary": "EV procurement plan.",
            "domain_profile": {
                "industry": "EV manufacturing",
                "business_context": "Procurement lifecycle.",
                "vendor_categories": ["Battery suppliers", "Metal suppliers", "Electronics suppliers"],
                "material_categories": [
                    {
                        "category_name": "Battery Components",
                        "material_examples": ["Lithium-Ion Cell", "Battery PCB", "Thermal Pad", "Copper Busbar", "Cell Spacer"],
                        "specification_patterns": ["21700", "2mm", "Grade A"],
                    }
                ],
                "warehouse_types": ["Raw Material"],
                "plant_locations": ["Bengaluru"],
                "carrier_name_patterns": ["regional freight"],
                "inspection_test_categories": ["Electrical continuity"],
            },
            "table_role_mapping": [
                {"table_name": "Vendor", "table_role": "vendor_dimension", "area": "Master", "confidence": "high", "reasoning": None},
                {
                    "table_name": "PurchaseOrderHeader",
                    "table_role": "purchase_order_header",
                    "area": "Procurement",
                    "confidence": "high",
                    "reasoning": None,
                },
                {
                    "table_name": "PurchaseOrderLine",
                    "table_role": "purchase_order_line",
                    "area": "Procurement",
                    "confidence": "high",
                    "reasoning": None,
                },
                {
                    "table_name": "ShipmentLine",
                    "table_role": "shipment_line",
                    "area": "Logistics",
                    "confidence": "high",
                    "reasoning": None,
                },
            ],
            "generation_order": ["Vendor", "PurchaseOrderHeader", "PurchaseOrderLine", "ShipmentLine"],
            "row_count_plan": [
                {"table_name": "Vendor", "target_rows": 10, "source": "metadata", "reasoning": None},
                {"table_name": "PurchaseOrderHeader", "target_rows": 10, "source": "metadata", "reasoning": None},
                {"table_name": "PurchaseOrderLine", "target_rows": 20, "source": "metadata", "reasoning": None},
                {"table_name": "ShipmentLine", "target_rows": 15, "source": "metadata", "reasoning": None},
            ],
            "column_generation_rules": [
                {
                    "table_name": "Vendor",
                    "column_name": "VendorName",
                    "generation_type": "vendor_name",
                    "strategy": "Domain supplier names.",
                    "allowed_values": [],
                    "min_value": None,
                    "max_value": None,
                    "nullable_strategy": "never_null",
                    "depends_on_columns": [],
                    "notes": None,
                },
                {
                    "table_name": "PurchaseOrderHeader",
                    "column_name": "OrderDate",
                    "generation_type": "date_range",
                    "strategy": "Lifecycle date.",
                    "allowed_values": [],
                    "min_value": None,
                    "max_value": None,
                    "nullable_strategy": "never_null",
                    "depends_on_columns": [],
                    "notes": None,
                },
                {
                    "table_name": "PurchaseOrderHeader",
                    "column_name": "Status",
                    "generation_type": "status",
                    "strategy": "Lifecycle status.",
                    "allowed_values": ["Draft", "Approved", "Closed"],
                    "min_value": None,
                    "max_value": None,
                    "nullable_strategy": "never_null",
                    "depends_on_columns": [],
                    "notes": None,
                },
                {
                    "table_name": "ShipmentLine",
                    "column_name": "CarrierName",
                    "generation_type": "faker_company",
                    "strategy": "Carrier company.",
                    "allowed_values": [],
                    "min_value": None,
                    "max_value": None,
                    "nullable_strategy": None,
                    "depends_on_columns": [],
                    "notes": None,
                },
            ],
            "formula_rules": [
                {
                    "rule_id": "line_amount",
                    "rule_type": "row_level",
                    "target_table": "PurchaseOrderLine",
                    "target_column": "LineAmount",
                    "operation": "multiply",
                    "input_columns": ["OrderedQuantity", "UnitPrice"],
                    "source_table": None,
                    "source_column": None,
                    "relationship_key": None,
                    "group_by_columns": [],
                    "formula": "OrderedQuantity * UnitPrice",
                    "denominator_column": None,
                    "denominator_guard": False,
                    "tolerance_type": "none",
                    "tolerance_value": None,
                    "description": None,
                },
                {
                    "rule_id": "header_total",
                    "rule_type": "aggregate",
                    "target_table": "PurchaseOrderHeader",
                    "target_column": "TotalAmount",
                    "operation": "sum",
                    "input_columns": ["LineAmount"],
                    "source_table": "PurchaseOrderLine",
                    "source_column": "LineAmount",
                    "relationship_key": "PurchaseOrderID",
                    "group_by_columns": ["PurchaseOrderID"],
                    "formula": "SUM(PurchaseOrderLine.LineAmount)",
                    "denominator_column": None,
                    "denominator_guard": False,
                    "tolerance_type": "absolute",
                    "tolerance_value": 0.01,
                    "description": None,
                },
            ],
            "date_rules": [
                {
                    "rule_id": "date_order",
                    "earlier_table": "PurchaseOrderHeader",
                    "earlier_column": "OrderDate",
                    "later_table": "PurchaseOrderHeader",
                    "later_column": "OrderDate",
                    "min_offset_days": 0,
                    "max_offset_days": 0,
                    "description": None,
                }
            ],
            "quantity_rules": [
                {
                    "rule_id": "ship_lte_order",
                    "left_table": "ShipmentLine",
                    "left_column": "ShippedQuantity",
                    "operator": "<=",
                    "right_table": "PurchaseOrderLine",
                    "right_column": "OrderedQuantity",
                    "description": None,
                }
            ],
            "status_rules": [
                {
                    "rule_id": "po_status",
                    "table_name": "PurchaseOrderHeader",
                    "status_column": "Status",
                    "status_values": ["Draft", "Approved", "Closed"],
                    "derivation_logic": "Derived from procurement lifecycle.",
                    "description": None,
                }
            ],
            "validation_rules": [
                {
                    "rule_id": "pk_vendor",
                    "rule_type": "pk_check",
                    "table_name": "Vendor",
                    "column_name": "VendorID",
                    "condition": "VendorID unique",
                    "severity": "error",
                    "description": None,
                }
            ],
            "assumptions": ["Metadata is source of truth."],
            "warnings": [],
        }
    )


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "Vendor": TableContract(
                table_name="Vendor",
                process_order=1,
                area="Master",
                table_role="vendor_dimension",
                target_rows=10,
                columns=[
                    _col("VendorID", "int", "PK", "No", "sequence_id"),
                    _col("VendorName", "varchar(200)", None, "No", "vendor_name"),
                ],
            ),
            "PurchaseOrderHeader": TableContract(
                table_name="PurchaseOrderHeader",
                process_order=2,
                area="Procurement",
                table_role="purchase_order_header",
                target_rows=10,
                columns=[
                    _col("PurchaseOrderID", "int", "PK", "No", "sequence_id"),
                    _col("VendorID", "int", "FK", "No", "foreign_key", related_table="Vendor", related_column="VendorID"),
                    _col("OrderDate", "date", None, "No", "date_range"),
                    _col("Status", "varchar(50)", None, "No", "status", allowed_values=["Draft", "Approved", "Closed"]),
                    _col("TotalAmount", "decimal(18,2)", None, "No", "calculated"),
                ],
            ),
            "PurchaseOrderLine": TableContract(
                table_name="PurchaseOrderLine",
                process_order=3,
                area="Procurement",
                table_role="purchase_order_line",
                target_rows=20,
                columns=[
                    _col("PurchaseOrderLineID", "int", "PK", "No", "sequence_id"),
                    _col("PurchaseOrderID", "int", "FK", "No", "foreign_key", related_table="PurchaseOrderHeader", related_column="PurchaseOrderID"),
                    _col("OrderedQuantity", "int", None, "No", "integer_range"),
                    _col("UnitPrice", "decimal(18,2)", None, "No", "decimal_range"),
                    _col("LineAmount", "decimal(18,2)", None, "No", "calculated"),
                ],
            ),
            "ShipmentLine": TableContract(
                table_name="ShipmentLine",
                process_order=4,
                area="Logistics",
                table_role="shipment_line",
                target_rows=15,
                columns=[
                    _col("ShipmentLineID", "int", "PK", "No", "sequence_id"),
                    _col("PurchaseOrderLineID", "int", "FK", "No", "foreign_key", related_table="PurchaseOrderLine", related_column="PurchaseOrderLineID"),
                    _col("ShippedQuantity", "int", None, "No", "integer_range"),
                    _col("CarrierName", "varchar(100)", None, "Yes", "faker_company"),
                ],
            ),
        }
    )


def _relationships() -> list[RelationshipContract]:
    return [
        RelationshipContract(
            parent_table="Vendor",
            child_table="PurchaseOrderHeader",
            relationship_type="one_to_many",
            mermaid_symbol="||--o{",
            label="supplies",
            raw_line="Vendor ||--o{ PurchaseOrderHeader : supplies",
        ),
        RelationshipContract(
            parent_table="PurchaseOrderHeader",
            child_table="PurchaseOrderLine",
            relationship_type="one_to_many",
            mermaid_symbol="||--o{",
            label="contains",
            raw_line="PurchaseOrderHeader ||--o{ PurchaseOrderLine : contains",
        ),
        RelationshipContract(
            parent_table="PurchaseOrderLine",
            child_table="ShipmentLine",
            relationship_type="one_to_many",
            mermaid_symbol="||--o{",
            label="ships",
            raw_line="PurchaseOrderLine ||--o{ ShipmentLine : ships",
        ),
    ]


def _col(
    name: str,
    data_type: str,
    key_type: str | None,
    nullable: str,
    generation_type: str,
    related_table: str | None = None,
    related_column: str | None = None,
    allowed_values: list[str] | None = None,
) -> ColumnContract:
    return ColumnContract(
        column_name=name,
        data_type=data_type,
        key_type=key_type,
        related_table=related_table,
        related_column=related_column,
        nullable=nullable,
        generation_type=generation_type,
        allowed_values=allowed_values or [],
    )
