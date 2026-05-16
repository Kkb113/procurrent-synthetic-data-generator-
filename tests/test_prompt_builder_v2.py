from __future__ import annotations

from pathlib import Path

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.llm.prompt_builder import build_llm_planning_prompt
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA = PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"
ERD = PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"
SCENARIO = PROJECT_ROOT / "input" / "procurement_v2_business_scenario.txt"

V2_TABLES = [
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
]


def test_build_llm_planning_prompt_supports_model_version_v2() -> None:
    prompt = _build_v2_prompt()

    assert "Procurement v2 Exact Model" in prompt


def test_v2_prompt_includes_all_25_table_names() -> None:
    prompt = _build_v2_prompt()

    for table_name in V2_TABLES:
        assert table_name in prompt


def test_v2_prompt_distinguishes_inventory_from_inventory_balance() -> None:
    prompt = _build_v2_prompt()

    assert "InventoryReceiptDetail is included in Procurement v2" in prompt
    assert "Inventory is included in Procurement v2" in prompt
    assert "Inventory should be calculated from InventoryTransaction" in prompt
    assert "InventoryBalance must not be generated or planned for Procurement v2." in prompt


def test_v2_prompt_includes_stockin_and_inventory_value_guidance() -> None:
    prompt = _build_v2_prompt()

    assert "InventoryReceiptDetail must be planned between InspectionResult and InventoryTransaction." in prompt
    assert "InventoryReceiptDetail.CrossYearDeliveryFlag" in prompt
    assert "InventoryTransaction.TransactionType must be StockIn" in prompt
    assert "InventoryTransaction should represent StockIn postings only" in prompt
    assert "InventoryValue must equal TransactionQuantity * UnitPrice" in prompt
    assert "Inventory.OnHandValue" in prompt
    assert "Inventory.AvailableValue" in prompt


def test_v2_prompt_says_inventory_balance_must_not_be_included() -> None:
    prompt = _build_v2_prompt()

    assert "InventoryBalance must not be generated or planned for Procurement v2." in prompt
    assert "- Do not include InventoryBalance." in prompt


def test_v2_prompt_includes_rfq_lifecycle() -> None:
    prompt = _build_v2_prompt()

    assert "PurchaseRequisition -> PurchaseReqLine -> RFQHeader -> RFQLine" in prompt
    assert "SupplierQuotation should be generated from RFQHeader." in prompt


def test_v2_prompt_includes_supplier_quotation_lifecycle() -> None:
    prompt = _build_v2_prompt()

    assert "SupplierQuotationLn should be generated from RFQLine." in prompt
    assert "PurchaseOrderHdr should be created from awarded SupplierQuotation." in prompt
    assert "PurchaseOrderLine should be created from awarded SupplierQuotationLn." in prompt


def test_v2_prompt_includes_po_schedule_lifecycle() -> None:
    prompt = _build_v2_prompt()

    assert "POSchedule should split PurchaseOrderLine delivery quantities." in prompt
    assert "ShipmentLine should be generated from POSchedule." in prompt


def test_v2_prompt_includes_supplier_invoice_and_payment_lifecycle() -> None:
    prompt = _build_v2_prompt()

    assert "SupplierInvoice should be generated after GoodsReceiptHeader." in prompt
    assert "PaymentTransaction should be generated after SupplierInvoice." in prompt


def test_v2_prompt_includes_us_only_location_requirement() -> None:
    prompt = _build_v2_prompt()

    assert "US-Only Location Guidance" in prompt
    assert "PlantCountry = USA." in prompt
    assert "WarehouseCountry = USA." in prompt
    assert "SupplierCountry = USA" in prompt


def test_v2_prompt_includes_usd_only_financial_requirement() -> None:
    prompt = _build_v2_prompt()

    assert "USD-Only Financial Guidance" in prompt
    assert "CurrencyCode must be USD where the column exists." in prompt
    assert "PaymentTransaction.PaymentAmount is in USD." in prompt


def test_v2_prompt_includes_lifecycle_based_status_realism() -> None:
    prompt = _build_v2_prompt()

    assert "Lifecycle-Based Status Realism" in prompt
    assert "POStatus = Received only" in prompt
    assert "LineStatus = Received only" in prompt
    assert "Statuses must be derived from lifecycle facts." in prompt
    assert "InventoryTransaction should be generated from InventoryReceiptDetail" in prompt
    assert "InventoryTransaction.UnitPrice = InventoryReceiptDetail.DeliveredUnitPrice" in prompt


def test_v2_prompt_includes_rejection_reason_realism() -> None:
    prompt = _build_v2_prompt()

    assert "Rejection Reason Realism" in prompt
    assert "If RejectedQuantity = 0, RejectionReason should be null" in prompt
    assert "Do not use the same rejection reason for all rows." in prompt


def test_v2_prompt_includes_depends_on_columns_same_table_rule() -> None:
    prompt = _build_v2_prompt()

    assert "depends_on_columns must contain same-table columns only." in prompt
    assert "LLM must not place cross-table fields in depends_on_columns." in prompt


def test_v2_prompt_includes_tolerance_guidance() -> None:
    prompt = _build_v2_prompt()

    assert "For money formulas, use tolerance_type absolute and tolerance_value 0.01" in prompt
    assert "For quantity formulas, use tolerance_type absolute and tolerance_value 0.0001." in prompt
    assert "Do not set tolerance_type = none for money/amount reconciliation." in prompt


def test_v2_prompt_includes_formula_guidance_for_v2_flow() -> None:
    prompt = _build_v2_prompt()

    assert "SupplierQuotationLn.QuotedLineAmount" in prompt
    assert "PurchaseOrderLine.LineAmount" in prompt
    assert "GoodsReceiptLine.ShortQuantity" in prompt
    assert "InspectionResult.RejectedQuantity" in prompt
    assert "SupplierInvoice.TotalInvoiceAmount" in prompt


def _build_v2_prompt() -> str:
    result = load_metadata_schema(METADATA)
    assert result.schema is not None

    return build_llm_planning_prompt(
        schema_contract=result.schema,
        relationships=parse_mermaid_erd_file(ERD),
        business_scenario=SCENARIO.read_text(encoding="utf-8"),
        model_version="v2",
    )
