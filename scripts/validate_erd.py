"""CLI script for validating Mermaid ERD relationships against metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.erd.erd_validator import (
    format_erd_validation_result,
    validate_erd_relationships,
)
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.metadata.metadata_reader import (
    format_validation_report,
    load_metadata_schema,
)


def main() -> int:
    """Load metadata, parse Mermaid ERD, and validate relationships."""

    parser = argparse.ArgumentParser(description="Validate Mermaid ERD against metadata FK definitions.")
    parser.add_argument("xlsx_path", help="Path to the metadata XLSX file.")
    parser.add_argument("erd_path", help="Path to the Mermaid ERD text file.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.xlsx_path)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    erd_path = Path(args.erd_path)
    if not erd_path.exists():
        metadata_result.report.add_error(
            message=f"ERD file does not exist: {erd_path}",
            suggested_fix="Provide a valid path to a Mermaid ERD text file.",
        )
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    relationships = parse_mermaid_erd_file(erd_path)
    result = validate_erd_relationships(metadata_result.schema, relationships)
    print(format_erd_validation_result(result))
    return 0 if result.report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
