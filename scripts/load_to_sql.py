"""CLI script for Phase 12 SQL Server table creation and data loading."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.metadata.metadata_reader import format_validation_report, load_metadata_schema
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import (
    SQLServerLoader,
    format_sql_load_report,
    load_csv_folders,
    save_sql_load_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load validated generated procurement CSV data to local SQL Server.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--data-folder", action="append", required=True, help="Generated CSV folder. May be repeated; later folders override earlier tables.")
    parser.add_argument("--quality-report", required=False, help="Path to Phase 11 data_quality_report.json.")
    parser.add_argument("--allow-unvalidated-load", action="store_true", help="Allow loading without a Phase 11 data quality report.")
    parser.add_argument("--if-table-exists", choices=["replace", "append", "fail"], help="Override IF_TABLE_EXISTS from .env.")
    parser.add_argument("--env", help="Optional .env path.")
    parser.add_argument("--report-folder", default="output", help="Folder for SQL load report files.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.metadata)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    try:
        config = DatabaseConfig.from_env(args.env, if_table_exists_override=args.if_table_exists)
    except ValueError as exc:
        print(f"Invalid database configuration: {exc}")
        return 1

    dataframes = load_csv_folders(args.data_folder)
    loader = SQLServerLoader(config)
    report = loader.load_dataset(
        dataframes,
        metadata_result.schema,
        validation_report_path=args.quality_report,
        allow_unvalidated_load=args.allow_unvalidated_load,
    )
    json_path, markdown_path = save_sql_load_report(report, args.report_folder)

    print(f"Database: {config.database}")
    print(f"Schema: {config.schema}")
    print(format_sql_load_report(report, json_path, markdown_path))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
