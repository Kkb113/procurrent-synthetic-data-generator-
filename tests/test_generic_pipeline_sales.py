from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from procurement_data_generator.core.contracts.sql_load_report import SQLLoadReport
from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.pipeline.generic_runner import (
    ModuleDependencyError,
    ModulePipelineInput,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES


ROOT = Path(__file__).resolve().parents[1]
PROC_METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PROC_ERD = ROOT / "input" / "procurement_v2_erd.mmd"
PROC_SCENARIO = ROOT / "input" / "procurement_v2_business_scenario.txt"
PROC_PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
PROD_METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PROD_ERD = ROOT / "input" / "production_v1_erd.mmd"
PROD_SCENARIO = ROOT / "input" / "production_v1_business_scenario.txt"
PROD_PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
SALES_METADATA = ROOT / "input" / "sales_v1_metadata.xlsx"
SALES_ERD = ROOT / "input" / "sales_v1_erd.mmd"


@pytest.fixture(scope="module")
def full_chain_result(tmp_path_factory):
    output_folder = tmp_path_factory.mktemp("generic_sales_full_chain")
    result = SyntheticDataPipelineRunner().run(_full_chain_spec(output_folder))
    return result


@pytest.mark.pipeline
def test_generic_runner_executes_procurement_production_sales(full_chain_result) -> None:
    result = full_chain_result

    assert result.status in {"passed", "passed_with_warnings"}
    assert result.module_ids == ("procurement", "production", "sales")
    assert tuple(result.module_results) == ("procurement", "production", "sales")


@pytest.mark.pipeline
def test_phase0_full_chain_smoke_guardrail(full_chain_result) -> None:
    result = full_chain_result
    audit_path = Path(result.output_folder) / "reports" / "row_count_audit.json"

    assert result.status in {"passed", "passed_with_warnings"}
    assert result.module_results["procurement"].tables_generated == 25
    assert result.module_results["production"].tables_generated == 21
    assert result.module_results["sales"].tables_generated == 18
    assert result.row_count_audit_paths["json"] == str(audit_path)
    assert audit_path.exists()


@pytest.mark.pipeline
def test_phase1_sales_metadata_schema_wiring_uses_sales_order_target(full_chain_result) -> None:
    sales_result = full_chain_result.module_results["sales"]

    assert sales_result.report.row_counts_by_table["SalesOrderHdr"] > 12


@pytest.mark.pipeline
def test_phase1_row_count_audit_reports_sales_expected_and_actual_rows(full_chain_result) -> None:
    audit_path = Path(full_chain_result.row_count_audit_paths["json"])
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    sales_module = next(module for module in payload["modules"] if module["module_id"] == "sales")
    sales_order = next(table for table in sales_module["tables"] if table["table_name"] == "SalesOrderHdr")

    assert sales_order["expected_rows"] == 500
    assert sales_order["actual_rows"] == full_chain_result.module_results["sales"].report.row_counts_by_table["SalesOrderHdr"]
    assert sales_order["delta_rows"] == sales_order["actual_rows"] - sales_order["expected_rows"]
    assert sales_order["status"] in {"matched", "below_target", "above_target"}


@pytest.mark.pipeline
def test_full_chain_table_counts_and_sales_outputs(full_chain_result) -> None:
    result = full_chain_result

    assert result.module_results["procurement"].tables_generated == 25
    assert result.module_results["production"].tables_generated == 21
    assert result.module_results["sales"].tables_generated == 18

    sales_final = Path(result.module_results["sales"].output_folder) / "final_data"
    sales_tables = {path.stem for path in sales_final.glob("*.csv")}
    assert sales_tables == set(SALES_V1_EXPECTED_TABLES)
    assert "SalesCreditMemo" not in sales_tables
    for table_name in (
        "CustomerMaster",
        "SalesOrderHdr",
        "SalesShipmentLine",
        "SalesInvoiceHeader",
        "CustomerPaymentReceipt",
        "SalesReturnHeader",
        "SalesShipmentTraceability",
    ):
        assert (sales_final / f"{table_name}.csv").exists()


@pytest.mark.pipeline
def test_full_chain_sales_validation_passes(full_chain_result) -> None:
    sales_result = full_chain_result.module_results["sales"]

    assert sales_result.data_quality_status == "passed"
    assert sales_result.report.validation_report is not None
    assert sales_result.report.validation_report.overall_status == "passed"
    assert sales_result.report.validation_report.error_count == 0


@pytest.mark.pipeline
def test_combined_final_data_uses_sales_adjusted_finished_goods_inventory(full_chain_result) -> None:
    result = full_chain_result
    production_final = Path(result.module_results["production"].output_folder) / "final_data"
    sales_final = Path(result.module_results["sales"].output_folder) / "final_data"
    combined_final = Path(result.output_folder) / "final_data"

    assert (combined_final / "FinishedGoodsInventory.csv").exists()
    adjusted_artifact = pd.read_csv(result.module_results["sales"].report.adjusted_finished_goods_inventory_path)
    combined_inventory = pd.read_csv(combined_final / "FinishedGoodsInventory.csv")
    pd.testing.assert_frame_equal(combined_inventory, adjusted_artifact)

    expected = _expected_finished_goods_inventory(
        original_inventory=pd.read_csv(production_final / "FinishedGoodsInventory.csv"),
        receipts=pd.read_csv(production_final / "FinishedGoodsReceipt.csv"),
        shipment_lines=pd.read_csv(sales_final / "SalesShipmentLine.csv"),
        reservations=pd.read_csv(sales_final / "SalesInventoryReservation.csv"),
        return_lines=pd.read_csv(sales_final / "SalesReturnLine.csv"),
    )
    merged = combined_inventory.merge(
        expected,
        on=["FinishedGoodsInventoryID", "ProductID", "PlantID", "WarehouseID"],
        suffixes=("", "_expected"),
    )

    assert (merged["OnHandQuantity"].round(2) == merged["OnHandQuantity_expected"].round(2)).all()
    assert (merged["ReservedQuantity"].round(2) == merged["ReservedQuantity_expected"].round(2)).all()
    assert (merged["AvailableQuantity"].round(2) == merged["AvailableQuantity_expected"].round(2)).all()


@pytest.mark.parametrize(
    "module_ids",
    [
        ("sales",),
        ("procurement", "sales"),
        ("production", "sales"),
        ("sales", "production"),
        ("sales", "procurement"),
        ("procurement", "sales", "production"),
    ],
)
def test_invalid_sales_module_flows_fail_clearly(tmp_path: Path, module_ids: tuple[str, ...]) -> None:
    with pytest.raises(ModuleDependencyError, match="Sales requires upstream Procurement and Production data"):
        SyntheticDataPipelineRunner().run(_full_chain_spec(tmp_path, module_ids=module_ids))


@pytest.mark.pipeline
def test_food_profile_full_chain_sales_data_has_no_ev_vocabulary(full_chain_result) -> None:
    sales_final = Path(full_chain_result.module_results["sales"].output_folder) / "final_data"
    text_values: list[str] = []
    for csv_path in sales_final.glob("*.csv"):
        dataframe = pd.read_csv(csv_path)
        text_values.extend(
            str(value)
            for value in dataframe.select_dtypes(include="object").to_numpy().ravel()
            if pd.notna(value)
        )
    text = " ".join(text_values).lower()

    for term in ("battery", "automotive", "chassis", "drive unit", "power electronics", "dealer", "fleet"):
        assert term not in text
    assert re.search(r"(?<![a-z])ev(?![a-z])", text, flags=re.IGNORECASE) is None


@pytest.mark.pipeline
def test_full_chain_sql_load_includes_sales_tables(tmp_path: Path) -> None:
    loaded_tables: list[set[str]] = []
    loaded_frames: list[dict[str, pd.DataFrame]] = []

    class RecordingSQLLoader:
        def __init__(self, _config) -> None:
            pass

        def load_dataset(self, dataframes, schema, validation_report_path=None, allow_unvalidated_load=False):
            report = SQLLoadReport()
            report.tables_loaded = [table.table_name for table in schema.ordered_tables]
            report.rows_inserted_by_table = {
                table_name: len(dataframes[table_name])
                for table_name in report.tables_loaded
            }
            report.complete()
            loaded_tables.append(set(report.tables_loaded))
            loaded_frames.append({table_name: dataframes[table_name].copy() for table_name in report.tables_loaded})
            return report

    result = SyntheticDataPipelineRunner(sql_loader_factory=RecordingSQLLoader).run(
        _full_chain_spec(tmp_path, load_sql=True)
    )

    assert result.status in {"passed", "passed_with_warnings"}
    assert len(loaded_tables) == 4
    assert len(loaded_tables[0]) == 25
    assert len(loaded_tables[1]) == 21
    assert loaded_tables[2] == set(SALES_V1_EXPECTED_TABLES)
    assert "SalesCreditMemo" not in loaded_tables[2]
    assert loaded_tables[3] == {"FinishedGoodsInventory"}

    adjusted_loaded = loaded_frames[3]["FinishedGoodsInventory"].reset_index(drop=True)
    adjusted_artifact = pd.read_csv(
        result.module_results["sales"].report.adjusted_finished_goods_inventory_path
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(adjusted_loaded, adjusted_artifact, check_dtype=False)

    production_inventory = pd.read_csv(
        Path(result.module_results["production"].output_folder) / "final_data" / "FinishedGoodsInventory.csv"
    )
    merged = adjusted_loaded.merge(
        production_inventory,
        on="FinishedGoodsInventoryID",
        suffixes=("_adjusted", "_production"),
    )
    assert (
        (merged["OnHandQuantity_adjusted"].round(2) != merged["OnHandQuantity_production"].round(2))
        | (merged["ReservedQuantity_adjusted"].round(2) != merged["ReservedQuantity_production"].round(2))
        | (merged["AvailableQuantity_adjusted"].round(2) != merged["AvailableQuantity_production"].round(2))
    ).any()
    assert result.module_results["sales"].sql_load_status == "passed"


def _full_chain_spec(
    tmp_path: Path,
    module_ids: tuple[str, ...] = ("procurement", "production", "sales"),
    load_sql: bool = False,
) -> PipelineRunSpec:
    return PipelineRunSpec(
        module_ids=module_ids,
        metadata_path=str(PROC_METADATA),
        erd_path=str(PROC_ERD),
        scenario_path=str(PROC_SCENARIO),
        plan_path=str(PROC_PLAN),
        output_folder=str(tmp_path),
        seed=42,
        load_sql=load_sql,
        build_prompt=False,
        model_version="v2",
        generation_config=GenerationConfig(
            seed=42,
            profile_id="food_manufacturing",
            max_production_orders=200,
            max_production_requirements=1200,
        ),
        module_inputs={
            "procurement": ModulePipelineInput(
                metadata_path=str(PROC_METADATA),
                erd_path=str(PROC_ERD),
                scenario_path=str(PROC_SCENARIO),
                plan_path=str(PROC_PLAN),
                model_version="v2",
            ),
            "production": ModulePipelineInput(
                metadata_path=str(PROD_METADATA),
                erd_path=str(PROD_ERD),
                scenario_path=str(PROD_SCENARIO),
                plan_path=str(PROD_PLAN),
                model_version="production_v1",
            ),
            "sales": ModulePipelineInput(
                metadata_path=str(SALES_METADATA),
                erd_path=str(SALES_ERD),
                scenario_path=None,
                plan_path=None,
                model_version="v1",
            ),
        },
    )


def _expected_finished_goods_inventory(
    original_inventory: pd.DataFrame,
    receipts: pd.DataFrame,
    shipment_lines: pd.DataFrame,
    reservations: pd.DataFrame,
    return_lines: pd.DataFrame,
) -> pd.DataFrame:
    receipt_rollup = receipts.groupby(["ProductID", "PlantID", "WarehouseID"], as_index=False)["GoodQuantity"].sum()
    base = original_inventory[["FinishedGoodsInventoryID", "ProductID", "PlantID", "WarehouseID"]].merge(
        receipt_rollup,
        on=["ProductID", "PlantID", "WarehouseID"],
        how="left",
    ).fillna({"GoodQuantity": 0.0})
    shipped = shipment_lines.groupby("FinishedGoodsInventoryID")["ShippedQuantity"].sum()
    if return_lines.empty:
        restocked = pd.Series(dtype=float)
    else:
        restocked = (
            return_lines.merge(
                shipment_lines[["ShipmentLineID", "FinishedGoodsInventoryID"]],
                on="ShipmentLineID",
                how="left",
            )
            .groupby("FinishedGoodsInventoryID")["RestockedQuantity"]
            .sum()
        )
    active_reserved = reservations[reservations["ReservationStatus"].astype(str).str.lower() == "reserved"]
    reserved = active_reserved.groupby("FinishedGoodsInventoryID")["ReservedQuantity"].sum()

    base["OnHandQuantity_expected"] = (
        base["GoodQuantity"]
        - base["FinishedGoodsInventoryID"].map(shipped).fillna(0.0)
        + base["FinishedGoodsInventoryID"].map(restocked).fillna(0.0)
    ).round(2)
    base["ReservedQuantity_expected"] = base["FinishedGoodsInventoryID"].map(reserved).fillna(0.0).round(2)
    base["AvailableQuantity_expected"] = (
        base["OnHandQuantity_expected"] - base["ReservedQuantity_expected"]
    ).round(2)
    return base[
        [
            "FinishedGoodsInventoryID",
            "ProductID",
            "PlantID",
            "WarehouseID",
            "OnHandQuantity_expected",
            "ReservedQuantity_expected",
            "AvailableQuantity_expected",
        ]
    ]
