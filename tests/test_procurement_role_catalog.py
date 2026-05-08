from __future__ import annotations

from copy import deepcopy

import pytest

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.modules.procurement.role_catalog import (
    PROCUREMENT_ROLE_CATALOG,
    PROCUREMENT_V2_ROLE_CATALOG,
)
from procurement_data_generator.modules.procurement.role_validator import validate_procurement_roles


ROLE_TO_TABLE_NAME = {
    "vendor_dimension": "Vendor",
    "material_dimension": "RawMaterial",
    "plant_dimension": "Plant",
    "warehouse_dimension": "Warehouse",
    "purchase_requisition_header": "PurchaseRequisitionHeader",
    "purchase_requisition_line": "PurchaseRequisitionLine",
    "purchase_order_header": "PurchaseOrderHeader",
    "purchase_order_line": "PurchaseOrderLine",
    "shipment_header": "ShipmentHeader",
    "shipment_line": "ShipmentLine",
    "goods_receipt_header": "GoodsReceiptHeader",
    "goods_receipt_line": "GoodsReceiptLine",
    "quality_inspection_header": "QualityInspectionHeader",
    "quality_inspection_line": "QualityInspectionLine",
    "inventory_transaction": "InventoryTransaction",
    "inventory_balance": "InventoryBalance",
}

V2_ROLE_TO_TABLE_NAME = {
    "supplier_master": "SupplierMaster",
    "supplier_component": "SupplierComponent",
    "component_master": "ComponentMaster",
    "plant_dimension": "Plant",
    "warehouse_dimension": "Warehouse",
    "purchase_requisition": "PurchaseRequisition",
    "purchase_req_line": "PurchaseReqLine",
    "rfq_header": "RFQHeader",
    "rfq_line": "RFQLine",
    "supplier_quotation": "SupplierQuotation",
    "supplier_quotation_line": "SupplierQuotationLn",
    "purchase_order_header": "PurchaseOrderHdr",
    "purchase_order_line": "PurchaseOrderLine",
    "po_schedule": "POSchedule",
    "shipment_header": "ShipmentHdr",
    "shipment_line": "ShipmentLine",
    "goods_receipt_header": "GoodsReceiptHeader",
    "goods_receipt_line": "GoodsReceiptLine",
    "incoming_inspection": "IncomingInspection",
    "inspection_result": "InspectionResult",
    "inventory_transaction": "InventoryTransaction",
    "inventory": "Inventory",
    "supplier_invoice": "SupplierInvoice",
    "payment_transaction": "PaymentTransaction",
}

V2_EXPECTED_AREAS = {
    "SupplierMaster": "Master",
    "SupplierComponent": "Master",
    "ComponentMaster": "Master",
    "Plant": "Master",
    "Warehouse": "Master",
    "PurchaseRequisition": "Procurement",
    "PurchaseReqLine": "Procurement",
    "RFQHeader": "Procurement",
    "RFQLine": "Procurement",
    "SupplierQuotation": "Procurement",
    "SupplierQuotationLn": "Procurement",
    "PurchaseOrderHdr": "Procurement",
    "PurchaseOrderLine": "Procurement",
    "POSchedule": "Procurement",
    "ShipmentHdr": "Logistics",
    "ShipmentLine": "Logistics",
    "GoodsReceiptHeader": "Logistics",
    "GoodsReceiptLine": "Logistics",
    "IncomingInspection": "Quality",
    "InspectionResult": "Quality",
    "InventoryTransaction": "Inventory",
    "Inventory": "Inventory",
    "SupplierInvoice": "Finance",
    "PaymentTransaction": "Finance",
}


def test_procurement_role_catalog_contains_expected_16_roles() -> None:
    assert len(PROCUREMENT_ROLE_CATALOG) == 16
    assert set(PROCUREMENT_ROLE_CATALOG) == set(ROLE_TO_TABLE_NAME)


def test_procurement_v2_role_catalog_contains_exactly_expected_24_roles() -> None:
    assert len(PROCUREMENT_V2_ROLE_CATALOG) == 24
    assert set(PROCUREMENT_V2_ROLE_CATALOG) == set(V2_ROLE_TO_TABLE_NAME)
    assert "inventory" in PROCUREMENT_V2_ROLE_CATALOG
    assert "inventory_balance" not in PROCUREMENT_V2_ROLE_CATALOG


def test_procurement_v2_role_to_area_mapping_is_correct() -> None:
    for role_name, table_name in V2_ROLE_TO_TABLE_NAME.items():
        assert PROCUREMENT_V2_ROLE_CATALOG[role_name].expected_area == V2_EXPECTED_AREAS[table_name]


def test_procurement_v2_inventory_roles_recommend_refined_columns() -> None:
    inventory_transaction = PROCUREMENT_V2_ROLE_CATALOG["inventory_transaction"]
    inventory = PROCUREMENT_V2_ROLE_CATALOG["inventory"]

    assert {
        "GoodsReceiptLineID",
        "PurchaseOrderLineID",
        "SupplierID",
        "UnitPrice",
        "InventoryValue",
        "InventoryStatus",
    }.issubset(set(inventory_transaction.recommended_column_names))
    assert {"OnHandValue", "AvailableValue"}.issubset(set(inventory.recommended_column_names))


def test_valid_metadata_with_all_roles_passes_role_validation() -> None:
    schema = _build_valid_schema()

    result = validate_procurement_roles(schema)

    assert result.report.is_valid
    assert result.summary.expected_roles == 16
    assert result.summary.detected_roles == 16
    assert result.summary.unsupported_roles == 0
    assert result.summary.duplicate_roles == 0
    assert result.report.warnings == []


def test_v2_valid_schema_passes_role_validation() -> None:
    schema = _build_valid_v2_schema()

    result = validate_procurement_roles(schema, model_version="v2")

    assert result.report.is_valid
    assert result.summary.expected_roles == 24
    assert result.summary.detected_roles == 24
    assert result.summary.unsupported_roles == 0
    assert result.summary.duplicate_roles == 0
    assert result.report.warnings == []


def test_missing_role_fails_role_validation() -> None:
    schema = _build_valid_schema()
    del schema.tables["InventoryBalance"]

    result = validate_procurement_roles(schema)

    assert not result.report.is_valid
    assert any(
        issue.message == "Missing procurement table role: inventory_balance."
        for issue in result.report.errors
    )


def test_v2_missing_role_fails_role_validation() -> None:
    schema = _build_valid_v2_schema()
    del schema.tables["PaymentTransaction"]

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert any(
        issue.message == "Missing procurement table role: payment_transaction."
        for issue in result.report.errors
    )


def test_unsupported_role_fails_role_validation() -> None:
    schema = _build_valid_schema()
    schema.tables["Vendor"] = schema.tables["Vendor"].model_copy(update={"table_role": "unknown_role"})

    result = validate_procurement_roles(schema)

    assert not result.report.is_valid
    assert any(
        issue.message == "Unsupported procurement table role: unknown_role."
        for issue in result.report.errors
    )


def test_v2_unsupported_role_fails_role_validation() -> None:
    schema = _build_valid_v2_schema()
    schema.tables["SupplierMaster"] = schema.tables["SupplierMaster"].model_copy(update={"table_role": "unknown_role"})

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert any(
        issue.message == "Unsupported procurement table role: unknown_role."
        for issue in result.report.errors
    )


def test_inventory_balance_is_unsupported_in_strict_v2_mode() -> None:
    schema = _build_valid_v2_schema()
    schema.tables["InventoryBalance"] = TableContract(
        table_name="InventoryBalance",
        process_order=24,
        area="Inventory",
        table_role="inventory_balance",
        target_rows=10,
        columns=[_pk_column("InventoryBalanceID")],
    )

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert result.summary.unsupported_roles == 1
    assert any(
        issue.table_name == "InventoryBalance"
        and issue.message == "Unsupported procurement table role: inventory_balance."
        for issue in result.report.errors
    )


def test_area_mismatch_fails_role_validation() -> None:
    schema = _build_valid_schema()
    schema.tables["PurchaseOrderHeader"] = schema.tables["PurchaseOrderHeader"].model_copy(
        update={"area": "Master"}
    )

    result = validate_procurement_roles(schema)

    assert not result.report.is_valid
    assert any(
        issue.message
        == "Area mismatch for role purchase_order_header. Expected Procurement but found Master."
        for issue in result.report.errors
    )


def test_v2_duplicate_role_fails_role_validation() -> None:
    schema = _build_valid_v2_schema()
    schema.tables["DuplicatePurchaseOrderHdr"] = schema.tables["PurchaseOrderHdr"].model_copy(
        update={"table_name": "DuplicatePurchaseOrderHdr"}
    )

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert result.summary.duplicate_roles == 1
    assert any(
        issue.message.startswith("Duplicate procurement table role: purchase_order_header.")
        for issue in result.report.errors
    )


def test_finance_area_is_supported() -> None:
    table = TableContract(
        table_name="SupplierInvoice",
        process_order=1,
        area="Finance",
        table_role="supplier_invoice",
        target_rows=10,
        columns=[_pk_column("SupplierInvoiceID")],
    )

    assert table.area == "Finance"


def test_duplicate_role_fails_role_validation() -> None:
    schema = _build_valid_schema()
    schema.tables["DuplicatePurchaseOrderHeader"] = schema.tables["PurchaseOrderHeader"].model_copy(
        update={"table_name": "DuplicatePurchaseOrderHeader"}
    )

    result = validate_procurement_roles(schema)

    assert not result.report.is_valid
    assert result.summary.duplicate_roles == 1
    assert any(
        issue.message.startswith("Duplicate procurement table role: purchase_order_header.")
        for issue in result.report.errors
    )


@pytest.mark.parametrize(
    ("table_name", "role_name"),
    sorted((table, role) for role, table in ROLE_TO_TABLE_NAME.items()),
)
def test_recommended_column_warning_is_non_blocking(table_name: str, role_name: str) -> None:
    schema = _build_valid_schema()
    schema.tables[table_name] = schema.tables[table_name].model_copy(
        update={"columns": [_pk_column(f"{table_name}ID")]}
    )

    result = validate_procurement_roles(schema)

    assert result.report.is_valid
    assert any(
        issue.level == "warning" and role_name in issue.message
        for issue in result.report.warnings
    )


def _build_valid_schema() -> SchemaContract:
    return _build_schema_from_catalog(PROCUREMENT_ROLE_CATALOG, ROLE_TO_TABLE_NAME)


def _build_valid_v2_schema() -> SchemaContract:
    return _build_schema_from_catalog(PROCUREMENT_V2_ROLE_CATALOG, V2_ROLE_TO_TABLE_NAME)


def _build_schema_from_catalog(catalog, role_to_table_name) -> SchemaContract:
    tables: dict[str, TableContract] = {}
    for process_order, (role_name, definition) in enumerate(catalog.items(), start=1):
        table_name = role_to_table_name[role_name]
        recommended_columns = list(definition.recommended_column_names)
        if not recommended_columns:
            recommended_columns = [f"{table_name}ID"]
        pk_name = recommended_columns[0]
        columns = [_pk_column(pk_name)]
        columns.extend(_text_column(column_name) for column_name in recommended_columns[1:])
        tables[table_name] = TableContract(
            table_name=table_name,
            process_order=process_order,
            area=definition.expected_area,
            table_role=role_name,
            target_rows=10,
            columns=columns,
        )
    return SchemaContract(tables=deepcopy(tables))


def _pk_column(column_name: str) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type="int",
        key_type="PK",
        nullable="No",
        generation_type="sequence_id",
    )


def _text_column(column_name: str) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type="varchar(255)",
        nullable="Yes",
        generation_type="faker_company",
    )
