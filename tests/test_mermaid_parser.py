from __future__ import annotations

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_text


def test_parse_one_to_many_relationship() -> None:
    relationships = parse_mermaid_erd_text(
        """
        erDiagram
            SupplierMaster ||--o{ PurchaseOrderHdr : supplies
        """
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.parent_table == "SupplierMaster"
    assert relationship.child_table == "PurchaseOrderHdr"
    assert relationship.relationship_type == "one_to_many"
    assert relationship.mermaid_symbol == "||--o{"
    assert relationship.label == "supplies"


def test_parse_one_to_one_relationship() -> None:
    relationships = parse_mermaid_erd_text(
        "GoodsReceiptLine ||--|| QualityInspectionHeader : inspected_by"
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.parent_table == "GoodsReceiptLine"
    assert relationship.child_table == "QualityInspectionHeader"
    assert relationship.relationship_type == "one_to_one"


def test_parse_reversed_many_to_one_relationship_normalizes_parent_child() -> None:
    relationships = parse_mermaid_erd_text(
        "PurchaseOrderHdr }o--|| SupplierMaster : supplied_by"
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.parent_table == "SupplierMaster"
    assert relationship.child_table == "PurchaseOrderHdr"
    assert relationship.relationship_type == "many_to_one"


def test_parser_ignores_header_blank_lines_and_comments() -> None:
    relationships = parse_mermaid_erd_text(
        """
        erDiagram
        %% a comment

        Plant ||--o{ Warehouse : contains %% trailing comment
        """
    )

    assert len(relationships) == 1
    assert relationships[0].parent_table == "Plant"
    assert relationships[0].child_table == "Warehouse"
    assert relationships[0].label == "contains"
