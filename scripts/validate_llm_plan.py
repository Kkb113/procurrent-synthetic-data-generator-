"""CLI script for validating an LLM generation plan JSON file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.llm.plan_loader import (
    format_llm_plan_validation_result,
    load_llm_plan_json,
)


def main() -> int:
    """Validate an LLM generation plan JSON file."""

    parser = argparse.ArgumentParser(description="Validate LLM generation plan JSON.")
    parser.add_argument("json_path", help="Path to the LLM generation plan JSON file.")
    args = parser.parse_args()

    result = load_llm_plan_json(args.json_path)
    print(format_llm_plan_validation_result(result))
    return 0 if result.report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
