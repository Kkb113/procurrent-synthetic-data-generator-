from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.llm.prompt_builder import build_llm_planning_prompt


def test_prompt_includes_business_scenario() -> None:
    prompt = _build_prompt()

    assert "EV manufacturing procurement scenario" in prompt


def test_prompt_uses_generic_mes_system_instruction() -> None:
    prompt = _build_prompt()

    assert "You are an MES synthetic data planning assistant." in prompt
    assert "You are a procurement data planning assistant." not in prompt


def test_prompt_explains_llm_plans_and_python_executes() -> None:
    prompt = _build_prompt()

    assert "LLM plans. Python validates. Python generates. Python calculates. Python reconciles." in prompt
    assert "Python owns primary key generation, foreign key consistency, formulas, reconciliation" in prompt


def test_prompt_includes_all_table_names_from_schema() -> None:
    prompt = _build_prompt()

    assert "TableName: SupplierMaster" in prompt
    assert "TableName: PurchaseOrderHdr" in prompt


def test_prompt_includes_column_names() -> None:
    prompt = _build_prompt()

    assert "ColumnName=SupplierID" in prompt
    assert "ColumnName=SupplierName" in prompt
    assert "ColumnName=PurchaseOrderID" in prompt


def test_prompt_includes_erd_relationships() -> None:
    prompt = _build_prompt()

    assert "Parent: SupplierMaster" in prompt
    assert "Child: PurchaseOrderHdr" in prompt
    assert "Type: one_to_many" in prompt


def test_prompt_includes_json_only_hard_rule() -> None:
    prompt = _build_prompt()

    assert "Return JSON only." in prompt
    assert "Return only valid JSON matching the LLMGenerationPlan schema." in prompt


def test_prompt_includes_no_row_generation_hard_rule() -> None:
    prompt = _build_prompt()

    assert "Do not generate raw rows." in prompt
    assert "Do not generate actual table rows." in prompt
    assert "Do not generate CSV data." in prompt
    assert "Do not generate SQL inserts." in prompt
    assert "Do not generate Python code." in prompt
    assert "Do not generate markdown." in prompt


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
    assert "Inventory.OnHandQuantity: can be expressed as a validation_rule for now" in prompt
    assert "InventoryReceiptDetail must be planned between InspectionResult and InventoryTransaction." in prompt
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


def test_prompt_builder_can_assemble_multi_module_prompt() -> None:
    prompt = build_llm_planning_prompt(
        schema_contract=_schema(),
        relationships=[],
        business_scenario="Integrated MES planning scenario.",
        module_ids=["procurement", "production"],
    )

    assert "Selected modules: procurement, production" in prompt
    assert "Procurement v2 Exact Model" in prompt
    assert "Production v1 Lifecycle Guidance" in prompt
    assert prompt.index("Procurement v2 Exact Model") < prompt.index("Production v1 Lifecycle Guidance")


def test_prompt_builder_unknown_module_fails_clearly() -> None:
    with pytest.raises(KeyError, match="Unknown module plugin 'quality'"):
        build_llm_planning_prompt(
            schema_contract=_schema(),
            relationships=[],
            business_scenario="Unknown module.",
            module_ids=["quality"],
        )


def test_core_prompt_builder_has_no_concrete_generator_imports() -> None:
    text = (Path(__file__).resolve().parents[1] / "procurement_data_generator" / "core" / "llm" / "prompt_builder.py").read_text(encoding="utf-8")

    assert "ProcurementMasterDataGenerator" not in text
    assert "ProcurementTransactionGenerator" not in text
    assert "ProductionMasterDataGenerator" not in text
    assert "ProductionTransactionGenerator" not in text


def test_prompt_can_be_saved_to_output_file(tmp_path: Path) -> None:
    prompt = _build_prompt()
    output_path = tmp_path / "llm_planning_prompt.txt"

    output_path.write_text(prompt, encoding="utf-8")

    assert output_path.exists()
    assert "LLMGenerationPlan" in output_path.read_text(encoding="utf-8")


def test_prompt_builder_rejects_procurement_v1_model_version() -> None:
    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        build_llm_planning_prompt(
            schema_contract=_schema(),
            relationships=[],
            business_scenario="Deprecated V1 request.",
            model_version="v1",
        )


def _build_prompt() -> str:
    return build_llm_planning_prompt(
        schema_contract=_schema(),
        relationships=[
            RelationshipContract(
                parent_table="SupplierMaster",
                child_table="PurchaseOrderHdr",
                relationship_type="one_to_many",
                mermaid_symbol="||--o{",
                label="supplies",
                raw_line="SupplierMaster ||--o{ PurchaseOrderHdr : supplies",
            )
        ],
        business_scenario="EV manufacturing procurement scenario",
        model_version="v2",
    )


def _schema() -> SchemaContract:
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
                    ColumnContract(
                        column_name="SupplierName",
                        data_type="varchar(255)",
                        nullable="No",
                        generation_type="vendor_name",
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
        }
    )
