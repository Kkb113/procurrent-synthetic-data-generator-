from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.production.data_validator import (
    validate_production_generated_data,
    write_production_quality_reports,
)
from tests.test_production_transaction_generator import _UPSTREAM_TABLES, _generate


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"


def test_data_validator_writes_json_and_markdown_reports(tmp_path) -> None:
    master_dir, transaction_dir, upstream_dir = _write_generated_files(tmp_path)
    schema = _schema()

    result = validate_production_generated_data(schema, master_dir, transaction_dir, upstream_dir)
    json_path, md_path = write_production_quality_reports(result, tmp_path / "validation")

    assert result.status in {"passed", "passed_with_warnings"}
    assert len(result.errors) == 0
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"passed", "passed_with_warnings"}
    assert payload["errors"] == []


def test_data_validator_fails_for_injected_invalid_data(tmp_path) -> None:
    master_dir, transaction_dir, upstream_dir = _write_generated_files(tmp_path)
    material_issue = pd.read_csv(transaction_dir / "MaterialIssueLine.csv")
    material_issue.loc[0, "IssuedQuantity"] = 9999999
    material_issue.to_csv(transaction_dir / "MaterialIssueLine.csv", index=False)

    result = validate_production_generated_data(_schema(), master_dir, transaction_dir, upstream_dir)

    assert result.status == "failed"
    assert result.errors


def test_data_validator_fails_for_shift_code_outside_operating_scope(tmp_path) -> None:
    master_dir, transaction_dir, upstream_dir = _write_generated_files(tmp_path)
    shift = pd.read_csv(master_dir / "ProductionShift.csv")
    shift.loc[0, "ShiftCode"] = "B"
    shift.to_csv(master_dir / "ProductionShift.csv", index=False)

    result = validate_production_generated_data(_schema(), master_dir, transaction_dir, upstream_dir)

    assert result.status == "failed"
    assert any(error.check_type == "PROD_OPERATING_SCOPE_SHIFT_CODE" for error in result.errors)


def test_validation_cli_script_runs_and_writes_reports(tmp_path) -> None:
    master_dir, transaction_dir, upstream_dir = _write_generated_files(tmp_path)
    output = tmp_path / "cli_validation"
    command = [
        sys.executable,
        "scripts/validate_production_generated_data.py",
        "--metadata",
        str(METADATA),
        "--plan",
        str(PLAN),
        "--master-data",
        str(master_dir),
        "--transaction-data",
        str(transaction_dir),
        "--upstream-data",
        str(upstream_dir),
        "--output",
        str(output),
    ]

    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (output / "production_data_quality_report.json").exists()
    assert (output / "production_data_quality_report.md").exists()


def _write_generated_files(tmp_path: Path):
    tx_data, report, master, upstream = _generate(tmp_path, seed=42)
    assert report.is_valid
    master_dir = tmp_path / "master"
    transaction_dir = tmp_path / "transaction"
    upstream_dir = tmp_path / "upstream"
    master_dir.mkdir()
    transaction_dir.mkdir()
    upstream_dir.mkdir()
    for table, dataframe in master.items():
        dataframe.to_csv(master_dir / f"{table}.csv", index=False)
    for table, dataframe in tx_data.items():
        dataframe.to_csv(transaction_dir / f"{table}.csv", index=False)
    for table in _UPSTREAM_TABLES:
        upstream[table].to_csv(upstream_dir / f"{table}.csv", index=False)
    return master_dir, transaction_dir, upstream_dir


def _schema():
    result = load_metadata_schema(METADATA)
    assert result.report.is_valid
    assert result.schema is not None
    return result.schema
