from __future__ import annotations

from pathlib import Path

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.llm.prompt_builder import build_llm_planning_prompt


def test_prompt_includes_business_scenario() -> None:
    prompt = _build_prompt()

    assert "EV manufacturing procurement scenario" in prompt


def test_prompt_includes_all_table_names_from_schema() -> None:
    prompt = _build_prompt()

    assert "TableName: Vendor" in prompt
    assert "TableName: PurchaseOrderHeader" in prompt


def test_prompt_includes_column_names() -> None:
    prompt = _build_prompt()

    assert "ColumnName=VendorID" in prompt
    assert "ColumnName=VendorName" in prompt
    assert "ColumnName=PurchaseOrderID" in prompt


def test_prompt_includes_erd_relationships() -> None:
    prompt = _build_prompt()

    assert "Parent: Vendor" in prompt
    assert "Child: PurchaseOrderHeader" in prompt
    assert "Type: one_to_many" in prompt


def test_prompt_includes_json_only_hard_rule() -> None:
    prompt = _build_prompt()

    assert "Return JSON only." in prompt
    assert "Return only valid JSON matching the LLMGenerationPlan schema." in prompt


def test_prompt_includes_no_row_generation_hard_rule() -> None:
    prompt = _build_prompt()

    assert "Do not generate actual table rows." in prompt


def test_prompt_includes_no_invented_tables_or_columns_hard_rule() -> None:
    prompt = _build_prompt()

    assert "Do not invent table names." in prompt
    assert "Do not invent column names." in prompt


def test_prompt_includes_supported_generation_types() -> None:
    prompt = _build_prompt()

    assert "GenerationType:" in prompt
    assert "sequence_id" in prompt
    assert "vendor_name" in prompt
    assert "calculated" in prompt


def test_prompt_includes_formula_guidance() -> None:
    prompt = _build_prompt()

    assert "PurchaseOrderLine.LineAmount = OrderedQuantity * UnitPrice" in prompt
    assert "InventoryBalance.OnHandQuantity = SUM(InventoryTransaction.Quantity)" in prompt
    assert "For InventoryBalance formulas, use rule_type = inventory_balance." in prompt
    assert 'group_by_columns = ["RawMaterialID", "PlantID", "WarehouseID"]' in prompt
    assert "relationship_key is only for single-key parent-child aggregations like PurchaseOrderID." in prompt


def test_prompt_includes_depends_on_columns_same_table_hard_rule() -> None:
    prompt = _build_prompt()

    assert (
        "CRITICAL: For column_generation_rules.depends_on_columns, only include columns that exist in the SAME table as table_name."
        in prompt
    )
    assert "Do not include columns from parent/child tables." in prompt
    assert "Cross-table dependencies belong in date_rules, quantity_rules, formula_rules, or validation_rules." in prompt
    assert "Before returning JSON, verify every depends_on_columns entry exists in that table's column list." in prompt


def test_prompt_includes_json_skeleton() -> None:
    prompt = _build_prompt()

    assert '"module": "procurement"' in prompt
    assert '"domain_profile"' in prompt
    assert '"formula_rules"' in prompt


def test_prompt_can_be_saved_to_output_file(tmp_path: Path) -> None:
    prompt = _build_prompt()
    output_path = tmp_path / "llm_planning_prompt.txt"

    output_path.write_text(prompt, encoding="utf-8")

    assert output_path.exists()
    assert "LLMGenerationPlan" in output_path.read_text(encoding="utf-8")


def _build_prompt() -> str:
    return build_llm_planning_prompt(
        schema_contract=_schema(),
        relationships=[
            RelationshipContract(
                parent_table="Vendor",
                child_table="PurchaseOrderHeader",
                relationship_type="one_to_many",
                mermaid_symbol="||--o{",
                label="supplies",
                raw_line="Vendor ||--o{ PurchaseOrderHeader : supplies",
            )
        ],
        business_scenario="EV manufacturing procurement scenario",
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
                    ColumnContract(
                        column_name="VendorID",
                        data_type="int",
                        key_type="PK",
                        nullable="No",
                        generation_type="sequence_id",
                    ),
                    ColumnContract(
                        column_name="VendorName",
                        data_type="varchar(255)",
                        nullable="No",
                        generation_type="vendor_name",
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
        }
    )
