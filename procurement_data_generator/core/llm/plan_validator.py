"""Semantic validation for LLMGenerationPlan objects against metadata and ERD."""

from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import dataclass
from typing import Iterable

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import (
    FormulaRule,
    LLMGenerationPlan,
    NormalizedLLMGenerationPlan,
    PlanValidationRule,
)
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.llm.plan_normalizer import get_legacy_module_plan, normalize_llm_generation_plan
from procurement_data_generator.modules.procurement.role_catalog import PROCUREMENT_V1_UNSUPPORTED_MESSAGE, get_procurement_role_catalog
from procurement_data_generator.modules.production.role_catalog import (
    PRODUCTION_V1_EXPECTED_TABLES,
    get_production_role_catalog,
)


NUMERIC_TYPES = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "money", "real")
DATE_TYPES = ("date", "datetime", "datetime2", "timestamp")
STRING_TYPES = ("varchar", "nvarchar", "char", "nchar", "text", "string")
BOOLEAN_TYPES = ("bit", "bool", "boolean")
NUMERIC_OPERATIONS = {"add", "subtract", "multiply", "divide", "sum", "avg", "min", "max", "percentage"}
V2_FORBIDDEN_TABLE = "InventoryBalance"
V2_FORBIDDEN_ROLE = "inventory_balance"
V2_EXPECTED_TABLES = (
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
    "InventoryReceiptDetail",
    "InventoryTransaction",
    "Inventory",
    "SupplierInvoice",
    "PaymentTransaction",
)
V2_KEY_STATUS_COLUMNS = (
    ("PurchaseRequisition", "Status"),
    ("PurchaseReqLine", "LineStatus"),
    ("RFQHeader", "RFQStatus"),
    ("RFQLine", "LineStatus"),
    ("SupplierQuotation", "QuotationStatus"),
    ("SupplierQuotationLn", "LineStatus"),
    ("PurchaseOrderHdr", "POStatus"),
    ("PurchaseOrderLine", "LineStatus"),
    ("POSchedule", "ScheduleStatus"),
    ("ShipmentHdr", "ShipmentStatus"),
    ("GoodsReceiptHeader", "ReceiptStatus"),
    ("IncomingInspection", "InspectionStatus"),
    ("InspectionResult", "ResultStatus"),
    ("InventoryReceiptDetail", "DeliveryStatus"),
    ("InventoryReceiptDetail", "PriceVarianceStatus"),
    ("InventoryReceiptDetail", "InventoryReceiptStatus"),
    ("InventoryTransaction", "TransactionType"),
    ("Inventory", "InventoryStatus"),
    ("SupplierInvoice", "InvoiceStatus"),
    ("PaymentTransaction", "PaymentStatus"),
)
V2_KEY_FORMULAS = (
    ("SupplierQuotationLn", "QuotedLineAmount"),
    ("PurchaseOrderLine", "LineAmount"),
    ("PurchaseOrderHdr", "TotalAmount"),
    ("GoodsReceiptLine", "ShortQuantity"),
    ("InspectionResult", "RejectedQuantity"),
    ("InspectionResult", "RejectionRatePct"),
    ("SupplierInvoice", "TotalInvoiceAmount"),
)
PRODUCTION_V1_OUT_OF_SCOPE_TERMS = (
    "OEE",
    "Downtime",
    "Maintenance",
    "LaborTracking",
    "Warranty",
    "Sales",
    "Customer",
    "Shipment",
)
PRODUCTION_V1_FORMULA_THEMES = {
    "RequiredQuantity = PlannedQuantity * ComponentQuantity": ("requiredquantity", "plannedquantity", "componentquantity"),
    "ScrapAdjustedQuantity = RequiredQuantity * (1 + ScrapFactorPct / 100)": (
        "scrapadjustedquantity",
        "requiredquantity",
        "scrapfactorpct",
    ),
    "IssueValue = IssuedQuantity * UnitCost": ("issuevalue", "issuedquantity", "unitcost"),
    "PassedQuantity + FailedQuantity = TestedQuantity": ("passedquantity", "failedquantity", "testedquantity"),
    "ReceiptValue = GoodQuantity * UnitCost": ("receiptvalue", "goodquantity", "unitcost"),
    "FinishedGoodsInventory.OnHandQuantity rolls up from FinishedGoodsReceipt.GoodQuantity": (
        "finishedgoodsinventory",
        "onhandquantity",
        "finishedgoodsreceipt",
        "goodquantity",
    ),
    "TotalProductionCost = MaterialCost + LaborCost + OverheadCost + ScrapCost": (
        "totalproductioncost",
        "materialcost",
        "laborcost",
        "overheadcost",
        "scrapcost",
    ),
    "UnitProductionCost = TotalProductionCost / GoodQuantity": (
        "unitproductioncost",
        "totalproductioncost",
        "goodquantity",
    ),
}
PRODUCTION_V1_INTEGRATION_THEMES = {
    "Production consumes Procurement Inventory": ("procurement", "inventory"),
    "MaterialIssueLine references InventoryTransaction": ("materialissueline", "inventorytransaction"),
    "MaterialIssueLine references InventoryReceiptDetail": ("materialissueline", "inventoryreceiptdetail"),
    "ProductionGenealogy traces procurement receipt lineage": (
        "productiongenealogy",
        "materialissueline",
        "inventoryreceiptdetail",
        "inventorytransaction",
        "componentmaster",
        "suppliermaster",
    ),
}


@dataclass(frozen=True)
class MetadataFkRelationship:
    """A parent-child relationship inferred from metadata FK columns."""

    parent_table: str
    child_table: str
    child_column: str
    parent_column: str


@dataclass(frozen=True)
class PlanValidationSummary:
    """Counters emitted by Phase 6 plan validation."""

    accepted_formula_rules: int = 0
    rejected_formula_rules: int = 0
    accepted_validation_rules: int = 0
    rejected_validation_rules: int = 0


@dataclass(frozen=True)
class PlanValidationResult:
    """Semantic plan validation result."""

    report: ValidationReport
    summary: PlanValidationSummary


def validate_generation_plan(
    plan: LLMGenerationPlan | NormalizedLLMGenerationPlan | dict,
    schema: SchemaContract,
    relationships: list[RelationshipContract],
    model_version: str = "v2",
) -> PlanValidationResult:
    """Validate an LLMGenerationPlan against metadata, roles, and ERD relationships."""

    if model_version == "v1":
        raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
    report = ValidationReport(
        total_tables_detected=len(schema.tables),
        total_columns_detected=sum(len(table.columns) for table in schema.tables.values()),
    )
    normalized_plan = normalize_llm_generation_plan(plan)
    expected_module = _expected_module(model_version)
    legacy_plan = get_legacy_module_plan(normalized_plan, expected_module)
    if legacy_plan is None and len(normalized_plan.module_set) == 1:
        legacy_plan = get_legacy_module_plan(normalized_plan, normalized_plan.module_set[0])
    if legacy_plan is None:
        report.add_error(
            message=(
                f"Normalized plan does not contain a legacy {expected_module} payload for current semantic validation."
            ),
            suggested_fix=(
                "Provide a legacy module payload under modules[module_id].legacy_plan until Phase 7 "
                "moves semantic validation to normalized module payloads."
            ),
        )
        return PlanValidationResult(report=report, summary=PlanValidationSummary())
    plan = legacy_plan
    fk_relationships = get_fk_relationships_from_schema(schema)

    _validate_module(plan, report, expected_module)
    role_catalog = _role_catalog_for_model(model_version)

    _validate_table_role_mapping(plan, schema, report, role_catalog)
    _validate_generation_order(plan, schema, fk_relationships, report)
    _validate_row_count_plan(plan, schema, report)
    _validate_column_generation_rules(plan, schema, report)
    accepted_formula_rules, rejected_formula_rules = _validate_formula_rules(
        plan, schema, relationships, fk_relationships, report
    )
    _validate_date_rules(plan, schema, report)
    _validate_quantity_rules(plan, schema, relationships, fk_relationships, report)
    _validate_status_rules(plan, schema, report)
    accepted_validation_rules, rejected_validation_rules = _validate_plan_validation_rules(plan, schema, report)
    _validate_domain_profile(plan, schema, report)
    if model_version == "v2":
        _validate_v2_plan(plan, schema, report)
    if model_version == "production_v1":
        _validate_production_v1_plan(plan, schema, report)

    return PlanValidationResult(
        report=report,
        summary=PlanValidationSummary(
            accepted_formula_rules=accepted_formula_rules,
            rejected_formula_rules=rejected_formula_rules,
            accepted_validation_rules=accepted_validation_rules,
            rejected_validation_rules=rejected_validation_rules,
        ),
    )


def format_plan_validation_result(result: PlanValidationResult) -> str:
    """Format plan validation output for CLI usage."""

    report = result.report
    summary = result.summary
    lines = [
        "Plan validation completed.",
        f"Plan status: {'valid' if report.is_valid else 'invalid'}",
        f"Errors: {len(report.errors)}",
        f"Warnings: {len(report.warnings)}",
        f"Accepted formula rules: {summary.accepted_formula_rules}",
        f"Rejected formula rules: {summary.rejected_formula_rules}",
        f"Accepted validation rules: {summary.accepted_validation_rules}",
        f"Rejected validation rules: {summary.rejected_validation_rules}",
    ]

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, issue in enumerate(report.warnings, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))

    return "\n".join(lines)


def table_exists(schema: SchemaContract, table_name: str) -> bool:
    return table_name in schema.tables


def get_table(schema: SchemaContract, table_name: str) -> TableContract | None:
    return schema.tables.get(table_name)


def column_exists(schema: SchemaContract, table_name: str, column_name: str) -> bool:
    table = get_table(schema, table_name)
    return table is not None and any(column.column_name == column_name for column in table.columns)


def get_column(schema: SchemaContract, table_name: str, column_name: str) -> ColumnContract | None:
    table = get_table(schema, table_name)
    if table is None:
        return None
    return next((column for column in table.columns if column.column_name == column_name), None)


def is_numeric_type(data_type: str) -> bool:
    normalized = _normalize_data_type(data_type)
    return any(normalized.startswith(type_name) for type_name in NUMERIC_TYPES)


def is_date_type(data_type: str) -> bool:
    normalized = _normalize_data_type(data_type)
    return any(normalized.startswith(type_name) for type_name in DATE_TYPES)


def is_string_type(data_type: str) -> bool:
    normalized = _normalize_data_type(data_type)
    return any(normalized.startswith(type_name) for type_name in STRING_TYPES)


def is_boolean_type(data_type: str) -> bool:
    normalized = _normalize_data_type(data_type)
    return any(normalized.startswith(type_name) for type_name in BOOLEAN_TYPES)


def get_fk_relationships_from_schema(schema: SchemaContract) -> list[MetadataFkRelationship]:
    relationships: list[MetadataFkRelationship] = []
    for table in schema.tables.values():
        for column in table.columns:
            if column.key_type == "FK" and column.related_table and column.related_column:
                relationships.append(
                    MetadataFkRelationship(
                        parent_table=column.related_table,
                        child_table=table.table_name,
                        child_column=column.column_name,
                        parent_column=column.related_column,
                    )
                )
    return relationships


def has_direct_relationship(
    table_a: str,
    table_b: str,
    fk_relationships: list[MetadataFkRelationship],
    erd_relationships: list[RelationshipContract],
) -> bool:
    return any(
        relationship.parent_table == table_a and relationship.child_table == table_b
        or relationship.parent_table == table_b and relationship.child_table == table_a
        for relationship in fk_relationships
    ) or any(
        relationship.parent_table == table_a and relationship.child_table == table_b
        or relationship.parent_table == table_b and relationship.child_table == table_a
        for relationship in erd_relationships
    )


def has_relationship_between(
    table_a: str,
    table_b: str,
    fk_relationships: list[MetadataFkRelationship],
    erd_relationships: list[RelationshipContract],
) -> bool:
    if table_a == table_b:
        return True
    adjacency: dict[str, set[str]] = {}
    for relationship in fk_relationships:
        adjacency.setdefault(relationship.parent_table, set()).add(relationship.child_table)
        adjacency.setdefault(relationship.child_table, set()).add(relationship.parent_table)
    for relationship in erd_relationships:
        adjacency.setdefault(relationship.parent_table, set()).add(relationship.child_table)
        adjacency.setdefault(relationship.child_table, set()).add(relationship.parent_table)

    visited = {table_a}
    queue: deque[str] = deque([table_a])
    while queue:
        table = queue.popleft()
        for neighbor in adjacency.get(table, set()):
            if neighbor == table_b:
                return True
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return False


def _expected_module(model_version: str) -> str:
    return "production" if model_version == "production_v1" else "procurement"


def _role_catalog_for_model(model_version: str) -> dict:
    if model_version == "production_v1":
        return get_production_role_catalog(model_version)
    return get_procurement_role_catalog(model_version)


def _validate_module(plan: LLMGenerationPlan, report: ValidationReport, expected_module: str) -> None:
    if plan.module != expected_module:
        report.add_error(
            message=f"Plan module must be {expected_module}.",
            suggested_fix=f"Set module to {expected_module}.",
        )


def _validate_table_role_mapping(
    plan: LLMGenerationPlan,
    schema: SchemaContract,
    report: ValidationReport,
    role_catalog: dict,
) -> None:
    mapping_tables = [mapping.table_name for mapping in plan.table_role_mapping]
    mapping_roles = [mapping.table_role for mapping in plan.table_role_mapping]
    _add_duplicate_errors(mapping_tables, "table_role_mapping table", report)
    _add_duplicate_errors(mapping_roles, "table_role_mapping role", report)

    for mapping in plan.table_role_mapping:
        table = get_table(schema, mapping.table_name)
        if table is None:
            report.add_error(
                table_name=mapping.table_name,
                message=f"Plan references table {mapping.table_name}, but it does not exist in metadata.",
                suggested_fix="Use an exact TableName from metadata.",
            )
            continue
        if mapping.table_role != table.table_role:
            report.add_error(
                table_name=mapping.table_name,
                message=(
                    f"Plan maps {mapping.table_name} to role {mapping.table_role}, "
                    f"but metadata role is {table.table_role}."
                ),
                suggested_fix=f"Set table_role to {table.table_role}.",
            )
        if mapping.area != table.area:
            report.add_error(
                table_name=mapping.table_name,
                message=(
                    f"Plan maps {mapping.table_name} area as {mapping.area}, "
                    f"but metadata area is {table.area}."
                ),
                suggested_fix=f"Set area to {table.area}.",
            )
        if mapping.table_role not in role_catalog:
            report.add_error(
                table_name=mapping.table_name,
                message=f"Unsupported table role in plan: {mapping.table_role}.",
                suggested_fix="Use a role from the active model role catalog.",
            )

    missing_tables = [table_name for table_name in schema.tables if table_name not in set(mapping_tables)]
    for table_name in missing_tables:
        report.add_error(
            table_name=table_name,
            message=f"Metadata table {table_name} is missing from table_role_mapping.",
            suggested_fix="Add one table_role_mapping entry for every metadata table.",
        )


def _validate_generation_order(
    plan: LLMGenerationPlan,
    schema: SchemaContract,
    fk_relationships: list[MetadataFkRelationship],
    report: ValidationReport,
) -> None:
    order = plan.generation_order
    if not order:
        report.add_error(
            message="generation_order is empty.",
            suggested_fix="Provide every metadata table exactly once in generation_order.",
        )
        return

    _add_duplicate_errors(order, "generation_order table", report)
    known_order_tables = [table_name for table_name in order if table_name in schema.tables]
    for table_name in order:
        if table_name not in schema.tables:
            report.add_error(
                table_name=table_name,
                message=f"generation_order references unknown table {table_name}.",
                suggested_fix="Use exact metadata table names in generation_order.",
            )

    for table_name in schema.tables:
        if table_name not in set(order):
            report.add_error(
                table_name=table_name,
                message=f"Metadata table {table_name} is missing from generation_order.",
                suggested_fix="Include every metadata table exactly once in generation_order.",
            )

    positions = {table_name: index for index, table_name in enumerate(order)}
    for relationship in fk_relationships:
        if relationship.parent_table in positions and relationship.child_table in positions:
            if positions[relationship.parent_table] > positions[relationship.child_table]:
                report.add_error(
                    table_name=relationship.child_table,
                    column_name=relationship.child_column,
                    message=(
                        "FK dependency order violation: "
                        f"{relationship.parent_table} must appear before {relationship.child_table}."
                    ),
                    suggested_fix="Move parent tables before child tables in generation_order.",
                )

    expected_process_order = [table.table_name for table in schema.ordered_tables]
    if set(known_order_tables) == set(schema.tables) and known_order_tables != expected_process_order:
        report.add_warning(
            message="generation_order differs from metadata ProcessOrder.",
            suggested_fix="Prefer metadata ProcessOrder unless FK dependencies require a different order.",
        )


def _validate_row_count_plan(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    entries_by_table = [entry.table_name for entry in plan.row_count_plan]
    _add_duplicate_errors(entries_by_table, "row_count_plan table", report)

    for entry in plan.row_count_plan:
        table = get_table(schema, entry.table_name)
        if table is None:
            report.add_error(
                table_name=entry.table_name,
                message=f"row_count_plan references unknown table {entry.table_name}.",
                suggested_fix="Use exact metadata table names in row_count_plan.",
            )
            continue
        if entry.source == "metadata" and entry.target_rows != table.target_rows:
            report.add_error(
                table_name=entry.table_name,
                message=(
                    f"row_count_plan source is metadata but target_rows is {entry.target_rows}; "
                    f"metadata TargetRows is {table.target_rows}."
                ),
                suggested_fix="Use the metadata TargetRows value or change source and provide reasoning.",
            )
        if entry.source in {"llm_adjusted", "derived_from_parent"}:
            if not _has_text(entry.reasoning):
                report.add_error(
                    table_name=entry.table_name,
                    message=f"row_count_plan source {entry.source} requires reasoning.",
                    suggested_fix="Provide non-blank reasoning for adjusted or derived row counts.",
                )
            else:
                report.add_warning(
                    table_name=entry.table_name,
                    message=f"row_count_plan uses {entry.source} for {entry.table_name}.",
                    suggested_fix="Confirm this row count is intentional during plan review.",
                )

    for table_name in schema.tables:
        if table_name not in set(entries_by_table):
            report.add_error(
                table_name=table_name,
                message=f"Metadata table {table_name} is missing from row_count_plan.",
                suggested_fix="Add one row_count_plan entry for every metadata table.",
            )


def _validate_column_generation_rules(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    rule_keys: set[tuple[str, str]] = set()
    for rule in plan.column_generation_rules:
        table = get_table(schema, rule.table_name)
        if table is None:
            report.add_error(
                table_name=rule.table_name,
                column_name=rule.column_name,
                message=f"ColumnGenerationRule references unknown table {rule.table_name}.",
                suggested_fix="Use exact metadata table names.",
            )
            continue
        column = get_column(schema, rule.table_name, rule.column_name)
        if column is None:
            report.add_error(
                table_name=rule.table_name,
                column_name=rule.column_name,
                message=f"ColumnGenerationRule references unknown column {rule.column_name}.",
                suggested_fix="Use exact column names from the metadata table.",
            )
            continue
        rule_keys.add((rule.table_name, rule.column_name))
        if rule.generation_type != column.generation_type:
            report.add_warning(
                table_name=rule.table_name,
                column_name=rule.column_name,
                message=(
                    f"Plan generation_type {rule.generation_type} differs from metadata "
                    f"GenerationType {column.generation_type}."
                ),
                suggested_fix="Prefer the metadata GenerationType unless there is a deliberate plan reason.",
            )
        for dependency in rule.depends_on_columns:
            if not column_exists(schema, rule.table_name, dependency):
                report.add_error(
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    message=f"depends_on_columns references unknown same-table column {dependency}.",
                    suggested_fix="Use dependencies that exist in the same metadata table.",
                )
        if rule.allowed_values and rule.generation_type not in {"category", "status"}:
            report.add_warning(
                table_name=rule.table_name,
                column_name=rule.column_name,
                message="allowed_values are usually only appropriate for category or status generation types.",
                suggested_fix="Remove allowed_values or use a category/status generation type.",
            )
        if column.allowed_values and rule.allowed_values:
            disallowed = sorted(set(rule.allowed_values) - set(column.allowed_values))
            if disallowed:
                report.add_warning(
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    message=f"Plan allowed_values include values not listed in metadata: {', '.join(disallowed)}.",
                    suggested_fix="Use metadata AllowedValues or explain compatibility in notes.",
                )
        if column.nullable == "No" and _nullable_strategy_allows_null(rule.nullable_strategy):
            report.add_error(
                table_name=rule.table_name,
                column_name=rule.column_name,
                message="nullable_strategy contradicts metadata Nullable = No.",
                suggested_fix="Use a non-null strategy for required metadata columns.",
            )

    for table in schema.tables.values():
        for column in table.columns:
            if column.key_type in {"PK", "FK"} or column.generation_type == "calculated":
                continue
            if (table.table_name, column.column_name) not in rule_keys:
                report.add_warning(
                    table_name=table.table_name,
                    column_name=column.column_name,
                    message="Metadata column is missing a column_generation_rule.",
                    suggested_fix="Add a column_generation_rule or confirm this column is handled by a later phase.",
                )


def _validate_formula_rules(
    plan: LLMGenerationPlan,
    schema: SchemaContract,
    erd_relationships: list[RelationshipContract],
    fk_relationships: list[MetadataFkRelationship],
    report: ValidationReport,
) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    seen_rule_ids: set[str] = set()

    for rule in plan.formula_rules:
        before_errors = len(report.errors)
        if rule.rule_id in seen_rule_ids:
            _formula_error(report, rule, "Duplicate formula rule_id.", "Use a unique rule_id for every formula rule.")
        seen_rule_ids.add(rule.rule_id)

        target_column = _validate_formula_target(rule, schema, report)
        if rule.rule_type == "row_level":
            _validate_row_level_formula(rule, schema, target_column, report)
        elif rule.rule_type == "aggregate":
            _validate_aggregate_formula(rule, schema, target_column, erd_relationships, fk_relationships, report)
        elif rule.rule_type == "date_diff":
            _validate_date_diff_formula(rule, schema, target_column, report)
        elif rule.rule_type == "percentage":
            _validate_percentage_formula(rule, schema, target_column, report)
        elif rule.rule_type == "inventory_balance":
            _validate_inventory_balance_formula(rule, schema, target_column, report)
        elif rule.rule_type == "quantity_reconciliation":
            _validate_quantity_reconciliation_formula(rule, schema, target_column, report)

        if len(report.errors) == before_errors:
            accepted += 1
        else:
            rejected += 1

    return accepted, rejected


def _validate_formula_target(
    rule: FormulaRule,
    schema: SchemaContract,
    report: ValidationReport,
) -> ColumnContract | None:
    if not table_exists(schema, rule.target_table):
        _formula_error(report, rule, f"Formula target_table {rule.target_table} does not exist.", "Use a metadata table.")
        return None
    target_column = get_column(schema, rule.target_table, rule.target_column)
    if target_column is None:
        _formula_error(
            report,
            rule,
            f"Formula target_column {rule.target_column} does not exist in {rule.target_table}.",
            "Use an existing target column from metadata.",
        )
    return target_column


def _validate_row_level_formula(
    rule: FormulaRule,
    schema: SchemaContract,
    target_column: ColumnContract | None,
    report: ValidationReport,
) -> None:
    input_columns = _existing_columns(rule.input_columns, rule.target_table, schema, rule, report)
    if rule.operation in NUMERIC_OPERATIONS:
        _require_numeric_columns(input_columns, report, rule)
        if target_column is not None and not is_numeric_type(target_column.data_type):
            _formula_error(report, rule, "Formula target column should be numeric-compatible.", "Use a numeric target column.")


def _validate_aggregate_formula(
    rule: FormulaRule,
    schema: SchemaContract,
    target_column: ColumnContract | None,
    erd_relationships: list[RelationshipContract],
    fk_relationships: list[MetadataFkRelationship],
    report: ValidationReport,
) -> None:
    if not rule.source_table or not table_exists(schema, rule.source_table):
        _formula_error(report, rule, "Aggregate formula requires an existing source_table.", "Set source_table to a metadata table.")
        return
    if not rule.source_column or not column_exists(schema, rule.source_table, rule.source_column):
        _formula_error(report, rule, "Aggregate formula requires an existing source_column.", "Set source_column to a metadata column.")
        return
    source_column = get_column(schema, rule.source_table, rule.source_column)
    if rule.operation in {"sum", "avg", "min", "max"} and source_column and not is_numeric_type(source_column.data_type):
        _formula_error(report, rule, "Aggregate source_column should be numeric-compatible.", "Use a numeric source column.")
    if target_column is not None and rule.operation in {"sum", "avg", "min", "max"} and not is_numeric_type(target_column.data_type):
        _formula_error(report, rule, "Aggregate target_column should be numeric-compatible.", "Use a numeric target column.")
    if rule.relationship_key:
        if not column_exists(schema, rule.source_table, rule.relationship_key) or not column_exists(
            schema, rule.target_table, rule.relationship_key
        ):
            _formula_error(
                report,
                rule,
                f"relationship_key {rule.relationship_key} must exist in source and target tables.",
                "Use a key column present in both aggregate source and target tables.",
            )
    else:
        valid_group_keys = [
            column_name
            for column_name in rule.group_by_columns
            if column_exists(schema, rule.source_table, column_name) and column_exists(schema, rule.target_table, column_name)
        ]
        if not valid_group_keys:
            _formula_error(
                report,
                rule,
                "Aggregate formula requires relationship_key or group_by_columns present in source and target tables.",
                "Provide a valid aggregation key.",
            )
    if not has_relationship_between(rule.source_table, rule.target_table, fk_relationships, erd_relationships):
        report.add_warning(
            table_name=rule.target_table,
            column_name=rule.target_column,
            message=f"Rule {rule.rule_id}: no metadata/ERD relationship path between {rule.source_table} and {rule.target_table}.",
            suggested_fix="Confirm the aggregation path or add relationship metadata/ERD support.",
        )


def _validate_date_diff_formula(
    rule: FormulaRule,
    schema: SchemaContract,
    target_column: ColumnContract | None,
    report: ValidationReport,
) -> None:
    input_columns = _existing_columns(rule.input_columns, rule.target_table, schema, rule, report)
    for column in input_columns:
        if not is_date_type(column.data_type):
            _formula_error(report, rule, "date_diff input columns should be date-compatible.", "Use date/datetime input columns.")
    if target_column is not None and not is_numeric_type(target_column.data_type):
        _formula_error(report, rule, "date_diff target column should be numeric-compatible.", "Use a numeric days column.")


def _validate_percentage_formula(
    rule: FormulaRule,
    schema: SchemaContract,
    target_column: ColumnContract | None,
    report: ValidationReport,
) -> None:
    input_columns = _existing_columns(rule.input_columns, rule.target_table, schema, rule, report)
    _require_numeric_columns(input_columns, report, rule)
    if target_column is not None and not is_numeric_type(target_column.data_type):
        _formula_error(report, rule, "Percentage target column should be numeric-compatible.", "Use a numeric target column.")
    if rule.denominator_column and not column_exists(schema, rule.target_table, rule.denominator_column):
        _formula_error(report, rule, "denominator_column does not exist in target_table.", "Use an existing denominator column.")
    if not rule.denominator_guard:
        report.add_warning(
            table_name=rule.target_table,
            column_name=rule.target_column,
            message=f"Rule {rule.rule_id}: percentage/divide rule should use denominator_guard.",
            suggested_fix="Set denominator_guard to true when division is possible.",
        )


def _validate_inventory_balance_formula(
    rule: FormulaRule,
    schema: SchemaContract,
    target_column: ColumnContract | None,
    report: ValidationReport,
) -> None:
    target_table = get_table(schema, rule.target_table)
    source_table = get_table(schema, rule.source_table) if rule.source_table else None
    if target_table and target_table.table_role != "inventory_balance":
        report.add_warning(
            table_name=rule.target_table,
            column_name=rule.target_column,
            message=f"Rule {rule.rule_id}: inventory_balance rule usually targets inventory_balance role.",
            suggested_fix="Confirm target table role or use a different rule_type.",
        )
    if source_table and source_table.table_role != "inventory_transaction":
        report.add_warning(
            table_name=rule.target_table,
            column_name=rule.target_column,
            message=f"Rule {rule.rule_id}: inventory_balance rule usually uses inventory_transaction source.",
            suggested_fix="Confirm source table role or use a different rule_type.",
        )
    if rule.operation != "sum":
        report.add_warning(
            table_name=rule.target_table,
            column_name=rule.target_column,
            message=f"Rule {rule.rule_id}: inventory_balance operation is usually sum.",
            suggested_fix="Use sum unless the plan has a clear reason.",
        )
    if target_column is not None and not is_numeric_type(target_column.data_type):
        _formula_error(report, rule, "Inventory balance target column should be numeric-compatible.", "Use a numeric target column.")
    if rule.source_table and rule.source_column:
        source_column = get_column(schema, rule.source_table, rule.source_column)
        if source_column is None:
            _formula_error(report, rule, "Inventory balance source_column does not exist.", "Use an existing source column.")
        elif not is_numeric_type(source_column.data_type):
            _formula_error(report, rule, "Inventory balance source_column should be numeric-compatible.", "Use a numeric source column.")
    for column_name in rule.group_by_columns:
        if rule.source_table and not column_exists(schema, rule.source_table, column_name):
            _formula_error(report, rule, f"group_by column {column_name} missing from source_table.", "Use existing source group_by columns.")
        if not column_exists(schema, rule.target_table, column_name):
            _formula_error(report, rule, f"group_by column {column_name} missing from target_table.", "Use existing target group_by columns.")


def _validate_quantity_reconciliation_formula(
    rule: FormulaRule,
    schema: SchemaContract,
    target_column: ColumnContract | None,
    report: ValidationReport,
) -> None:
    input_columns = _existing_columns(rule.input_columns, rule.target_table, schema, rule, report)
    _require_numeric_columns(input_columns, report, rule)
    if target_column is not None and not is_numeric_type(target_column.data_type):
        _formula_error(report, rule, "Quantity reconciliation target should be numeric-compatible.", "Use a numeric target column.")


def _validate_date_rules(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    for rule in plan.date_rules:
        earlier_column = _require_column(schema, rule.earlier_table, rule.earlier_column, report)
        later_column = _require_column(schema, rule.later_table, rule.later_column, report)
        if earlier_column and not is_date_type(earlier_column.data_type):
            report.add_error(
                table_name=rule.earlier_table,
                column_name=rule.earlier_column,
                message=f"DateRule {rule.rule_id} earlier_column is not date-compatible.",
                suggested_fix="Use a date/datetime metadata column.",
            )
        if later_column and not is_date_type(later_column.data_type):
            report.add_error(
                table_name=rule.later_table,
                column_name=rule.later_column,
                message=f"DateRule {rule.rule_id} later_column is not date-compatible.",
                suggested_fix="Use a date/datetime metadata column.",
            )
        if (
            rule.min_offset_days is not None
            and rule.max_offset_days is not None
            and rule.max_offset_days < rule.min_offset_days
        ):
            report.add_error(
                message=f"DateRule {rule.rule_id} max_offset_days is less than min_offset_days.",
                suggested_fix="Set max_offset_days greater than or equal to min_offset_days.",
            )


def _validate_quantity_rules(
    plan: LLMGenerationPlan,
    schema: SchemaContract,
    erd_relationships: list[RelationshipContract],
    fk_relationships: list[MetadataFkRelationship],
    report: ValidationReport,
) -> None:
    for rule in plan.quantity_rules:
        left_column = _require_column(schema, rule.left_table, rule.left_column, report)
        right_column = _require_column(schema, rule.right_table, rule.right_column, report)
        if left_column and not is_numeric_type(left_column.data_type):
            report.add_error(
                table_name=rule.left_table,
                column_name=rule.left_column,
                message=f"QuantityRule {rule.rule_id} left_column is not numeric-compatible.",
                suggested_fix="Use a numeric quantity column.",
            )
        if right_column and not is_numeric_type(right_column.data_type):
            report.add_error(
                table_name=rule.right_table,
                column_name=rule.right_column,
                message=f"QuantityRule {rule.rule_id} right_column is not numeric-compatible.",
                suggested_fix="Use a numeric quantity column.",
            )
        if rule.left_table != rule.right_table and table_exists(schema, rule.left_table) and table_exists(schema, rule.right_table):
            if not has_relationship_between(rule.left_table, rule.right_table, fk_relationships, erd_relationships):
                report.add_warning(
                    table_name=rule.left_table,
                    column_name=rule.left_column,
                    message=f"QuantityRule {rule.rule_id} has no relationship path between compared tables.",
                    suggested_fix="Confirm the lifecycle relationship or add FK/ERD support.",
                )


def _validate_status_rules(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    for rule in plan.status_rules:
        column = _require_column(schema, rule.table_name, rule.status_column, report)
        if column is None:
            continue
        if not is_string_type(column.data_type):
            report.add_error(
                table_name=rule.table_name,
                column_name=rule.status_column,
                message=f"StatusRule {rule.rule_id} status_column is not string/category-compatible.",
                suggested_fix="Use a varchar/nvarchar/string status column.",
            )
        if not rule.status_values:
            report.add_error(
                table_name=rule.table_name,
                column_name=rule.status_column,
                message=f"StatusRule {rule.rule_id} has empty status_values.",
                suggested_fix="Provide allowed lifecycle status values.",
            )
        if column.allowed_values:
            extra_values = sorted(set(rule.status_values) - set(column.allowed_values))
            if extra_values:
                report.add_warning(
                    table_name=rule.table_name,
                    column_name=rule.status_column,
                    message=f"StatusRule {rule.rule_id} includes values not present in metadata AllowedValues: {', '.join(extra_values)}.",
                    suggested_fix="Use metadata AllowedValues unless the plan explains compatibility.",
                )


def _validate_plan_validation_rules(
    plan: LLMGenerationPlan,
    schema: SchemaContract,
    report: ValidationReport,
) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    seen_rule_ids: set[str] = set()
    for rule in plan.validation_rules:
        before_errors = len(report.errors)
        if rule.rule_id in seen_rule_ids:
            _validation_rule_error(report, rule, "Duplicate validation rule_id.", "Use a unique rule_id.")
        seen_rule_ids.add(rule.rule_id)
        if rule.table_name and not table_exists(schema, rule.table_name):
            _validation_rule_error(report, rule, f"Validation rule table {rule.table_name} does not exist.", "Use a metadata table.")
        if rule.column_name:
            if not rule.table_name:
                if not _is_allowed_global_validation_column(rule):
                    _validation_rule_error(report, rule, "column_name is provided without table_name.", "Provide table_name with column_name.")
            elif not column_exists(schema, rule.table_name, rule.column_name):
                _validation_rule_error(report, rule, f"Validation rule column {rule.column_name} does not exist.", "Use a metadata column.")
        if not _has_text(rule.condition):
            _validation_rule_error(report, rule, "Validation rule condition is blank.", "Provide a non-blank condition.")
        if len(report.errors) == before_errors:
            accepted += 1
        else:
            rejected += 1
    return accepted, rejected


def _is_allowed_global_validation_column(rule: PlanValidationRule) -> bool:
    """Allow narrowly scoped global v2 validation rules such as CurrencyCode = USD."""

    column_name = (rule.column_name or "").lower()
    condition = (rule.condition or "").lower()
    if column_name == "currencycode" and "usd" in condition:
        return True
    if column_name in {"suppliercountry", "plantcountry", "warehousecountry"} and "usa" in condition:
        return True
    return False


def _validate_domain_profile(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    profile = plan.domain_profile
    if not _has_text(profile.industry):
        report.add_error(
            message="domain_profile.industry is blank.",
            suggested_fix="Provide the procurement industry inferred from the scenario.",
        )
    if not profile.vendor_categories:
        report.add_warning(
            message="domain_profile.vendor_categories is empty.",
            suggested_fix="Provide vendor category guidance for name generation.",
        )
    if not profile.material_categories:
        report.add_warning(
            message="domain_profile.material_categories is empty.",
            suggested_fix="Provide material categories and examples for domain-aware names.",
        )
    for category in profile.material_categories:
        if not category.material_examples:
            report.add_warning(
                message=f"Material category {category.category_name} has no material_examples.",
                suggested_fix="Add realistic material examples for this category.",
            )
    if not profile.warehouse_types:
        report.add_warning(
            message="domain_profile.warehouse_types is empty.",
            suggested_fix="Provide warehouse function/type guidance.",
        )
    if not profile.plant_locations:
        report.add_warning(
            message="domain_profile.plant_locations is empty.",
            suggested_fix="Provide plant location guidance.",
        )

    vendor_target = _target_rows_for_role(schema, "vendor_dimension")
    material_target = _target_rows_for_role(schema, "material_dimension")
    plant_target = _target_rows_for_role(schema, "plant_dimension")
    material_example_count = sum(len(category.material_examples) for category in profile.material_categories)
    if vendor_target and profile.vendor_categories and len(profile.vendor_categories) < min(vendor_target, 3):
        report.add_warning(
            message="vendor_categories may be too few for the Vendor target rows.",
            suggested_fix="Provide enough vendor category variety for realistic unique names.",
        )
    if material_target and material_example_count and material_example_count < min(material_target, 5):
        report.add_warning(
            message="material_examples may be too few for the RawMaterial target rows.",
            suggested_fix="Provide more material examples/specification patterns for unique names.",
        )
    if plant_target and profile.plant_locations and len(profile.plant_locations) < plant_target:
        report.add_warning(
            message="plant_locations are fewer than Plant target rows.",
            suggested_fix="Provide at least as many plant locations as planned plant records or explain reuse.",
        )


def _validate_v2_plan(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    _validate_v2_inventory_balance_absent(plan, report)
    _validate_v2_expected_tables(schema, report)
    _validate_v2_generation_order(plan, report)
    _validate_v2_row_counts(plan, report)
    _validate_v2_column_rules(plan, schema, report)
    _validate_v2_formula_expectations(plan, schema, report)
    _validate_v2_status_expectations(plan, schema, report)
    _validate_v2_domain_profile(plan, schema, report)
    _validate_v2_validation_rule_themes(plan, report)


def _validate_v2_inventory_balance_absent(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    if any(mapping.table_name == V2_FORBIDDEN_TABLE or mapping.table_role == V2_FORBIDDEN_ROLE for mapping in plan.table_role_mapping):
        report.add_error(
            table_name=V2_FORBIDDEN_TABLE,
            message="Procurement v2 plans must not include InventoryBalance or inventory_balance role.",
            suggested_fix="Remove InventoryBalance from table_role_mapping and use InventoryTransaction only.",
        )
    containers = [
        ("generation_order", plan.generation_order),
        ("row_count_plan", [entry.table_name for entry in plan.row_count_plan]),
        ("column_generation_rules", [rule.table_name for rule in plan.column_generation_rules]),
        ("formula_rules", [rule.target_table for rule in plan.formula_rules] + [rule.source_table or "" for rule in plan.formula_rules]),
        ("date_rules", [rule.earlier_table for rule in plan.date_rules] + [rule.later_table for rule in plan.date_rules]),
        ("quantity_rules", [rule.left_table for rule in plan.quantity_rules] + [rule.right_table for rule in plan.quantity_rules]),
        ("status_rules", [rule.table_name for rule in plan.status_rules]),
        ("validation_rules", [rule.table_name or "" for rule in plan.validation_rules] + [rule.condition for rule in plan.validation_rules]),
    ]
    for container_name, values in containers:
        if any(V2_FORBIDDEN_TABLE in value for value in values):
            report.add_error(
                table_name=V2_FORBIDDEN_TABLE,
                message=f"Procurement v2 plan references InventoryBalance in {container_name}.",
                suggested_fix="Remove InventoryBalance references; v2 does not include InventoryBalance.",
            )


def _validate_v2_expected_tables(schema: SchemaContract, report: ValidationReport) -> None:
    table_names = set(schema.tables)
    missing = [table_name for table_name in V2_EXPECTED_TABLES if table_name not in table_names]
    extras = sorted(table_names - set(V2_EXPECTED_TABLES))
    for table_name in missing:
        report.add_error(
            table_name=table_name,
            message=f"Procurement v2 metadata is missing expected table {table_name}.",
            suggested_fix="Use the 25-table Procurement v2 metadata model.",
        )
    for table_name in extras:
        report.add_error(
            table_name=table_name,
            message=f"Procurement v2 metadata includes unsupported table {table_name}.",
            suggested_fix="Use exactly the 25 Procurement v2 tables.",
        )


def _validate_v2_generation_order(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    if set(plan.generation_order) == set(V2_EXPECTED_TABLES) and len(plan.generation_order) == len(V2_EXPECTED_TABLES):
        return
    missing = [table_name for table_name in V2_EXPECTED_TABLES if table_name not in plan.generation_order]
    for table_name in missing:
        report.add_error(
            table_name=table_name,
            message=f"Procurement v2 generation_order is missing {table_name}.",
            suggested_fix="Include all 25 v2 tables exactly once in generation_order.",
        )


def _validate_v2_row_counts(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    total = sum(entry.target_rows for entry in plan.row_count_plan)
    if total > 100000:
        report.add_warning(
            message=f"Procurement v2 total planned rows are high: {total}.",
            suggested_fix="Confirm the row volume is intentional for local generation.",
        )


def _validate_v2_column_rules(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    covered = {(rule.table_name, rule.column_name) for rule in plan.column_generation_rules}
    for rule in plan.column_generation_rules:
        column = get_column(schema, rule.table_name, rule.column_name)
        if column is None:
            continue
        if rule.column_name == "CurrencyCode":
            values = {value.upper() for value in rule.allowed_values}
            strategy = f"{rule.strategy} {rule.notes or ''}".upper()
            if values and values != {"USD"}:
                report.add_error(
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    message="Procurement v2 CurrencyCode generation must be USD-only.",
                    suggested_fix="Use allowed_values ['USD'] or a strategy that always emits USD.",
                )
            elif not values and "USD" not in strategy:
                report.add_warning(
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    message="Procurement v2 CurrencyCode rule should explicitly mention USD.",
                    suggested_fix="Set allowed_values to ['USD'] or mention USD in strategy.",
                )
        if rule.column_name in {"SupplierCountry", "PlantCountry", "WarehouseCountry"}:
            values = {value.upper() for value in rule.allowed_values}
            strategy = f"{rule.strategy} {rule.notes or ''}".upper()
            if values and values != {"USA"}:
                report.add_error(
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    message="Procurement v2 country generation must be USA-only.",
                    suggested_fix="Use allowed_values ['USA'] for Supplier/Plant/Warehouse country columns.",
                )
            elif not values and "USA" not in strategy:
                report.add_warning(
                    table_name=rule.table_name,
                    column_name=rule.column_name,
                    message="Procurement v2 country rule should explicitly mention USA.",
                    suggested_fix="Set allowed_values to ['USA'] or mention USA in strategy.",
                )
    for column_name in ["WarehouseLocation", "WarehouseCity", "WarehouseState", "WarehouseCountry", "WarehouseZipCode"]:
        if ("Warehouse", column_name) not in covered:
            report.add_warning(
                table_name="Warehouse",
                column_name=column_name,
                message="Procurement v2 plan is missing a Warehouse location column_generation_rule.",
                suggested_fix="Add warehouse location generation rules that align with PlantID.",
            )


def _validate_v2_formula_expectations(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    formula_targets = {(rule.target_table, rule.target_column): rule for rule in plan.formula_rules}
    for target in V2_KEY_FORMULAS:
        if target not in formula_targets:
            report.add_warning(
                table_name=target[0],
                column_name=target[1],
                message="Procurement v2 key formula rule is missing.",
                suggested_fix="Add the expected v2 structured FormulaRule when the metadata column exists.",
            )
    for rule in plan.formula_rules:
        if _is_money_column_name(rule.target_column) and (rule.tolerance_type == "none" or rule.tolerance_value == 0):
            report.add_warning(
                table_name=rule.target_table,
                column_name=rule.target_column,
                message="Money formula uses tolerance_type none or zero tolerance.",
                suggested_fix="Use tolerance_type absolute and tolerance_value 0.01 for money/amount reconciliation.",
            )
        if rule.target_table == "InspectionResult" and rule.target_column == "RejectionRatePct":
            if rule.operation not in {"percentage", "divide"}:
                _formula_error(report, rule, "RejectionRatePct should use percentage or divide operation.", "Use operation percentage or divide.")
            if rule.denominator_column != "InspectedQuantity" or not rule.denominator_guard:
                report.add_warning(
                    table_name=rule.target_table,
                    column_name=rule.target_column,
                    message="RejectionRatePct should use InspectedQuantity denominator with denominator_guard true.",
                    suggested_fix="Set denominator_column to InspectedQuantity and denominator_guard to true.",
                )


def _validate_v2_status_expectations(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    status_rule_keys = {(rule.table_name, rule.status_column): rule for rule in plan.status_rules}
    for table_name, column_name in V2_KEY_STATUS_COLUMNS:
        if table_exists(schema, table_name) and column_exists(schema, table_name, column_name) and (table_name, column_name) not in status_rule_keys:
            report.add_warning(
                table_name=table_name,
                column_name=column_name,
                message="Procurement v2 key lifecycle status column is missing a status_rule.",
                suggested_fix="Add a status_rule that derives statuses from lifecycle facts.",
            )
    for rule in plan.status_rules:
        column = get_column(schema, rule.table_name, rule.status_column)
        if column and column.allowed_values:
            invalid = sorted(set(rule.status_values) - set(column.allowed_values))
            if invalid:
                report.add_error(
                    table_name=rule.table_name,
                    column_name=rule.status_column,
                    message=f"StatusRule {rule.rule_id} includes invalid v2 status values: {', '.join(invalid)}.",
                    suggested_fix="Use only metadata AllowedValues for v2 status rules.",
                )


def _validate_v2_domain_profile(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    profile = plan.domain_profile
    domain_text = " ".join([profile.industry or "", profile.business_context or ""]).lower()
    if domain_text and not any(term in domain_text for term in ["ev", "electric vehicle", "automotive", "battery", "manufacturing"]):
        report.add_warning(
            message="Procurement v2 domain_profile does not clearly mention EV, automotive, battery, or manufacturing.",
            suggested_fix="Use an EV manufacturing domain profile for the v2 fixture scenario.",
        )
    material_text = " ".join(
        [category.category_name for category in profile.material_categories]
        + [example for category in profile.material_categories for example in category.material_examples]
    ).lower()
    if material_text and not any(term in material_text for term in ["battery", "cell", "connector", "busbar", "motor", "electrical", "thermal", "ev"]):
        report.add_warning(
            message="Procurement v2 material categories/examples do not look EV-component-specific.",
            suggested_fix="Include EV component examples such as cells, busbars, connectors, thermal pads, motors, or electronics.",
        )
    location_text = " ".join(profile.plant_locations).lower()
    if profile.plant_locations and not any(term in location_text for term in ["usa", "detroit", "austin", "fremont", "phoenix", "nashville", "columbus", "reno", "greenville"]):
        report.add_warning(
            message="Procurement v2 plant_locations do not appear US-focused.",
            suggested_fix="Use US plant locations such as Detroit, Austin, Fremont, Phoenix, Nashville, Columbus, Reno, or Greenville.",
        )


def _validate_v2_validation_rule_themes(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    condition_text = " ".join(rule.condition for rule in plan.validation_rules).lower()
    expected_terms = {
        "CurrencyCode = USD": "usd",
        "Country = USA": "usa",
        "status diversity": "status",
        "payment amount <= invoice total": "payment",
    }
    for label, token in expected_terms.items():
        if token not in condition_text:
            report.add_warning(
                message=f"Procurement v2 validation_rules may be missing theme: {label}.",
                suggested_fix="Add a validation_rule for this v2 quality theme.",
            )


def _validate_production_v1_plan(plan: LLMGenerationPlan, schema: SchemaContract, report: ValidationReport) -> None:
    _validate_production_v1_expected_tables(schema, report)
    _validate_production_v1_generation_order(plan, report)
    _validate_production_v1_out_of_scope_tables(plan, report)
    _validate_production_v1_date_scope(plan, report)
    _validate_production_v1_role_mapping(plan, report)
    _validate_production_v1_formula_themes(plan, report)
    _validate_production_v1_integration_themes(plan, report)
    _validate_production_v1_uom_precision_themes(plan, report)


def _validate_production_v1_expected_tables(schema: SchemaContract, report: ValidationReport) -> None:
    table_names = set(schema.tables)
    missing = [table_name for table_name in PRODUCTION_V1_EXPECTED_TABLES if table_name not in table_names]
    extras = sorted(table_names - set(PRODUCTION_V1_EXPECTED_TABLES))
    for table_name in missing:
        report.add_error(
            table_name=table_name,
            message=f"Production v1 metadata is missing expected table {table_name}.",
            suggested_fix="Use the 21-table Production Execution module within MES context v1 metadata model.",
        )
    for table_name in extras:
        report.add_error(
            table_name=table_name,
            message=f"Production v1 metadata includes unsupported table {table_name}.",
            suggested_fix="Use exactly the 21 Production Execution module within MES context v1 tables.",
        )


def _validate_production_v1_generation_order(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    if tuple(plan.generation_order) == PRODUCTION_V1_EXPECTED_TABLES:
        return
    missing = [table_name for table_name in PRODUCTION_V1_EXPECTED_TABLES if table_name not in plan.generation_order]
    for table_name in missing:
        report.add_error(
            table_name=table_name,
            message=f"Production v1 generation_order is missing {table_name}.",
            suggested_fix="Include all 21 Production Execution module within MES context v1 tables exactly once in corrected lifecycle order.",
        )
    if set(plan.generation_order) == set(PRODUCTION_V1_EXPECTED_TABLES) and len(plan.generation_order) == len(PRODUCTION_V1_EXPECTED_TABLES):
        report.add_error(
            message="Production v1 generation_order must follow the corrected lifecycle order.",
            suggested_fix="Use ProductMaster through ProductionCostSummary in the Production Execution module within MES context v1 metadata ProcessOrder.",
        )


def _validate_production_v1_out_of_scope_tables(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    values = list(plan.generation_order)
    values.extend(mapping.table_name for mapping in plan.table_role_mapping)
    values.extend(mapping.table_role for mapping in plan.table_role_mapping)
    for value in values:
        normalized = value.lower().replace("_", "")
        for term in PRODUCTION_V1_OUT_OF_SCOPE_TERMS:
            if term.lower().replace("_", "") in normalized:
                report.add_error(
                    table_name=value,
                    message=f"Production v1 plan includes out-of-scope MES concept: {term}.",
                    suggested_fix="Remove OEE, downtime, maintenance, labor, warranty, sales, customer, and shipment tables from Production v1.",
                )


def _validate_production_v1_date_scope(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    plan_text = _plan_text(plan)
    if "2026" in plan_text or "2024" in plan_text:
        report.add_error(
            message="Production v1 plan references dates outside the 2025-only scope.",
            suggested_fix="Keep Production v1 date guidance between 2025-01-01 and 2025-12-31.",
        )
    if "2025" not in plan_text:
        report.add_error(
            message="Production v1 plan does not clearly state the 2025-only date scope.",
            suggested_fix="Add 2025-only date guidance to date_rules, validation_rules, or assumptions.",
        )


def _validate_production_v1_role_mapping(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    mapped_tables = {mapping.table_name for mapping in plan.table_role_mapping}
    for table_name in PRODUCTION_V1_EXPECTED_TABLES:
        if table_name not in mapped_tables:
            report.add_error(
                table_name=table_name,
                message=f"Production v1 table_role_mapping is missing {table_name}.",
                suggested_fix="Map every expected Production Execution module within MES context v1 table to its role.",
            )


def _validate_production_v1_formula_themes(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    plan_text = _plan_text(plan)
    normalized = _normalize_theme_text(plan_text)
    for label, tokens in PRODUCTION_V1_FORMULA_THEMES.items():
        if not all(token in normalized for token in tokens):
            report.add_error(
                message=f"Production v1 plan is missing formula guidance: {label}.",
                suggested_fix="Add a formula_rule or validation_rule documenting this Production Execution calculation.",
            )


def _validate_production_v1_integration_themes(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    normalized = _normalize_theme_text(_plan_text(plan))
    for label, tokens in PRODUCTION_V1_INTEGRATION_THEMES.items():
        if not all(token in normalized for token in tokens):
            report.add_error(
                message=f"Production v1 plan is missing integration guidance: {label}.",
                suggested_fix="Add Procurement inventory and genealogy integration guidance to the plan.",
            )


def _validate_production_v1_uom_precision_themes(plan: LLMGenerationPlan, report: ValidationReport) -> None:
    normalized = _normalize_theme_text(_plan_text(plan))
    if not all(token in normalized for token in ["countable", "integer", "bulk", "decimal"]):
        report.add_error(
            message="Production v1 plan is missing UOM precision guidance for countable and bulk materials.",
            suggested_fix="State that countable UOMs use integers and bulk/measurable UOMs may use decimals.",
        )


def _plan_text(plan: LLMGenerationPlan) -> str:
    return json.dumps(plan.model_dump(mode="json"), sort_keys=True).lower()


def _normalize_theme_text(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _is_money_column_name(column_name: str) -> bool:
    normalized = column_name.lower()
    return any(token in normalized for token in ["amount", "price", "cost", "freight", "tax"])


def _existing_columns(
    column_names: Iterable[str],
    table_name: str,
    schema: SchemaContract,
    rule: FormulaRule,
    report: ValidationReport,
) -> list[ColumnContract]:
    columns: list[ColumnContract] = []
    for column_name in column_names:
        column = get_column(schema, table_name, column_name)
        if column is None:
            _formula_error(
                report,
                rule,
                f"Formula input column {column_name} does not exist in {table_name}.",
                "Use existing input_columns from the target table.",
            )
        else:
            columns.append(column)
    return columns


def _require_numeric_columns(columns: Iterable[ColumnContract], report: ValidationReport, rule: FormulaRule) -> None:
    for column in columns:
        if not is_numeric_type(column.data_type):
            _formula_error(
                report,
                rule,
                f"Formula input column {column.column_name} should be numeric-compatible.",
                "Use numeric-compatible input columns for numeric operations.",
            )


def _require_column(
    schema: SchemaContract,
    table_name: str,
    column_name: str,
    report: ValidationReport,
) -> ColumnContract | None:
    if not table_exists(schema, table_name):
        report.add_error(
            table_name=table_name,
            column_name=column_name,
            message=f"Referenced table {table_name} does not exist in metadata.",
            suggested_fix="Use an existing metadata table.",
        )
        return None
    column = get_column(schema, table_name, column_name)
    if column is None:
        report.add_error(
            table_name=table_name,
            column_name=column_name,
            message=f"Referenced column {column_name} does not exist in {table_name}.",
            suggested_fix="Use an existing metadata column.",
        )
    return column


def _formula_error(report: ValidationReport, rule: FormulaRule, message: str, suggested_fix: str) -> None:
    report.add_error(
        table_name=rule.target_table,
        column_name=rule.target_column,
        message=f"FormulaRule {rule.rule_id}: {message}",
        suggested_fix=suggested_fix,
    )


def _validation_rule_error(
    report: ValidationReport,
    rule: PlanValidationRule,
    message: str,
    suggested_fix: str,
) -> None:
    report.add_error(
        table_name=rule.table_name,
        column_name=rule.column_name,
        message=f"PlanValidationRule {rule.rule_id}: {message}",
        suggested_fix=suggested_fix,
    )


def _add_duplicate_errors(values: list[str], label: str, report: ValidationReport) -> None:
    counts = Counter(values)
    for value, count in counts.items():
        if count > 1:
            report.add_error(
                table_name=value,
                message=f"Duplicate {label}: {value}.",
                suggested_fix=f"Use each {label} exactly once.",
            )


def _target_rows_for_role(schema: SchemaContract, table_role: str) -> int | None:
    for table in schema.tables.values():
        if table.table_role == table_role:
            return table.target_rows
    return None


def _nullable_strategy_allows_null(nullable_strategy: str | None) -> bool:
    if nullable_strategy is None:
        return False
    normalized = nullable_strategy.strip().lower().replace("-", "_")
    if normalized in {"never_null", "not_null", "non_null", "no_nulls"}:
        return False
    return "null" in normalized or "nullable" in normalized


def _normalize_data_type(data_type: str) -> str:
    return data_type.strip().lower()


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _format_issue(
    index: int,
    table_name: str | None,
    column_name: str | None,
    message: str,
    suggested_fix: str,
) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines

