"""SQL Server table creation and data loading layer."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from procurement_data_generator.core.contracts.schema_contract import SchemaContract, TableContract
from procurement_data_generator.core.contracts.sql_load_report import SQLLoadReport
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.ddl_generator import SQLDDLGenerator, quote_identifier


ConnectionFactory = Callable[[str], Any]


class SQLServerLoader:
    """Create SQL Server tables and load validated generated DataFrames."""

    def __init__(
        self,
        config: DatabaseConfig,
        connection_factory: ConnectionFactory | None = None,
        ddl_generator: SQLDDLGenerator | None = None,
    ) -> None:
        self.config = config
        self.connection_factory = connection_factory or _pyodbc_connect
        self.ddl = ddl_generator or SQLDDLGenerator(config.schema)
        self.connection = None

    def connect(self) -> Any:
        self.connection = self.connection_factory(self.config.build_pyodbc_connection_string())
        return self.connection

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def load_dataset(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        validation_report_path: str | Path | None = None,
        allow_unvalidated_load: bool = False,
    ) -> SQLLoadReport:
        report = SQLLoadReport()
        if not check_quality_gate(validation_report_path, allow_unvalidated_load, report):
            report.complete()
            return report

        try:
            self._check_required_tables(dataframes, schema)
            self.connect()
            cursor = self.connection.cursor()
            self.ensure_schema_exists(cursor)
            self.create_tables(cursor, schema, self.config.if_table_exists, report)
            self.insert_dataframes(cursor, dataframes, schema, report)
            self.create_constraints(cursor, schema, report)
            self.connection.commit()
        except Exception as exc:  # pragma: no cover - integration failures depend on local DB
            if self.connection is not None:
                try:
                    self.connection.rollback()
                except Exception:
                    pass
            report.add_error(f"SQL load failed: {exc}")
        finally:
            self.close()
            report.complete()
        return report

    def ensure_schema_exists(self, cursor: Any) -> None:
        cursor.execute(self.ddl.generate_create_schema_sql())

    def create_tables(self, cursor: Any, schema: SchemaContract, if_table_exists: str, report: SQLLoadReport) -> None:
        ordered = self.ddl.dependency_order(schema)
        if if_table_exists == "replace":
            for table in reversed(ordered):
                cursor.execute(self.ddl.generate_drop_table_sql(table.table_name))
        elif if_table_exists == "fail":
            for table in ordered:
                cursor.execute(self.ddl.generate_table_exists_sql(table.table_name))
                if cursor.fetchone():
                    raise RuntimeError(f"Table already exists: {self.config.schema}.{table.table_name}")

        if if_table_exists in {"replace", "fail"}:
            for table in ordered:
                cursor.execute(self.ddl.generate_create_table_sql(table))
                report.tables_created.append(table.table_name)

    def insert_dataframes(
        self,
        cursor: Any,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        report: SQLLoadReport,
    ) -> None:
        if hasattr(cursor, "fast_executemany"):
            cursor.fast_executemany = True
        for table in self.ddl.dependency_order(schema):
            dataframe = dataframes[table.table_name]
            prepared, warnings = prepare_dataframe_for_sql(dataframe, table)
            for warning in warnings:
                report.add_warning(warning)
            if prepared.empty:
                report.tables_loaded.append(table.table_name)
                report.rows_inserted_by_table[table.table_name] = 0
                continue
            columns = [column.column_name for column in table.columns]
            placeholders = ", ".join("?" for _ in columns)
            column_sql = ", ".join(quote_identifier(column) for column in columns)
            insert_sql = f"INSERT INTO {self.ddl.qualified_table_name(table.table_name)} ({column_sql}) VALUES ({placeholders});"
            records = dataframe_to_records(prepared)
            for start in range(0, len(records), self.config.batch_size):
                cursor.executemany(insert_sql, records[start : start + self.config.batch_size])
            report.tables_loaded.append(table.table_name)
            report.rows_inserted_by_table[table.table_name] = len(records)

    def create_constraints(self, cursor: Any, schema: SchemaContract, report: SQLLoadReport) -> None:
        for table in self.ddl.dependency_order(schema):
            pk_sql = self.ddl.generate_pk_constraint_sql(table)
            if pk_sql:
                cursor.execute(pk_sql)
                report.pk_constraints_created.append(f"PK_{table.table_name}")
        for table in self.ddl.dependency_order(schema):
            for fk_sql in self.ddl.generate_fk_constraint_sql(table):
                cursor.execute(fk_sql)
                report.fk_constraints_created.append(_constraint_name_from_fk_sql(fk_sql))

    def _check_required_tables(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract) -> None:
        missing = [table.table_name for table in schema.ordered_tables if table.table_name not in dataframes]
        if missing:
            raise ValueError("Missing generated data for required table(s): " + ", ".join(missing))


def load_csv_folders(data_folders: list[str | Path]) -> dict[str, pd.DataFrame]:
    """Load CSV files from folders, letting later folders override earlier tables."""

    dataframes: dict[str, pd.DataFrame] = {}
    for folder in data_folders:
        path = Path(folder)
        if not path.exists():
            continue
        for csv_path in sorted(path.glob("*.csv")):
            dataframes[csv_path.stem] = pd.read_csv(csv_path)
    return dataframes


def check_quality_gate(
    validation_report_path: str | Path | None,
    allow_unvalidated_load: bool,
    report: SQLLoadReport,
) -> bool:
    """Block SQL loading unless Phase 11 report passed or warnings are explicitly accepted."""

    if validation_report_path is None:
        if allow_unvalidated_load:
            report.add_warning("SQL load allowed without a data quality report because --allow-unvalidated-load was used.")
            return True
        report.add_error("SQL load blocked: data quality report is missing.")
        return False

    path = Path(validation_report_path)
    if not path.exists():
        if allow_unvalidated_load:
            report.add_warning(f"SQL load allowed without data quality report because --allow-unvalidated-load was used: {path}")
            return True
        report.add_error(f"SQL load blocked: data quality report not found: {path}")
        return False

    payload = json.loads(path.read_text(encoding="utf-8"))
    status = payload.get("overall_status")
    if status == "failed":
        report.add_error("SQL load blocked: data quality report status is failed.")
        return False
    if status not in {"passed", "passed_with_warnings"}:
        report.add_error(f"SQL load blocked: unsupported data quality status {status!r}.")
        return False
    if status == "passed_with_warnings":
        report.add_warning("Data quality report passed with warnings; SQL load is allowed.")
    return True


def prepare_dataframe_for_sql(dataframe: pd.DataFrame, table: TableContract) -> tuple[pd.DataFrame, list[str]]:
    """Select metadata columns, reject bad values, and prepare values for pyodbc inserts."""

    warnings: list[str] = []
    metadata_columns = [column.column_name for column in table.columns]
    missing = [column.column_name for column in table.columns if column.column_name not in dataframe.columns]
    if missing:
        raise ValueError(f"{table.table_name} is missing required metadata column(s): {', '.join(missing)}")
    extra = [column for column in dataframe.columns if column not in metadata_columns]
    if extra:
        warnings.append(f"{table.table_name}: ignoring extra DataFrame columns: {', '.join(extra)}")
    prepared = dataframe[metadata_columns].copy()
    if contains_infinity(prepared):
        raise ValueError(f"{table.table_name} contains positive or negative Infinity values.")
    prepared = prepared.astype(object).where(pd.notna(prepared), None)
    return prepared, warnings


def dataframe_to_records(dataframe: pd.DataFrame) -> list[tuple[Any, ...]]:
    """Convert a prepared DataFrame to pyodbc-friendly tuples."""

    records: list[tuple[Any, ...]] = []
    for row in dataframe.itertuples(index=False, name=None):
        records.append(tuple(_python_scalar(value) for value in row))
    return records


def contains_infinity(dataframe: pd.DataFrame) -> bool:
    numeric = dataframe.apply(pd.to_numeric, errors="coerce")
    return bool(np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any())


def save_sql_load_report(report: SQLLoadReport, output_folder: str | Path = "output") -> tuple[Path, Path]:
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "sql_load_report.json"
    markdown_path = output_path / "sql_load_report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    markdown_path.write_text(format_sql_load_report_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def format_sql_load_report(report: SQLLoadReport, json_path: Path | None = None, markdown_path: Path | None = None) -> str:
    lines = [
        "SQL load completed." if report.status == "passed" else "SQL load failed.",
        f"Tables created: {len(report.tables_created)}",
        f"Tables loaded: {len(report.tables_loaded)}",
        f"Total rows inserted: {report.total_rows_inserted}",
        f"PK constraints created: {len(report.pk_constraints_created)}",
        f"FK constraints created: {len(report.fk_constraints_created)}",
        f"Warnings: {len(report.warnings)}",
        f"Errors: {len(report.errors)}",
        f"SQL load status: {report.status}",
    ]
    if json_path:
        lines.append(f"Report JSON: {json_path}")
    if markdown_path:
        lines.append(f"Report Markdown: {markdown_path}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, error in enumerate(report.errors, start=1):
            lines.append(f"{index}. {error}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, warning in enumerate(report.warnings, start=1):
            lines.append(f"{index}. {warning}")
    return "\n".join(lines)


def format_sql_load_report_markdown(report: SQLLoadReport) -> str:
    lines = [
        "# SQL Load Report",
        "",
        f"- Status: {report.status}",
        f"- Tables created: {len(report.tables_created)}",
        f"- Tables loaded: {len(report.tables_loaded)}",
        f"- Total rows inserted: {report.total_rows_inserted}",
        f"- PK constraints created: {len(report.pk_constraints_created)}",
        f"- FK constraints created: {len(report.fk_constraints_created)}",
        "",
        "## Rows Inserted",
        "",
    ]
    if report.rows_inserted_by_table:
        for table_name, count in report.rows_inserted_by_table.items():
            lines.append(f"- {table_name}: {count}")
    else:
        lines.append("No rows inserted.")
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report.errors)
    return "\n".join(lines)


def _pyodbc_connect(connection_string: str) -> Any:
    import pyodbc

    return pyodbc.connect(connection_string)


def _python_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if math.isnan(float(value)):
            return None
        return float(value)
    return value


def _constraint_name_from_fk_sql(statement: str) -> str:
    marker = "CONSTRAINT "
    if marker not in statement:
        return "FK_UNKNOWN"
    raw = statement.split(marker, 1)[1].split(" ", 1)[0]
    return raw.strip("[]").replace("]]", "]")
