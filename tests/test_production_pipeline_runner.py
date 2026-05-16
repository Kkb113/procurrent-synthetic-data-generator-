from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from procurement_data_generator.modules.production.reconciler_rules import PRODUCTION_TABLES
from tests.test_production_transaction_generator import _UPSTREAM_TABLES, _generate


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_production_pipeline.py"
METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
ERD = ROOT / "input" / "production_v1_erd.mmd"
SCENARIO = ROOT / "input" / "production_v1_business_scenario.txt"
PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"

PROCUREMENT_TABLES = {
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "Inventory",
    "InventoryTransaction",
    "InventoryReceiptDetail",
    "SupplierMaster",
    "PurchaseOrderLine",
    "GoodsReceiptLine",
}


def test_run_production_pipeline_script_exists() -> None:
    assert SCRIPT.exists()


def test_production_pipeline_requires_upstream_procurement_data(tmp_path: Path) -> None:
    output = tmp_path / "runs"
    command = _pipeline_command(tmp_path / "missing_upstream", output, run_id="missing-upstream")

    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert completed.returncode != 0
    report = output / "missing-upstream" / "reports" / "production_pipeline_report.json"
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert "Missing required upstream Procurement tables" in " ".join(payload["errors"])


def test_production_pipeline_generates_21_table_run_folder_and_reports(tmp_path: Path) -> None:
    upstream = _write_upstream_fixture(tmp_path)
    output = tmp_path / "runs"
    command = _pipeline_command(upstream, output, run_id="production-pipeline-test")

    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_folder = output / "production-pipeline-test"
    master_data = run_folder / "master_data"
    transaction_data = run_folder / "transaction_data"
    final_data = run_folder / "final_data"
    reports = run_folder / "reports"

    assert master_data.exists()
    assert transaction_data.exists()
    assert final_data.exists()
    assert reports.exists()

    final_csvs = {path.stem for path in final_data.glob("*.csv")}
    assert final_csvs == set(PRODUCTION_TABLES)
    assert len(final_csvs) == 21
    assert final_csvs.isdisjoint(PROCUREMENT_TABLES)

    assert (reports / "production_pipeline_report.json").exists()
    assert (reports / "production_pipeline_report.md").exists()
    assert (reports / "production_data_quality_report.json").exists()
    assert (reports / "production_data_quality_report.md").exists()

    payload = json.loads((reports / "production_pipeline_report.json").read_text(encoding="utf-8"))
    assert payload["status"] in {"passed", "passed_with_warnings"}
    assert payload["validation_error_count"] == 0
    assert payload["final_data_csv_count"] == 21
    assert payload["generated_table_count"] == 21
    assert payload["validation_warning_count"] >= 0

    assert len(pd.read_csv(final_data / "ProductionGenealogy.csv")) > 0
    assert len(pd.read_csv(final_data / "MaterialIssueLine.csv")) > 0
    assert len(pd.read_csv(final_data / "FinishedGoodsInventory.csv")) > 0
    assert set(pd.read_csv(final_data / "ProductionShift.csv")["ShiftCode"]) == {"A"}

    plant_ids = set()
    warehouse_ids = set()
    for path in final_data.glob("*.csv"):
        frame = pd.read_csv(path)
        if "PlantID" in frame.columns:
            plant_ids.update(frame["PlantID"].dropna().astype(int).tolist())
        if "WarehouseID" in frame.columns:
            warehouse_ids.update(frame["WarehouseID"].dropna().astype(int).tolist())
    assert len(plant_ids) == 1
    assert len(warehouse_ids) == 1


def test_production_pipeline_does_not_modify_procurement_pipeline_script() -> None:
    text = (ROOT / "scripts" / "run_pipeline.py").read_text(encoding="utf-8")

    assert "run_production_pipeline" not in text
    assert "production_v1" not in text


def _pipeline_command(upstream: Path, output: Path, run_id: str) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--metadata",
        str(METADATA),
        "--erd",
        str(ERD),
        "--scenario",
        str(SCENARIO),
        "--plan",
        str(PLAN),
        "--upstream-data",
        str(upstream),
        "--output",
        str(output),
        "--seed",
        "42",
        "--run-id",
        run_id,
    ]


def _write_upstream_fixture(tmp_path: Path) -> Path:
    _tx_data, report, _master, upstream = _generate(tmp_path, seed=42)
    assert report.is_valid
    upstream_dir = tmp_path / "upstream_final_data"
    upstream_dir.mkdir()
    for table_name in _UPSTREAM_TABLES:
        upstream[table_name].to_csv(upstream_dir / f"{table_name}.csv", index=False)
    return upstream_dir
