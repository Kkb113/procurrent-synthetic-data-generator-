from __future__ import annotations

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.erd.erd_validator import validate_erd_relationships
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_text


def test_valid_erd_matches_metadata_fk_relationships() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("Vendor ||--o{ PurchaseOrderHeader : supplies")

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert result.report.warnings == []
    assert result.summary.relationships_detected == 1
    assert result.summary.metadata_fk_relationships_checked == 1
    assert result.summary.matched_relationships == 1


def test_erd_unknown_table_is_error() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("UnknownSupplier ||--o{ PurchaseOrderHeader : supplies")

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
        issue.message == "Metadata FK relationship Vendor -> PurchaseOrderHeader is missing from ERD."
        for issue in result.report.warnings
    )


def test_erd_relationship_without_matching_fk_is_warning() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text(
        """
        Vendor ||--o{ PurchaseOrderHeader : supplies
        Vendor ||--o{ Warehouse : incorrect
        """
    )

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert any(
        issue.message == "ERD relationship has no matching metadata FK: Vendor -> Warehouse."
        for issue in result.report.warnings
    )


def test_duplicate_erd_relationship_is_warning() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text(
        """
        Vendor ||--o{ PurchaseOrderHeader : supplies
        Vendor ||--o{ PurchaseOrderHeader : supplies_again
        """
    )

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    assert any(
        issue.message == "Duplicate ERD relationship detected: Vendor -> PurchaseOrderHeader."
        for issue in result.report.warnings
    )


def test_direction_mismatch_warns_for_missing_metadata_relationship_and_no_matching_fk() -> None:
    schema = _schema_with_fk()
    relationships = parse_mermaid_erd_text("PurchaseOrderHeader ||--o{ Vendor : wrong_direction")

    result = validate_erd_relationships(schema, relationships)

    assert result.report.is_valid
    messages = [issue.message for issue in result.report.warnings]
    assert "Metadata FK relationship Vendor -> PurchaseOrderHeader is missing from ERD." in messages
    assert "ERD relationship has no matching metadata FK: PurchaseOrderHeader -> Vendor." in messages


def _schema_with_fk() -> SchemaContract:
    return SchemaContract(
        tables={
            "Vendor": TableContract(
                table_name="Vendor",
                process_order=1,
                area="Master",
                table_role="vendor_dimension",
                target_rows=10,
                columns=[
                    ColumnContract(
                        column_name="VendorID",
                        data_type="int",
                        key_type="PK",
                        nullable="No",
                        generation_type="sequence_id",
                    ),
                ],
            ),
            "PurchaseOrderHeader": TableContract(
                table_name="PurchaseOrderHeader",
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
                        column_name="VendorID",
                        data_type="int",
                        key_type="FK",
                        related_table="Vendor",
                        related_column="VendorID",
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
