from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.production.master_generator import (
    PRODUCTION_MASTER_TABLES,
    ProductionMasterDataGenerator,
)
from procurement_data_generator.modules.shared.industry_profiles import get_default_industry_profile
from procurement_data_generator.modules.shared.quantity_precision import is_whole_quantity, requires_integer_quantity
from procurement_data_generator.modules.shared.operating_scope import (
    get_allowed_shift_codes,
    get_default_shift_code,
    get_expected_plant_count,
)


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"
TRANSACTION_TABLES = {
    "ProductionOrderHdr",
    "ProductionOrderLine",
    "ProductionMaterialRequirement",
    "MaterialIssueHeader",
    "MaterialIssueLine",
    "ProductionBatch",
    "OperationExecution",
    "ProductionQualityInspection",
    "ProductionQualityResult",
    "ScrapReworkEvent",
    "FinishedGoodsReceipt",
    "FinishedGoodsInventory",
    "ProductionGenealogy",
    "ProductionCostSummary",
}


def test_production_master_generator_imports_and_generates_seven_tables(tmp_path: Path) -> None:
    dataframes, report, _context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))

    assert report.is_valid
    assert set(dataframes) == set(PRODUCTION_MASTER_TABLES)
    assert len(dataframes) == 7
    assert not TRANSACTION_TABLES.intersection(dataframes)


def test_product_master_unique_ids_and_codes(tmp_path: Path) -> None:
    dataframes, _report, _context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))
    products = dataframes["ProductMaster"]
    profile_product_names = {str(product["name"]) for product in get_default_industry_profile().production.product_catalog}

    assert products["ProductID"].is_unique
    assert products["ProductCode"].is_unique
    assert set(products["ProductType"]).issubset({"FinishedGood", "SemiFinished"})
    assert set(products["UOM"]).issubset({"EA", "Unit", "Set"})
    assert set(products["ProductName"]).intersection(profile_product_names)


def test_bom_header_and_line_reference_products_plants_and_components(tmp_path: Path) -> None:
    dataframes, _report, context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))
    bom_header = dataframes["BOMHeader"]
    bom_line = dataframes["BOMLine"]

    assert set(bom_header["ProductID"]).issubset(set(dataframes["ProductMaster"]["ProductID"]))
    assert set(bom_header["PlantID"]).issubset(set(context.plants["PlantID"]))
    assert bom_header["PlantID"].nunique() == get_expected_plant_count()
    assert set(bom_line["BOMID"]).issubset(set(bom_header["BOMID"]))
    assert set(bom_line["ComponentID"]).issubset(set(context.components["ComponentID"]))


def test_bom_line_uom_matches_component_master_and_precision_rules(tmp_path: Path) -> None:
    dataframes, _report, context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))
    component_uom = dict(zip(context.components["ComponentID"], context.components["UOM"]))
    decimal_quantity_seen = False

    for row in dataframes["BOMLine"].itertuples(index=False):
        expected_uom = component_uom[row.ComponentID]
        assert row.UOM == expected_uom
        if requires_integer_quantity(expected_uom):
            assert is_whole_quantity(row.ComponentQuantity)
        elif not is_whole_quantity(row.ComponentQuantity):
            decimal_quantity_seen = True

    assert decimal_quantity_seen


def test_work_centers_routings_operations_and_shifts_are_consistent(tmp_path: Path) -> None:
    dataframes, _report, context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))
    work_centers = dataframes["WorkCenter"]
    routing_header = dataframes["RoutingHeader"]
    routing_operation = dataframes["RoutingOperation"]
    shifts = dataframes["ProductionShift"]
    profile_work_centers = {str(work_center["name"]) for work_center in get_default_industry_profile().production.work_center_catalog}
    profile_operations = set(get_default_industry_profile().production.routing_operation_names)

    assert set(work_centers["PlantID"]).issubset(set(context.plants["PlantID"]))
    assert all(
        any(str(work_center_name).startswith(profile_name) for profile_name in profile_work_centers)
        for work_center_name in work_centers["WorkCenterName"]
    )
    assert work_centers["PlantID"].nunique() == get_expected_plant_count()
    assert len(work_centers) > get_expected_plant_count()
    assert set(routing_header["ProductID"]).issubset(set(dataframes["ProductMaster"]["ProductID"]))
    assert set(routing_header["PlantID"]).issubset(set(context.plants["PlantID"]))
    assert routing_header["PlantID"].nunique() == get_expected_plant_count()
    assert set(routing_operation["RoutingID"]).issubset(set(routing_header["RoutingID"]))
    assert set(routing_operation["WorkCenterID"]).issubset(set(work_centers["WorkCenterID"]))
    assert set(routing_operation["OperationName"]).issubset(profile_operations)
    for _routing_id, rows in routing_operation.groupby("RoutingID"):
        sequences = list(rows.sort_values("OperationSequence")["OperationSequence"])
        assert sequences == sorted(sequences)
        assert len(sequences) == len(set(sequences))
    work_center_plants = dict(zip(work_centers["WorkCenterID"], work_centers["PlantID"]))
    assert set(shifts["WorkCenterID"]).issubset(set(work_centers["WorkCenterID"]))
    assert all(row.PlantID == work_center_plants[row.WorkCenterID] for row in shifts.itertuples(index=False))
    assert shifts["PlantID"].nunique() == get_expected_plant_count()
    assert set(shifts["ShiftCode"]) == {get_default_shift_code()}
    assert set(shifts["ShiftCode"]).issubset(set(get_allowed_shift_codes()))


def test_all_production_master_dates_are_in_2025(tmp_path: Path) -> None:
    dataframes, _report, _context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))
    date_columns = {
        "BOMHeader": ["EffectiveFromDate", "EffectiveToDate"],
        "ProductionShift": ["ShiftDate"],
    }

    for table_name, columns in date_columns.items():
        for column in columns:
            values = pd.to_datetime(dataframes[table_name][column])
            assert values.min() >= pd.Timestamp("2025-01-01")
            assert values.max() <= pd.Timestamp("2025-12-31")
    assert (
        pd.to_datetime(dataframes["BOMHeader"]["EffectiveFromDate"])
        <= pd.to_datetime(dataframes["BOMHeader"]["EffectiveToDate"])
    ).all()


def test_generation_is_deterministic_for_same_seed_and_changes_for_different_seed(tmp_path: Path) -> None:
    upstream = _upstream_fixture_folder(tmp_path)
    first, _first_report, _context = _generate(seed=42, upstream_data_folder=upstream)
    second, _second_report, _context = _generate(seed=42, upstream_data_folder=upstream)
    third, _third_report, _context = _generate(seed=43, upstream_data_folder=upstream)

    for table_name in PRODUCTION_MASTER_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])
    assert not first["ProductMaster"].equals(third["ProductMaster"])


def test_export_writes_only_master_setup_csv_files(tmp_path: Path) -> None:
    dataframes, report, _context = _generate(seed=42, upstream_data_folder=_upstream_fixture_folder(tmp_path))
    assert report.is_valid

    paths = ProductionMasterDataGenerator().export_master_data(dataframes, tmp_path)

    assert {path.name for path in paths} == {f"{table}.csv" for table in PRODUCTION_MASTER_TABLES}
    assert {path.stem for path in tmp_path.glob("*.csv")} == set(PRODUCTION_MASTER_TABLES)


def test_generator_uses_deterministic_fallback_when_upstream_is_absent() -> None:
    dataframes, report, context = _generate(seed=42, upstream_data_folder=None)

    assert report.is_valid
    assert context.used_fallback
    assert any("No upstream Procurement context" in warning.message for warning in report.warnings)
    assert set(dataframes["BOMLine"]["ComponentID"]).issubset(set(context.components["ComponentID"]))


def _generate(seed: int, upstream_data_folder: Path | None):
    schema_result = load_metadata_schema(METADATA)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None
    plan_result = load_llm_plan_json(PLAN)
    assert plan_result.report.is_valid
    assert plan_result.plan is not None
    generator = ProductionMasterDataGenerator()
    dataframes, report = generator.generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=seed,
        upstream_data_folder=upstream_data_folder,
    )
    context = generator.load_upstream_context(upstream_data_folder)
    return dataframes, report, context


def _upstream_fixture_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "production_upstream"
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"ComponentID": 101, "ComponentName": "Battery Cell Module", "UOM": "EA"},
            {"ComponentID": 102, "ComponentName": "Copper Busbar", "UOM": "EA"},
            {"ComponentID": 103, "ComponentName": "Thermal Paste", "UOM": "KG"},
            {"ComponentID": 104, "ComponentName": "Cooling Tube", "UOM": "Meter"},
            {"ComponentID": 105, "ComponentName": "Insulation Roll", "UOM": "Roll"},
        ]
    ).to_csv(folder / "ComponentMaster.csv", index=False)
    pd.DataFrame(
        [
            {"PlantID": 11, "PlantName": "Detroit EV Assembly"},
        ]
    ).to_csv(folder / "Plant.csv", index=False)
    pd.DataFrame(
        [
            {"WarehouseID": 21, "PlantID": 11, "WarehouseName": "Detroit Raw Material Warehouse"},
        ]
    ).to_csv(folder / "Warehouse.csv", index=False)
    return folder
