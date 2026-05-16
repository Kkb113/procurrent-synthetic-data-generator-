from __future__ import annotations

from copy import deepcopy

import pytest

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.modules.procurement.role_catalog import PROCUREMENT_V2_ROLE_CATALOG, get_procurement_role_catalog
from procurement_data_generator.modules.procurement.role_validator import validate_procurement_roles


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
    "inventory_receipt_detail": "InventoryReceiptDetail",
    "inventory_transaction": "InventoryTransaction",
    "inventory": "Inventory",
    "supplier_invoice": "SupplierInvoice",
    "payment_transaction": "PaymentTransaction",
}


def test_procurement_role_catalog_active_model_contains_exactly_v2_roles() -> None:
    assert len(PROCUREMENT_V2_ROLE_CATALOG) == 25
    assert set(PROCUREMENT_V2_ROLE_CATALOG) == set(V2_ROLE_TO_TABLE_NAME)
    assert "inventory_receipt_detail" in PROCUREMENT_V2_ROLE_CATALOG
    assert "inventory" in PROCUREMENT_V2_ROLE_CATALOG
    assert "inventory_balance" not in PROCUREMENT_V2_ROLE_CATALOG


def test_procurement_v2_role_definitions_match_catalog_keys() -> None:
    for role_name, definition in PROCUREMENT_V2_ROLE_CATALOG.items():
        assert definition.role_name == role_name
        assert definition.expected_area
        assert definition.expected_process_stage


def test_procurement_v1_role_catalog_is_no_longer_supported() -> None:
    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        get_procurement_role_catalog("v1")


def test_procurement_v2_valid_schema_passes_role_validation() -> None:
    result = validate_procurement_roles(_build_valid_v2_schema(), model_version="v2")

    assert result.report.is_valid
    assert result.summary.expected_roles == 25
    assert result.summary.detected_roles == 25
    assert result.summary.unsupported_roles == 0
    assert result.summary.duplicate_roles == 0


def test_procurement_v2_missing_required_role_fails_validation() -> None:
    schema = _build_valid_v2_schema()
    del schema.tables["InventoryReceiptDetail"]

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert any("inventory_receipt_detail" in issue.message for issue in result.report.errors)


def test_procurement_v2_unsupported_role_fails_validation() -> None:
    schema = _build_valid_v2_schema()
    schema.tables["SupplierMaster"] = schema.tables["SupplierMaster"].model_copy(update={"table_role": "unknown_role"})

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert result.summary.unsupported_roles == 1


def test_procurement_v2_duplicate_role_fails_validation() -> None:
    schema = _build_valid_v2_schema()
    schema.tables["DuplicatePurchaseOrderHdr"] = schema.tables["PurchaseOrderHdr"].model_copy(
        update={"table_name": "DuplicatePurchaseOrderHdr"}
    )

    result = validate_procurement_roles(schema, model_version="v2")

    assert not result.report.is_valid
    assert result.summary.duplicate_roles == 1


def _build_valid_v2_schema() -> SchemaContract:
    tables: dict[str, TableContract] = {}
    for process_order, (role_name, definition) in enumerate(PROCUREMENT_V2_ROLE_CATALOG.items(), start=1):
        table_name = V2_ROLE_TO_TABLE_NAME[role_name]
        recommended_columns = list(definition.recommended_column_names) or [f"{table_name}ID"]
        columns = [_pk_column(recommended_columns[0])]
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
