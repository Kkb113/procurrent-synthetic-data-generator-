from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.audit.row_count_audit import RowCountAuditBuilder, RowCountAuditInput
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.metadata.metadata_reader import METADATA_SHEET_NAME


pytestmark = pytest.mark.unit


def test_row_count_audit_compares_expected_actual_and_extra_tables(tmp_path: Path) -> None:
    schema = SchemaContract(
        tables={
            "SupplierMaster": _table("SupplierMaster", "supplier_master", 3),
            "PurchaseOrderLine": _table("PurchaseOrderLine", "purchase_order_line", 4),
        }
    )

    result = RowCountAuditBuilder().build_for_schema(
        module_id="procurement",
        schema=schema,
        actual_counts={
            "SupplierMaster": 3,
            "PurchaseOrderLine": 2,
            "UnexpectedTable": 1,
        },
        output_folder=tmp_path,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    statuses = {table["table_name"]: table["status"] for table in payload["modules"][0]["tables"]}

    assert payload["summary"]["expected_rows"] == 7
    assert payload["summary"]["actual_rows"] == 6
    assert payload["summary"]["delta_rows"] == -1
    assert statuses["SupplierMaster"] == "matched"
    assert statuses["PurchaseOrderLine"] == "below_target"
    assert statuses["UnexpectedTable"] == "extra"
    assert "Row Count Audit" in result.markdown_path.read_text(encoding="utf-8")


def test_row_count_audit_builds_from_metadata_and_csv_folder(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.xlsx"
    data_folder = tmp_path / "final_data"
    data_folder.mkdir()
    pd.DataFrame([{"SupplierID": 1}, {"SupplierID": 2}]).to_csv(data_folder / "SupplierMaster.csv", index=False)
    _write_metadata(metadata_path, table_name="SupplierMaster", target_rows=2)

    result = RowCountAuditBuilder().build_for_inputs(
        [RowCountAuditInput(module_id="procurement", metadata_path=metadata_path, data_folder=data_folder)],
        tmp_path / "reports",
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert payload["modules"][0]["summary"]["matched_tables"] == 1
    assert payload["modules"][0]["tables"][0]["actual_rows"] == 2


def _table(table_name: str, table_role: str, target_rows: int) -> TableContract:
    return TableContract(
        table_name=table_name,
        process_order=1,
        area="Procurement",
        table_role=table_role,
        target_rows=target_rows,
        columns=[
            ColumnContract(
                column_name=f"{table_name}ID",
                data_type="int",
                key_type="PK",
                nullable="No",
                generation_type="sequence_id",
            )
        ],
    )


def _write_metadata(path: Path, *, table_name: str, target_rows: int) -> None:
    metadata = pd.DataFrame(
        [
            {
                "TableName": table_name,
                "ProcessOrder": 1,
                "Area": "Procurement",
                "TableRole": "supplier_master",
                "TargetRows": target_rows,
                "ColumnName": "SupplierID",
                "DataType": "int",
                "KeyType": "PK",
                "RelatedTable": None,
                "RelatedColumn": None,
                "Nullable": "No",
                "GenerationType": "sequence_id",
                "AllowedValues": None,
                "MinValue": None,
                "MaxValue": None,
                "Formula": None,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name=METADATA_SHEET_NAME, index=False)
