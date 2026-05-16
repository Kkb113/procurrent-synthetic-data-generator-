from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.ddl_generator import SQLDDLGenerator
from procurement_data_generator.core.sql.sql_loader import (
    SQLServerLoader,
    check_quality_gate,
    contains_infinity,
    dataframe_to_records,
    load_csv_folders,
    prepare_dataframe_for_sql,
)
from procurement_data_generator.core.contracts.sql_load_report import SQLLoadReport


def test_config_parsing_from_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "DB_SERVER=test-server",
                "DB_NAME=TestDb",
                "DB_SCHEMA=stage",
                "DB_DRIVER=ODBC Driver 18 for SQL Server",
                "DB_TRUSTED_CONNECTION=no",
                "DB_USERNAME=sa",
                "DB_PASSWORD=secret",
                "IF_TABLE_EXISTS=append",
                "BATCH_SIZE=25",
            ]
        ),
        encoding="utf-8",
    )

    config = DatabaseConfig.from_env(env_path)

    assert config.server == "test-server"
    assert config.database == "TestDb"
    assert config.schema == "stage"
    assert config.trusted_connection is False
    assert config.username == "sa"
    assert config.password == "secret"
    assert config.if_table_exists == "append"
    assert config.batch_size == 25
    assert "PWD=secret" in config.build_pyodbc_connection_string()
    assert config.masked_summary()["password"] == "***"


def test_table_create_order_respects_fk_dependencies() -> None:
    order = [table.table_name for table in SQLDDLGenerator().dependency_order(_schema())]

    assert order.index("SupplierMaster") < order.index("PurchaseOrderHdr")
    assert order.index("PurchaseOrderHdr") < order.index("PurchaseOrderLine")


def test_replace_mode_uses_reverse_dependency_drop_order() -> None:
    connection = FakeConnection()
    loader = SQLServerLoader(_config(), connection_factory=lambda _: connection)
    report = loader.load_dataset(_dataframes(), _schema(), allow_unvalidated_load=True)
    drop_sql = [sql for sql in connection.cursor_obj.executed if sql.startswith("IF OBJECT_ID")]

    assert report.status == "passed"
    assert "PurchaseOrderLine" in drop_sql[0]
    assert "SupplierMaster" in drop_sql[-1]


def test_later_data_folder_overrides_earlier_table_csv(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    pd.DataFrame({"SupplierID": [1], "SupplierName": ["Old"]}).to_csv(first / "SupplierMaster.csv", index=False)
    pd.DataFrame({"SupplierID": [2], "SupplierName": ["New"]}).to_csv(second / "SupplierMaster.csv", index=False)

    dataframes = load_csv_folders([first, second])

    assert list(dataframes["SupplierMaster"]["SupplierID"]) == [2]


def test_csv_loader_preserves_literal_none_values(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "ProductionQualityResult.csv").write_text("DefectSeverity\nNone\nLow\n", encoding="utf-8")

    dataframes = load_csv_folders([folder])

    assert list(dataframes["ProductionQualityResult"]["DefectSeverity"]) == ["None", "Low"]


def test_nullable_blank_strings_prepare_as_sql_null() -> None:
    table = TableContract(
        table_name="QualityExample",
        process_order=1,
        area="Production",
        table_role="quality_example",
        target_rows=1,
        columns=[
            _col("QualityID", "int", "sequence_id", "No", "PK"),
            _col("OptionalReason", "varchar(100)", "status", "Yes"),
        ],
    )
    dataframe = pd.DataFrame({"QualityID": [1], "OptionalReason": [""]})

    prepared, warnings = prepare_dataframe_for_sql(dataframe, table)
    records = dataframe_to_records(prepared)

    assert warnings == []
    assert records == [(1, None)]


def test_quality_report_failed_blocks_load(tmp_path: Path) -> None:
    path = _quality_report(tmp_path, "failed")
    report = SQLLoadReport()

    assert check_quality_gate(path, False, report) is False
    assert report.status == "failed"
    assert "failed" in report.errors[0]


def test_quality_report_passed_with_warnings_allows_load(tmp_path: Path) -> None:
    path = _quality_report(tmp_path, "passed_with_warnings")
    report = SQLLoadReport()

    assert check_quality_gate(path, False, report) is True
    assert report.warnings


def test_quality_gate_accepts_production_status_field(tmp_path: Path) -> None:
    path = tmp_path / "production_quality.json"
    path.write_text(json.dumps({"status": "passed_with_warnings", "errors": [], "warnings": [{}]}), encoding="utf-8")
    report = SQLLoadReport()

    assert check_quality_gate(path, False, report) is True
    assert report.warnings


def test_missing_quality_report_blocks_by_default(tmp_path: Path) -> None:
    report = SQLLoadReport()

    assert check_quality_gate(tmp_path / "missing.json", False, report) is False
    assert report.status == "failed"


def test_allow_unvalidated_load_allows_but_warns() -> None:
    report = SQLLoadReport()

    assert check_quality_gate(None, True, report) is True
    assert report.warnings


def test_nan_to_none_conversion_helper() -> None:
    dataframe = pd.DataFrame({"SupplierID": [1], "SupplierName": [np.nan]})
    prepared, warnings = prepare_dataframe_for_sql(dataframe, _schema().tables["SupplierMaster"])
    records = dataframe_to_records(prepared)

    assert warnings == []
    assert records == [(1, None)]


def test_infinity_detection_blocks_insert() -> None:
    dataframe = pd.DataFrame({"SupplierID": [1], "SupplierName": ["A"], "Extra": [np.inf]})

    assert contains_infinity(dataframe)


def test_metadata_column_order_selection_and_extra_warning() -> None:
    dataframe = pd.DataFrame({"SupplierName": ["A"], "Extra": ["ignored"], "SupplierID": [1]})
    prepared, warnings = prepare_dataframe_for_sql(dataframe, _schema().tables["SupplierMaster"])

    assert list(prepared.columns) == ["SupplierID", "SupplierName"]
    assert warnings and "ignoring extra" in warnings[0]


def test_missing_required_columns_error() -> None:
    dataframe = pd.DataFrame({"SupplierID": [1]})

    with pytest.raises(ValueError, match="missing required metadata"):
        prepare_dataframe_for_sql(dataframe, _schema().tables["SupplierMaster"])


def test_loader_blocks_infinity_before_insert() -> None:
    connection = FakeConnection()
    dataframes = _dataframes()
    dataframes["SupplierMaster"] = dataframes["SupplierMaster"].astype({"SupplierID": "float64"})
    dataframes["SupplierMaster"].loc[0, "SupplierID"] = np.inf
    loader = SQLServerLoader(_config(), connection_factory=lambda _: connection)

    report = loader.load_dataset(dataframes, _schema(), allow_unvalidated_load=True)

    assert report.status == "failed"
    assert "Infinity" in report.errors[0]


def test_quality_gate_blocks_failed_report_before_connection(tmp_path: Path) -> None:
    path = _quality_report(tmp_path, "failed")
    connection = FakeConnection()
    loader = SQLServerLoader(_config(), connection_factory=lambda _: connection)

    report = loader.load_dataset(_dataframes(), _schema(), validation_report_path=path)

    assert report.status == "failed"
    assert connection.cursor_created is False


def test_loader_skips_fk_constraints_to_external_parent_tables() -> None:
    schema = SchemaContract(
        tables={
            "ProductionExample": TableContract(
                table_name="ProductionExample",
                process_order=1,
                area="Production",
                table_role="production_example",
                target_rows=1,
                columns=[
                    _col("ProductionExampleID", "int", "sequence_id", "No", "PK"),
                    _col("PlantID", "int", "foreign_key", "No", "FK", "Plant", "PlantID"),
                ],
            )
        }
    )
    dataframes = {"ProductionExample": pd.DataFrame({"ProductionExampleID": [1], "PlantID": [1]})}
    connection = FakeConnection()
    loader = SQLServerLoader(_config(), connection_factory=lambda _: connection)

    report = loader.load_dataset(dataframes, schema, allow_unvalidated_load=True)

    assert report.status == "passed"
    assert report.tables_loaded == ["ProductionExample"]
    assert report.pk_constraints_created == ["PK_ProductionExample"]
    assert report.fk_constraints_created == []
    assert any("skipping FK constraint to external table Plant" in warning for warning in report.warnings)


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.cursor_created = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        self.cursor_created = True
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.executemany_calls: list[tuple[str, list[tuple]]] = []
        self.fast_executemany = False

    def execute(self, sql: str):
        self.executed.append(sql)
        return self

    def executemany(self, sql: str, records: list[tuple]):
        self.executemany_calls.append((sql, records))
        return self

    def fetchone(self):
        return None


def _config() -> DatabaseConfig:
    return DatabaseConfig(batch_size=2)


def _quality_report(tmp_path: Path, status: str) -> Path:
    path = tmp_path / "quality.json"
    path.write_text(json.dumps({"overall_status": status}), encoding="utf-8")
    return path


def _dataframes() -> dict[str, pd.DataFrame]:
    return {
        "SupplierMaster": pd.DataFrame({"SupplierID": [1], "SupplierName": ["Apex"]}),
        "PurchaseOrderHdr": pd.DataFrame({"PurchaseOrderID": [10], "SupplierID": [1], "TotalAmount": [20.0]}),
        "PurchaseOrderLine": pd.DataFrame({"PurchaseOrderLineID": [100], "PurchaseOrderID": [10], "LineAmount": [20.0]}),
    }


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "SupplierMaster": TableContract(
                table_name="SupplierMaster",
                process_order=1,
                area="Master",
                table_role="supplier_master",
                target_rows=1,
                columns=[
                    _col("SupplierID", "int", "sequence_id", "No", "PK"),
                    _col("SupplierName", "varchar(200)", "vendor_name", "No"),
                ],
            ),
            "PurchaseOrderHdr": TableContract(
                table_name="PurchaseOrderHdr",
                process_order=2,
                area="Procurement",
                table_role="purchase_order_header",
                target_rows=1,
                columns=[
                    _col("PurchaseOrderID", "int", "sequence_id", "No", "PK"),
                    _col("SupplierID", "int", "foreign_key", "No", "FK", "SupplierMaster", "SupplierID"),
                    _col("TotalAmount", "decimal(18,2)", "decimal_range", "No"),
                ],
            ),
            "PurchaseOrderLine": TableContract(
                table_name="PurchaseOrderLine",
                process_order=3,
                area="Procurement",
                table_role="purchase_order_line",
                target_rows=1,
                columns=[
                    _col("PurchaseOrderLineID", "int", "sequence_id", "No", "PK"),
                    _col("PurchaseOrderID", "int", "foreign_key", "No", "FK", "PurchaseOrderHdr", "PurchaseOrderID"),
                    _col("LineAmount", "decimal(18,2)", "decimal_range", "No"),
                ],
            ),
        }
    )


def _col(
    column_name: str,
    data_type: str,
    generation_type: str,
    nullable: str,
    key_type: str | None = None,
    related_table: str | None = None,
    related_column: str | None = None,
) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type=data_type,
        key_type=key_type,
        related_table=related_table,
        related_column=related_column,
        nullable=nullable,
        generation_type=generation_type,
    )
