"""Build strict LLM planning prompts from validated project contracts."""

from __future__ import annotations

import json
from typing import get_args

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.llm_plan_contract import (
    Confidence,
    FormulaOperation,
    FormulaRuleType,
    PlanValidationRuleType,
    QuantityOperator,
    RowCountSource,
    RuleSeverity,
)
from procurement_data_generator.core.contracts.schema_contract import Area, GenerationType, SchemaContract
from procurement_data_generator.modules.procurement.role_catalog import get_procurement_role_catalog


def build_llm_planning_prompt(
    schema_contract: SchemaContract,
    relationships: list[RelationshipContract],
    business_scenario: str,
    role_catalog: dict | None = None,
    model_version: str = "v1",
) -> str:
    """Build the strict planning prompt that will later be sent to an LLM."""

    catalog = role_catalog or get_procurement_role_catalog(model_version)
    scenario = business_scenario.strip()
    version_sections = _v2_sections() if model_version == "v2" else []

    sections = [
        _system_instruction_section(),
        _task_objective_section(),
        _hard_rules_section(),
        *version_sections,
        _business_scenario_section(scenario),
        _metadata_summary_section(schema_contract),
        _erd_relationships_section(relationships),
        _supported_values_section(catalog),
        _json_shape_section(),
        _formula_guidance_section(),
        _date_rule_guidance_section(),
        _quantity_rule_guidance_section(),
        _status_rule_guidance_section(),
        _domain_profile_guidance_section(),
        _output_contract_section(),
    ]
    return "\n\n".join(sections).strip() + "\n"


def _v2_sections() -> list[str]:
    return [
        _v2_model_section(),
        _v2_hard_rules_section(),
        _v2_lifecycle_guidance_section(),
        _v2_status_realism_section(),
        _v2_rejection_reason_section(),
        _v2_location_guidance_section(),
        _v2_usd_financial_guidance_section(),
        _v2_formula_guidance_section(),
        _v2_date_rule_guidance_section(),
        _v2_quantity_rule_guidance_section(),
        _v2_validation_rule_guidance_section(),
    ]


def _system_instruction_section() -> str:
    return "\n".join(
        [
            "A. System/Role Instruction",
            "You are a procurement data planning assistant.",
            "Your job is to create a structured LLMGenerationPlan JSON contract for Python to validate and execute later.",
            "Core principle: LLM plans. Python validates. Python generates. Python calculates. Python reconciles. Python loads to SQL.",
        ]
    )


def _task_objective_section() -> str:
    return "\n".join(
        [
            "B. Task Objective",
            "Produce one LLMGenerationPlan JSON object only.",
            "The plan should describe module context, domain profile, table role mapping, generation order, row counts, column strategies, formula rules, date rules, quantity rules, status rules, validation rules, assumptions, and warnings.",
        ]
    )


def _hard_rules_section() -> str:
    return "\n".join(
        [
            "C. Hard Rules",
            "- Return JSON only.",
            "- Do not generate actual table rows.",
            "- Do not invent table names.",
            "- Do not invent column names.",
            "- Use only the provided metadata tables and columns.",
            "- Use only supported generation types.",
            "- Use only supported formula rule types.",
            "- Use only supported formula operations.",
            "- Formula rules must reference existing columns only.",
            "- Date rules must reference existing date columns only.",
            "- Quantity rules must reference existing quantity columns only.",
            "- Status rules must reference existing status columns only.",
            "- CRITICAL: For column_generation_rules.depends_on_columns, only include columns that exist in the SAME table as table_name. Do not include columns from parent/child tables. Cross-table dependencies belong in date_rules, quantity_rules, formula_rules, or validation_rules.",
            "- depends_on_columns is for same-table dependencies only.",
            "- Every value in depends_on_columns must be a column that exists in the same table_name.",
            "- Do not put parent-table or child-table columns inside depends_on_columns.",
            "- If a generated column depends on a parent table column, leave depends_on_columns empty and describe the dependency in date_rules or quantity_rules.",
            "- Before returning JSON, verify every depends_on_columns entry exists in that table's column list.",
            "- Row count plan should primarily respect TargetRows from metadata.",
            "- If the business scenario suggests row count changes, set source to llm_adjusted and explain reasoning.",
            "- Domain profile should help Python generate realistic and unique names.",
            "- Do not fix duplicate names by appending numeric suffixes.",
            "- Do not include raw formulas outside the supported FormulaRule structure.",
            "- Do not use unsafe operations.",
            "- Do not produce SQL.",
            "- Do not produce code.",
            "- Do not use markdown.",
            "- Do not include comments inside JSON.",
            "- Do not include explanations outside JSON.",
        ]
    )


def _v2_model_section() -> str:
    return "\n".join(
        [
            "C1. Procurement v2 Exact Model",
            "Use exactly the Procurement v2 metadata model when model_version is v2.",
            "The exact Procurement v2 table list is:",
            "1. SupplierMaster",
            "2. SupplierComponent",
            "3. ComponentMaster",
            "4. Plant",
            "5. Warehouse",
            "6. PurchaseRequisition",
            "7. PurchaseReqLine",
            "8. RFQHeader",
            "9. RFQLine",
            "10. SupplierQuotation",
            "11. SupplierQuotationLn",
            "12. PurchaseOrderHdr",
            "13. PurchaseOrderLine",
            "14. POSchedule",
            "15. ShipmentHdr",
            "16. ShipmentLine",
            "17. GoodsReceiptHeader",
            "18. GoodsReceiptLine",
            "19. IncomingInspection",
            "20. InspectionResult",
            "21. InventoryTransaction",
            "22. Inventory",
            "23. SupplierInvoice",
            "24. PaymentTransaction",
            "Inventory is included in Procurement v2 as the calculated current stock position table.",
            "InventoryTransaction is included as the detailed inbound StockIn posting table for accepted supplier receipts.",
            "InventoryBalance must not be generated or planned for Procurement v2.",
        ]
    )


def _v2_hard_rules_section() -> str:
    return "\n".join(
        [
            "C2. Procurement v2 Hard Rules",
            "- Return JSON only.",
            "- No markdown fences.",
            "- Do not generate actual table rows.",
            "- Do not invent tables.",
            "- Do not invent columns.",
            "- Use only metadata table names.",
            "- Use only metadata column names.",
            "- Use only supported enum values.",
            "- Do not include InventoryBalance.",
            "- InventoryTransaction.TransactionType must be StockIn for this inbound procurement scenario.",
            "- Do not plan PlantMaster or WarehouseMaster. Use Plant and Warehouse.",
            "- Use 2025 date range only.",
            "- Use US locations only for Plant, Warehouse, and Supplier location planning.",
            "- Use CurrencyCode = USD for all financial tables.",
            "- Do not assign one constant status value across a whole lifecycle table.",
            "- Statuses must be derived from lifecycle facts.",
            "- RejectionReason should be null/blank/Not Applicable when RejectedQuantity = 0.",
            "- RejectionReason should vary when RejectedQuantity > 0.",
            "- LLM must not place cross-table fields in depends_on_columns.",
            "- depends_on_columns must contain same-table columns only.",
            "- Cross-table dependencies must be expressed through date_rules, quantity_rules, formula_rules, or validation_rules.",
            "- Formula text is audit-only; execution uses structured fields.",
            "- For money formulas, use tolerance_type absolute and tolerance_value 0.01 unless the schema says otherwise.",
            "- For quantity formulas, use tolerance_type absolute and tolerance_value 0.0001.",
            "- For percentage formulas, use tolerance_type absolute and tolerance_value 0.01.",
            "- Do not set tolerance_type = none for money/amount reconciliation.",
        ]
    )


def _v2_lifecycle_guidance_section() -> str:
    return "\n".join(
        [
            "C3. Procurement v2 Lifecycle Guidance",
            "Supplier and component setup:",
            "SupplierMaster and ComponentMaster define suppliers and EV components.",
            "SupplierComponent maps suppliers to components they can supply.",
            "RFQ/quotation/PO logic should prefer supplier-component eligible suppliers.",
            "",
            "Procurement lifecycle:",
            "PurchaseRequisition -> PurchaseReqLine -> RFQHeader -> RFQLine -> SupplierQuotation -> SupplierQuotationLn -> PurchaseOrderHdr -> PurchaseOrderLine -> POSchedule -> ShipmentHdr -> ShipmentLine -> GoodsReceiptHeader -> GoodsReceiptLine -> IncomingInspection -> InspectionResult -> InventoryTransaction -> Inventory -> SupplierInvoice -> PaymentTransaction",
            "",
            "Supporting location lifecycle:",
            "Plant -> Warehouse",
            "Plant -> PurchaseRequisition",
            "Plant/Warehouse -> GoodsReceiptHeader",
            "Plant/Warehouse -> InventoryTransaction",
            "Plant/Warehouse -> Inventory",
            "",
            "Important lifecycle rules:",
            "- SupplierQuotation should be generated from RFQHeader.",
            "- SupplierQuotationLn should be generated from RFQLine.",
            "- PurchaseOrderHdr should be created from awarded SupplierQuotation.",
            "- PurchaseOrderLine should be created from awarded SupplierQuotationLn.",
            "- POSchedule should split PurchaseOrderLine delivery quantities.",
            "- ShipmentLine should be generated from POSchedule.",
            "- GoodsReceiptLine should be generated from ShipmentLine.",
            "- IncomingInspection should be generated from GoodsReceiptLine.",
            "- InspectionResult should be generated from IncomingInspection.",
            "- InventoryTransaction should be generated from accepted InspectionResult quantity.",
            "- InventoryTransaction should represent StockIn postings only, with supplier traceability and inventory value.",
            "- Inventory should be calculated from InventoryTransaction by ComponentID, PlantID, and WarehouseID.",
            "- SupplierInvoice should be generated after GoodsReceiptHeader.",
            "- PaymentTransaction should be generated after SupplierInvoice.",
        ]
    )


def _v2_status_realism_section() -> str:
    return "\n".join(
        [
            "C4. Procurement v2 Lifecycle-Based Status Realism",
            "The LLM plan should instruct Python to derive statuses from lifecycle facts.",
            "Do not allow constant/default status values across entire tables if multiple allowed values exist.",
            "- PurchaseRequisition.Status: Draft/Submitted early, Approved if approved, ConvertedToRFQ if RFQ exists, Cancelled only small percentage if allowed.",
            "- PurchaseReqLine.LineStatus: Open if not converted, Approved if approved, ConvertedToRFQ if RFQLine exists, Cancelled only small percentage if allowed.",
            "- RFQHeader.RFQStatus: Created before sent, Sent when quotations are expected, Closed when quotations are completed/awarded, Cancelled small percentage if allowed.",
            "- RFQLine.LineStatus: Open before quotes, Quoted when supplier quotation lines exist, Awarded when awarded quotation line exists, Closed after award/PO conversion.",
            "- SupplierQuotation.QuotationStatus: Submitted when supplier responded, UnderReview before award, Awarded if any line awarded, Rejected if not awarded, Expired if validity passed and not awarded.",
            "- SupplierQuotationLn.LineStatus: Quoted by default, Awarded when AwardedFlag = 1, Rejected when AwardedFlag = 0 and award exists.",
            "- PurchaseOrderHdr.POStatus: Created/Approved/Sent early, PartiallyReceived when some receipt exists, Closed when fully received, Cancelled small percentage if allowed.",
            "- PurchaseOrderLine.LineStatus: Open before schedule, Scheduled when POSchedule exists, PartiallyShipped when partial shipments exist, PartiallyReceived when partial receipts exist, Closed when fully received.",
            "- POSchedule.ScheduleStatus: Planned/Scheduled before shipment, PartiallyShipped when partial shipment exists, Shipped when shipped, Delayed if shipment date is after scheduled date.",
            "- ShipmentHdr.ShipmentStatus: Planned before shipment, Shipped/InTransit after shipment, Delivered after goods receipt, Delayed if shipment date exceeds expected/scheduled date, PartiallyDelivered when partial receipt exists.",
            "- GoodsReceiptHeader.ReceiptStatus: Received if fully received, Partial if partially received, ShortReceived if received quantity is less than shipped quantity, Damaged if damaged quantity exists, Closed after inspection/inventory posting.",
            "- IncomingInspection.InspectionStatus: Pending before result, Passed if all accepted, PartiallyRejected if some rejected, Failed if all rejected, Completed after inspection result.",
            "- InspectionResult.ResultStatus: Passed if RejectedQuantity = 0, PartiallyRejected if AcceptedQuantity > 0 and RejectedQuantity > 0, Failed if AcceptedQuantity = 0 and RejectedQuantity > 0.",
            "- InventoryTransaction.TransactionType: StockIn only for this procurement inbound scenario; it represents accepted supplier goods posted into inventory.",
            "- InventoryTransaction supplier and value traceability: SupplierID must come from PO/supplier lineage, UnitPrice must come from PurchaseOrderLine.UnitPrice, and InventoryValue must equal TransactionQuantity * UnitPrice.",
            "- Inventory.InventoryStatus: Available when available quantity is healthy, LowStock when available quantity is low, OutOfStock when on-hand is zero, Hold when stock exists but available quantity is zero.",
            "- SupplierInvoice.InvoiceStatus: Draft/Submitted early, Approved after invoice validation, PartiallyPaid if partial payment exists, Paid if fully paid, Overdue if due date passed and not fully paid.",
            "- PaymentTransaction.PaymentStatus: Pending before paid, Paid if full amount paid, PartiallyPaid if partial amount paid, Failed small percentage if allowed.",
        ]
    )


def _v2_rejection_reason_section() -> str:
    return "\n".join(
        [
            "C5. Procurement v2 Rejection Reason Realism",
            "- If RejectedQuantity = 0, RejectionReason should be null, blank, or Not Applicable if allowed.",
            "- If RejectedQuantity > 0, RejectionReason must be populated.",
            "- RejectionReason should vary across rejected rows.",
            "- Do not use the same rejection reason for all rows.",
            "- Choose realistic reasons based on EV manufacturing quality context.",
            "Reason catalog:",
            "Dimension Out of Tolerance; Surface Defect; Electrical Test Failure; Packaging Damage; Material Contamination; Wrong Specification; Thermal Stress Failure; Supplier Documentation Issue; Visual Defect; Functional Test Failure; Connector Fitment Issue; Battery Cell Leakage; Weld Defect; Insulation Resistance Failure.",
        ]
    )


def _v2_location_guidance_section() -> str:
    return "\n".join(
        [
            "C6. Procurement v2 US-Only Location Guidance",
            "- PlantCountry = USA.",
            "- WarehouseCountry = USA.",
            "- SupplierCountry = USA unless metadata explicitly allows international suppliers. For the v2 fixture, use USA.",
            "- WarehouseCity and WarehouseState must align with Plant/Warehouse logic.",
            "- Warehouses should belong to a Plant.",
            "- Warehouse location should be consistent with its PlantID.",
            "- Do not randomly assign warehouse city/state unrelated to its Plant.",
            "Suggested US plant/warehouse locations: Detroit, Michigan; Austin, Texas; Fremont, California; Phoenix, Arizona; Nashville, Tennessee; Columbus, Ohio; Reno, Nevada; Greenville, South Carolina.",
        ]
    )


def _v2_usd_financial_guidance_section() -> str:
    return "\n".join(
        [
            "C7. Procurement v2 USD-Only Financial Guidance",
            "- CurrencyCode must be USD where the column exists.",
            "- SupplierComponent.ContractPrice is in USD.",
            "- SupplierQuotationLn.QuotedUnitPrice and QuotedLineAmount are in USD.",
            "- PurchaseOrderLine.UnitPrice and LineAmount are in USD.",
            "- PurchaseOrderHdr.TotalAmount is in USD.",
            "- SupplierInvoice.InvoiceAmount, TaxAmount, FreightAmount, TotalInvoiceAmount are in USD.",
            "- PaymentTransaction.PaymentAmount is in USD.",
            "- Do not generate other currency codes.",
        ]
    )


def _v2_formula_guidance_section() -> str:
    return "\n".join(
        [
            "C8. Procurement v2 Formula Guidance",
            "Include only FormulaRule objects that can be expressed using supported structured fields.",
            "- SupplierQuotationLn.QuotedLineAmount: rule_type row_level; operation multiply; input_columns [\"QuotedQuantity\", \"QuotedUnitPrice\"]; target_table SupplierQuotationLn; target_column QuotedLineAmount; tolerance_type absolute; tolerance_value 0.01.",
            "- PurchaseOrderLine.LineAmount: rule_type row_level; operation multiply; input_columns [\"OrderedQuantity\", \"UnitPrice\"]; target_table PurchaseOrderLine; target_column LineAmount; tolerance_type absolute; tolerance_value 0.01.",
            "- PurchaseOrderHdr.TotalAmount: rule_type aggregate; operation sum; source_table PurchaseOrderLine; source_column LineAmount; target_table PurchaseOrderHdr; target_column TotalAmount; relationship_key PurchaseOrderID; tolerance_type absolute; tolerance_value 0.01.",
            "- GoodsReceiptLine.ShortQuantity: rule_type row_level; operation subtract; input_columns [\"ShippedQuantity\", \"ReceivedQuantity\"]; target_table GoodsReceiptLine; target_column ShortQuantity; tolerance_type absolute; tolerance_value 0.0001.",
            "- InspectionResult.RejectedQuantity: rule_type row_level; operation subtract; input_columns [\"InspectedQuantity\", \"AcceptedQuantity\"]; target_table InspectionResult; target_column RejectedQuantity; tolerance_type absolute; tolerance_value 0.0001.",
            "- InspectionResult.RejectionRatePct: rule_type percentage; operation percentage; input_columns [\"RejectedQuantity\", \"InspectedQuantity\"]; denominator_column InspectedQuantity; target_table InspectionResult; target_column RejectionRatePct; denominator_guard true; tolerance_type absolute; tolerance_value 0.01.",
            "- SupplierInvoice.TotalInvoiceAmount: rule_type row_level; operation add; input_columns [\"InvoiceAmount\", \"TaxAmount\", \"FreightAmount\"]; target_table SupplierInvoice; target_column TotalInvoiceAmount; tolerance_type absolute; tolerance_value 0.01.",
            "- InventoryTransaction.InventoryValue: rule_type row_level; operation multiply; input_columns [\"TransactionQuantity\", \"UnitPrice\"]; target_table InventoryTransaction; target_column InventoryValue; tolerance_type absolute; tolerance_value 0.01.",
            "- Inventory.OnHandQuantity: can be expressed as a validation_rule for now; it must equal SUM(InventoryTransaction.TransactionQuantity) grouped by ComponentID, PlantID, WarehouseID.",
            "- Inventory.OnHandValue: can be expressed as a validation_rule for now; it must equal SUM(InventoryTransaction.InventoryValue) grouped by ComponentID, PlantID, WarehouseID.",
            "- Inventory.AvailableQuantity: can be expressed as a validation_rule for now; it must equal OnHandQuantity - ReservedQuantity.",
            "- Inventory.AvailableValue: can be expressed as a validation_rule for now; it should be derived from AvailableQuantity and average unit cost, where average unit cost is OnHandValue / OnHandQuantity.",
            "- For SupplierInvoice.InvoiceAmount: If current formula schema cannot express received PO value cleanly, include a validation_rule instead of unsafe formula. Do not invent unsupported formula structures.",
            "- Do not set tolerance_type = none for money/amount reconciliation.",
        ]
    )


def _v2_date_rule_guidance_section() -> str:
    return "\n".join(
        [
            "C9. Procurement v2 Date Rule Guidance",
            "Dates should follow: RequisitionDate <= RFQDate <= QuotationDate <= OrderDate <= ScheduledDeliveryDate <= ShipmentDate <= ReceiptDate <= InspectionDate <= TransactionDate <= InvoiceDate <= PaymentDate.",
            "- RequiredDate >= RequisitionDate.",
            "- RFQDate >= RequisitionDate.",
            "- RFQDueDate >= RFQDate.",
            "- QuotationDate >= RFQDate.",
            "- ValidUntilDate >= QuotationDate.",
            "- OrderDate >= QuotationDate.",
            "- ExpectedDeliveryDate >= OrderDate.",
            "- ScheduledDeliveryDate >= OrderDate.",
            "- ShipmentDate >= OrderDate.",
            "- ReceiptDate >= ShipmentDate.",
            "- InspectionDate >= ReceiptDate.",
            "- TransactionDate >= InspectionDate.",
            "- InvoiceDate >= ReceiptDate.",
            "- DueDate >= InvoiceDate.",
            "- PaymentDate >= InvoiceDate.",
            "- All dates must remain within 2025 where metadata date MinValue/MaxValue says 2025.",
        ]
    )


def _v2_quantity_rule_guidance_section() -> str:
    return "\n".join(
        [
            "C10. Procurement v2 Quantity Rule Guidance",
            "- RequestedQuantity > 0.",
            "- RFQQuantity should be based on RequestedQuantity.",
            "- QuotedQuantity should be based on RFQQuantity.",
            "- OrderedQuantity should be based on awarded QuotedQuantity.",
            "- ScheduledQuantity should not exceed OrderedQuantity remaining.",
            "- ShippedQuantity should not exceed ScheduledQuantity.",
            "- ReceivedQuantity should not exceed ShippedQuantity.",
            "- DamagedQuantity should not exceed ReceivedQuantity.",
            "- ShortQuantity = ShippedQuantity - ReceivedQuantity.",
            "- InspectedQuantity should be <= ReceivedQuantity.",
            "- AcceptedQuantity + RejectedQuantity = InspectedQuantity.",
            "- InventoryTransaction.TransactionQuantity = AcceptedQuantity.",
            "- InventoryTransaction.TransactionType = StockIn.",
            "- InventoryTransaction.UnitPrice = PurchaseOrderLine.UnitPrice.",
            "- InventoryTransaction.InventoryValue = TransactionQuantity * UnitPrice.",
            "- Inventory.OnHandQuantity = SUM(InventoryTransaction.TransactionQuantity) grouped by ComponentID, PlantID, WarehouseID.",
            "- Inventory.OnHandValue = SUM(InventoryTransaction.InventoryValue) grouped by ComponentID, PlantID, WarehouseID.",
            "- Inventory.AvailableQuantity = OnHandQuantity - ReservedQuantity.",
            "- Inventory.AvailableValue is derived from AvailableQuantity and average unit cost.",
            "- PaymentAmount <= SupplierInvoice.TotalInvoiceAmount.",
        ]
    )


def _v2_validation_rule_guidance_section() -> str:
    return "\n".join(
        [
            "C11. Procurement v2 Validation Rule Guidance",
            "Include validation rules only with supported PlanValidationRule fields.",
            "- SupplierComponent supplier/component FK consistency.",
            "- RFQLine to requisition line.",
            "- SupplierQuotation to RFQ and Supplier.",
            "- SupplierQuotationLn to SupplierQuotation and RFQLine.",
            "- Awarded quotation to PO.",
            "- PO schedule quantity <= ordered quantity.",
            "- Shipment quantity <= scheduled quantity.",
            "- Receipt quantity <= shipped quantity.",
            "- Inspection accepted + rejected = inspected.",
            "- InventoryTransaction quantity = accepted quantity.",
            "- InventoryTransaction SupplierID, GoodsReceiptLineID, PurchaseOrderLineID, ComponentID, PlantID, and WarehouseID must match procurement receipt/PO/inspection lineage.",
            "- InventoryTransaction TransactionType must be StockIn.",
            "- InventoryTransaction InventoryValue equals TransactionQuantity times UnitPrice.",
            "- Inventory OnHandQuantity equals grouped InventoryTransaction quantity.",
            "- Inventory OnHandValue equals grouped InventoryTransaction value.",
            "- Inventory AvailableQuantity equals OnHandQuantity minus ReservedQuantity.",
            "- Inventory AvailableValue is derived from AvailableQuantity and average unit cost.",
            "- Invoice after receipt.",
            "- Payment after invoice.",
            "- Payment amount <= invoice total.",
            "- CurrencyCode = USD.",
            "- Country = USA for Plant/Warehouse/Supplier.",
            "- Status diversity where multiple AllowedValues exist.",
            "Use supported validation_rule structures only. Do not invent unsupported schema fields.",
        ]
    )


def _business_scenario_section(business_scenario: str) -> str:
    return "\n".join(
        [
            "D. Business Scenario",
            business_scenario or "(No business scenario was provided.)",
        ]
    )


def _metadata_summary_section(schema_contract: SchemaContract) -> str:
    lines = ["E. Metadata Summary"]
    for table in schema_contract.ordered_tables:
        lines.extend(
            [
                f"TableName: {table.table_name}",
                f"ProcessOrder: {table.process_order}",
                f"Area: {table.area}",
                f"TableRole: {table.table_role}",
                f"TargetRows: {table.target_rows}",
                "Columns:",
            ]
        )
        for column in table.columns:
            lines.append(
                "  - "
                f"ColumnName={column.column_name}; "
                f"DataType={column.data_type}; "
                f"KeyType={column.key_type or ''}; "
                f"RelatedTable={column.related_table or ''}; "
                f"RelatedColumn={column.related_column or ''}; "
                f"Nullable={column.nullable}; "
                f"GenerationType={column.generation_type}; "
                f"AllowedValues={', '.join(column.allowed_values)}; "
                f"MinValue={_blank_if_none(column.min_value)}; "
                f"MaxValue={_blank_if_none(column.max_value)}; "
                f"Formula={column.formula or ''}"
            )
        lines.append("")
    return "\n".join(lines).strip()


def _erd_relationships_section(relationships: list[RelationshipContract]) -> str:
    lines = ["F. ERD Relationships"]
    if not relationships:
        lines.append("- No ERD relationships were parsed.")
        return "\n".join(lines)

    for relationship in relationships:
        lines.extend(
            [
                f"- Parent: {relationship.parent_table}",
                f"  Child: {relationship.child_table}",
                f"  Type: {relationship.relationship_type}",
                f"  MermaidSymbol: {relationship.mermaid_symbol}",
                f"  Label: {relationship.label or ''}",
            ]
        )
    return "\n".join(lines)


def _supported_values_section(role_catalog: dict) -> str:
    return "\n".join(
        [
            "G. Supported Values",
            f"- Area: {', '.join(get_args(Area))}",
            f"- TableRole: {', '.join(role_catalog.keys())}",
            f"- GenerationType: {', '.join(get_args(GenerationType))}",
            f"- Formula rule_type: {', '.join(get_args(FormulaRuleType))}",
            f"- Formula operation: {', '.join(get_args(FormulaOperation))}",
            f"- Quantity operator: {', '.join(get_args(QuantityOperator))}",
            f"- Validation rule type: {', '.join(get_args(PlanValidationRuleType))}",
            f"- Severity: {', '.join(get_args(RuleSeverity))}",
            f"- Confidence: {', '.join(get_args(Confidence))}",
            f"- Row count source: {', '.join(get_args(RowCountSource))}",
        ]
    )


def _json_shape_section() -> str:
    skeleton = {
        "module": "procurement",
        "business_summary": "string",
        "domain_profile": {
            "industry": "string",
            "business_context": "string or null",
            "vendor_categories": ["string"],
            "material_categories": [
                {
                    "category_name": "string",
                    "material_examples": ["string"],
                    "specification_patterns": ["string"],
                }
            ],
            "warehouse_types": ["string"],
            "plant_locations": ["string"],
            "carrier_name_patterns": ["string"],
            "inspection_test_categories": ["string"],
        },
        "table_role_mapping": [
            {
                "table_name": "existing metadata table name",
                "table_role": "supported procurement role",
                "area": "supported area",
                "confidence": "high|medium|low",
                "reasoning": "string or null",
            }
        ],
        "generation_order": ["existing metadata table name"],
        "row_count_plan": [
            {
                "table_name": "existing metadata table name",
                "target_rows": 1,
                "source": "metadata|llm_adjusted|derived_from_parent",
                "reasoning": "string or null",
            }
        ],
        "column_generation_rules": [
            {
                "table_name": "existing metadata table name",
                "column_name": "existing metadata column name",
                "generation_type": "supported generation type",
                "strategy": "string",
                "allowed_values": ["string"],
                "min_value": "string, number, or null",
                "max_value": "string, number, or null",
                "nullable_strategy": "string or null",
                "depends_on_columns": ["existing metadata column name"],
                "notes": "string or null",
            }
        ],
        "formula_rules": [
            {
                "rule_id": "non_blank_string",
                "rule_type": "supported formula rule_type",
                "target_table": "existing metadata table name",
                "target_column": "existing metadata column name",
                "operation": "supported formula operation",
                "input_columns": ["existing metadata column name"],
                "source_table": "existing metadata table name or null",
                "source_column": "existing metadata column name or null",
                "relationship_key": "existing key column or null",
                "group_by_columns": ["existing metadata column name"],
                "formula": "string",
                "denominator_column": "existing metadata column name or null",
                "denominator_guard": True,
                "tolerance_type": "absolute|percentage|none|null",
                "tolerance_value": 0.0,
                "description": "string or null",
            }
        ],
        "date_rules": [
            {
                "rule_id": "non_blank_string",
                "earlier_table": "existing metadata table name",
                "earlier_column": "existing date column name",
                "later_table": "existing metadata table name",
                "later_column": "existing date column name",
                "min_offset_days": 0,
                "max_offset_days": 30,
                "description": "string or null",
            }
        ],
        "quantity_rules": [
            {
                "rule_id": "non_blank_string",
                "left_table": "existing metadata table name",
                "left_column": "existing quantity column name",
                "operator": "<=|>=|=|<|>",
                "right_table": "existing metadata table name",
                "right_column": "existing quantity column name",
                "description": "string or null",
            }
        ],
        "status_rules": [
            {
                "rule_id": "non_blank_string",
                "table_name": "existing metadata table name",
                "status_column": "existing status column name",
                "status_values": ["string"],
                "derivation_logic": "string",
                "description": "string or null",
            }
        ],
        "validation_rules": [
            {
                "rule_id": "non_blank_string",
                "rule_type": "supported validation rule type",
                "table_name": "existing metadata table name or null",
                "column_name": "existing metadata column name or null",
                "condition": "string",
                "severity": "error|warning",
                "description": "string or null",
            }
        ],
        "assumptions": ["string"],
        "warnings": ["string"],
    }
    return "H. Required JSON Shape\n" + json.dumps(skeleton, indent=2)


def _formula_guidance_section() -> str:
    return "\n".join(
        [
            "I. Formula Guidance",
            "Include formula rules only if the involved target and input columns exist in metadata.",
            "- PurchaseOrderLine.LineAmount = OrderedQuantity * UnitPrice",
            "- PurchaseOrderHeader.TotalAmount = SUM(PurchaseOrderLine.LineAmount) grouped by PurchaseOrderID",
            "- GoodsReceiptLine.ShortQuantity = ShippedQuantity - ReceivedQuantity",
            "- QualityInspectionLine.RejectedQuantity = InspectedQuantity - AcceptedQuantity",
            "- QualityInspectionLine.RejectionRatePct = RejectedQuantity / InspectedQuantity * 100 with denominator guard",
            "- InventoryBalance.OnHandQuantity = SUM(InventoryTransaction.Quantity) grouped by RawMaterialID, PlantID, WarehouseID",
            "- For InventoryBalance formulas, use rule_type = inventory_balance.",
            "- For InventoryBalance formulas, use group_by_columns = [\"RawMaterialID\", \"PlantID\", \"WarehouseID\"] when those columns exist.",
            "- Do not use relationship_key for multi-column inventory balance formulas.",
            "- relationship_key is only for single-key parent-child aggregations like PurchaseOrderID.",
            "Do not execute formulas. Only describe them using FormulaRule objects.",
        ]
    )


def _date_rule_guidance_section() -> str:
    return "\n".join(
        [
            "J. Date Rule Guidance",
            "Create date rules only when those columns exist in metadata.",
            "- RequisitionDate <= OrderDate",
            "- OrderDate <= ShipmentDate",
            "- ShipmentDate <= ReceiptDate",
            "- ReceiptDate <= InspectionDate",
            "- InspectionDate <= InventoryPostingDate",
        ]
    )


def _quantity_rule_guidance_section() -> str:
    return "\n".join(
        [
            "K. Quantity Rule Guidance",
            "Create quantity rules only when those columns exist in metadata.",
            "- ShippedQuantity <= OrderedQuantity",
            "- ReceivedQuantity <= ShippedQuantity",
            "- AcceptedQuantity + RejectedQuantity = InspectedQuantity",
            "- InventoryTransaction.Quantity = AcceptedQuantity",
        ]
    )


def _status_rule_guidance_section() -> str:
    return "\n".join(
        [
            "L. Status Rule Guidance",
            "- Status values should be derived from lifecycle logic later.",
            "- Do not treat status as random if lifecycle context exists.",
            "- Use AllowedValues from metadata when present.",
        ]
    )


def _domain_profile_guidance_section() -> str:
    return "\n".join(
        [
            "M. Domain Profile Guidance",
            "- Use the business scenario to infer industry.",
            "- Produce vendor categories, material categories, material examples, specification patterns, warehouse types, plant locations, carrier patterns, and inspection test categories.",
            "- Material names must be industry-specific.",
            "- Vendor names must be supplier/manufacturer style.",
            "- Warehouse names should be location plus warehouse function.",
            "- No artificial numeric suffixes for duplicate names.",
            "- If not enough unique names can be generated later, Python should fail clearly.",
        ]
    )


def _output_contract_section() -> str:
    return "\n".join(
        [
            "N. Output Contract",
            "Return only valid JSON matching the LLMGenerationPlan schema.",
            "Do not include markdown fences.",
            "Do not include explanations.",
        ]
    )


def _blank_if_none(value: object) -> str:
    return "" if value is None else str(value)
