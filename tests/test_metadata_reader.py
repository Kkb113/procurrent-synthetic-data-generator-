from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


METADATA_COLUMNS = [
    "TableName",
    "ProcessOrder",
    "Area",
    "TableRole",
    "TargetRows",
    "ColumnName",
    "DataType",
    "KeyType",
    "RelatedTable",
    "RelatedColumn",
    "Nullable",
    "GenerationType",
    "AllowedValues",
    "MinValue",
    "MaxValue",
    "Formula",
]


def _write_metadata(path: Path, rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows, columns=METADATA_COLUMNS)
    df.to_excel(path, sheet_name="Metadata", index=False)


def test_valid_metadata_builds_schema(tmp_path: Path) -> None:
    path = tmp_path / "valid_metadata.xlsx"
    _write_metadata(
        path,
        [
            {
                "TableName": "SupplierMaster",
                "ProcessOrder": 1,
                "Area": "Master",
                "TableRole": "supplier_master",
                "TargetRows": 10,
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
            },
            {
                "TableName": "SupplierMaster",
                "ProcessOrder": 1,
                "Area": "Master",
                "TableRole": "supplier_master",
                "TargetRows": 10,
                "ColumnName": "SupplierName",
                "DataType": "varchar(255)",
                "KeyType": None,
                "RelatedTable": None,
                "RelatedColumn": None,
                "Nullable": "No",
                "GenerationType": "vendor_name",
                "AllowedValues": None,
                "MinValue": None,
                "MaxValue": None,
                "Formula": None,
            },
        ],
    )

    result = load_metadata_schema(path)

    assert result.report.is_valid
    assert result.schema is not None
    assert result.report.total_tables_detected == 1
    assert result.report.total_columns_detected == 2
    assert "SupplierMaster" in result.schema.tables


def test_invalid_metadata_reports_errors(tmp_path: Path) -> None:
    path = tmp_path / "invalid_metadata.xlsx"
    _write_metadata(
        path,
        [
            {
                "TableName": "PurchaseOrderLine",
                "ProcessOrder": 2,
                "Area": "BadArea",
                "TableRole": "purchase_order_line",
                "TargetRows": 0,
                "ColumnName": "PurchaseOrderID",
                "DataType": "int",
                "KeyType": "FK",
                "RelatedTable": None,
                "RelatedColumn": None,
                "Nullable": "No",
                "GenerationType": "foreign_key",
                "AllowedValues": None,
                "MinValue": None,
                "MaxValue": None,
                "Formula": None,
            },
            {
                "TableName": "PurchaseOrderLine",
                "ProcessOrder": 2,
                "Area": "Procurement",
                "TableRole": "purchase_order_line",
                "TargetRows": 10,
                "ColumnName": "BadGeneratedColumn",
                "DataType": "varchar(20)",
                "KeyType": None,
                "RelatedTable": None,
                "RelatedColumn": None,
                "Nullable": "No",
                "GenerationType": "unknown_generator",
                "AllowedValues": None,
                "MinValue": None,
                "MaxValue": None,
                "Formula": None,
            },
        ],
    )

    result = load_metadata_schema(path)

    assert not result.report.is_valid
    messages = [issue.message for issue in result.report.errors]
    assert "Table has 0 primary key columns; exactly one is required." in messages
    assert "FK column is missing RelatedTable or RelatedColumn." in messages
    assert any("Area 'BadArea' is not supported." == message for message in messages)
    assert any("GenerationType 'unknown_generator' is not supported." == message for message in messages)
    assert "TargetRows must be greater than 0." in messages
