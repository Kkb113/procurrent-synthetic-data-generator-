from __future__ import annotations

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.erd.erd_validator import validate_erd_relationships
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_text


def test_valid_erd_matches_metadata_fk_relationships() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("SupplierMaster ||--o{ PurchaseOrderHdr : supplies")

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert result.report.warnings == []
    assert result.summary.relationships_detected == 1
    assert result.summary.metadata_fk_relationships_checked == 1
    assert result.summary.matched_relationships == 1


def test_erd_unknown_table_is_error() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("UnknownSupplier ||--o{ PurchaseOrderHdr : supplies")

    result = validate_erd_relationships(schema, relationships)

    assert not result.report.is_valid
    assert result.summary.unknown_erd_tables == 1
    assert any("UnknownSupplier" in issue.message for issue in result.report.errors)


def test_metadata_fk_missing_from_erd_is_warning() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("")

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert any(
        issue.message == "Metadata FK relationship SupplierMaster -> PurchaseOrderHdr is missing from ERD."
        for issue in result.report.warnings
    )


def test_erd_relationship_without_matching_fk_is_warning() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text(
        """
        SupplierMaster ||--o{ PurchaseOrderHdr : supplies
        SupplierMaster ||--o{ Warehouse : incorrect
        """
    )

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert any(
        issue.message == "ERD relationship has no matching metadata FK: SupplierMaster -> Warehouse."
        for issue in result.report.warnings
    )


def test_duplicate_erd_relationship_is_warning() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text(
        """
        SupplierMaster ||--o{ PurchaseOrderHdr : supplies
        SupplierMaster ||--o{ PurchaseOrderHdr : supplies_again
        """
    )

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert any(
        issue.message == "Duplicate ERD relationship detected: SupplierMaster -> PurchaseOrderHdr."
        for issue in result.report.warnings
    )


def test_direction_mismatch_warns_for_missing_metadata_relationship_and_no_matching_fk() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("PurchaseOrderHdr ||--o{ SupplierMaster : wrong_direction")

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    messages = [issue.message for issue in result.report.warnings]
    assert "Metadata FK relationship SupplierMaster -> PurchaseOrderHdr is missing from ERD." in messages
    assert "ERD relationship has no matching metadata FK: PurchaseOrderHdr -> SupplierMaster." in messages


def _schema_with_fk() -> SchemaContract:
    return SchemaContract(
        tables={
            "SupplierMaster": TableContract(
                table_name="SupplierMaster",
                process_order=1,
                area="Master",
                table_role="supplier_master",
                target_rows=10,
                columns=[
                    ColumnContract(
                        column_name="SupplierID",
                        data_type="int",
                        key_type="PK",
                        nullable="No",
                        generation_type="sequence_id",
                    ),
                ],
            ),
            "PurchaseOrderHdr": TableContract(
                table_name="PurchaseOrderHdr",
                process_order=2,
                area="Procurement",
                table_role="purchase_order_header",
                target_rows=10,
                columns=[
                    ColumnContract(
                        column_name="PurchaseOrderID",
                        data_type="int",
                        key_type="PK",
                        nullable="No",
                        generation_type="sequence_id",
                    ),
                    ColumnContract(
                        column_name="SupplierID",
                        data_type="int",
                        key_type="FK",
                        related_table="SupplierMaster",
                        related_column="SupplierID",
                        nullable="No",
                        generation_type="foreign_key",
                    ),
                ],
            ),
            "Warehouse": TableContract(
                table_name="Warehouse",
                process_order=3,
                area="Master",
                table_role="warehouse_dimension",
                target_rows=10,
                columns=[
                    ColumnContract(
                        column_name="WarehouseID",
                        data_type="int",
                        key_type="PK",
                        nullable="No",
                        generation_type="sequence_id",
                    ),
                ],
            ),
        }
    )
