"""CLI script for validating procurement table roles in metadata XLSX files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.metadata.metadata_reader import (
    format_validation_report,
    load_metadata_schema,
)
from procurement_data_generator.modules.procurement.role_validator import (
    format_procurement_role_validation_result,
    validate_procurement_roles,
)


def main() -> int:
    """Validate generic metadata first, then procurement role rules."""

    parser = argparse.ArgumentParser(description="Validate procurement metadata table roles.")
    parser.add_argument("xlsx_path", help="Path to the metadata XLSX file.")
    args = parser.parse_args()

    metadata_result = load_metadata_schema(args.xlsx_path)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        print(format_validation_report(metadata_result.report, metadata_result.schema))
        return 1

    role_result = validate_procurement_roles(metadata_result.schema, metadata_result.report)
    print(format_procurement_role_validation_result(role_result))
    return 0 if role_result.report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
