from __future__ import annotations

from pathlib import Path

import pandas as pd

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.transaction_generator import (
    PRODUCTION_MASTER_TABLES,
    PRODUCTION_TRANSACTION_TABLES,
    ProductionTransactionGenerator,
)
from procurement_data_generator.modules.shared.quantity_precision import is_whole_quantity, requires_integer_quantity
from procurement_data_generator.modules.shared.operating_scope import (
    get_default_shift_code,
    get_expected_plant_count,
    get_expected_warehouse_count,
)
from procurement_data_generator.modules.shared.industry_profiles import get_default_industry_profile


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "production_v1_metadata.xlsx"
PLAN = ROOT / "input" / "sample_generation_plan_production_v1_valid.json"


def test_transaction_generation_produces_14_execution_tables(tmp_path: Path) -> None:
    dataframes, report, _master, _upstream = _generate(tmp_path, seed=42)

    assert report.is_valid
    assert set(dataframes) == set(PRODUCTION_TRANSACTION_TABLES)
    assert len(dataframes) == 14
    assert not set(PRODUCTION_MASTER_TABLES).intersection(dataframes)


def test_order_requirement_and_material_issue_lineage(tmp_path: Path) -> None:
    dataframes, _report, master, upstream = _generate(tmp_path, seed=42)
    orders = dataframes["ProductionOrderHdr"]
    lines = dataframes["ProductionOrderLine"]
    requirements = dataframes["ProductionMaterialRequirement"]
    issue_headers = dataframes["MaterialIssueHeader"]
    issue_lines = dataframes["MaterialIssueLine"]

    assert set(orders["PlantID"]).issubset(set(upstream["Plant"]["PlantID"]))
    assert orders["PlantID"].nunique() == get_expected_plant_count()
    assert set(lines["ProductionOrderID"]).issubset(set(orders["ProductionOrderID"]))
    assert set(lines["ProductID"]).issubset(set(master["ProductMaster"]["ProductID"]))
    assert set(lines["BOMID"]).issubset(set(master["BOMHeader"]["BOMID"]))
    assert set(lines["RoutingID"]).issubset(set(master["RoutingHeader"]["RoutingID"]))
    assert set(requirements["ProductionOrderLineID"]).issubset(set(lines["ProductionOrderLineID"]))
    assert set(requirements["BOMLineID"]).issubset(set(master["BOMLine"]["BOMLineID"]))
    assert set(issue_headers["ProductionOrderID"]).issubset(set(orders["ProductionOrderID"]))
    assert requirements["PlantID"].nunique() == get_expected_plant_count()
    assert requirements["WarehouseID"].nunique() == get_expected_warehouse_count()
    assert issue_headers["PlantID"].nunique() == get_expected_plant_count()
    assert issue_headers["WarehouseID"].nunique() == get_expected_warehouse_count()
    assert set(issue_lines["MaterialRequirementID"]).issubset(set(requirements["MaterialRequirementID"]))
    assert set(issue_lines["InventoryID"]).issubset(set(upstream["Inventory"]["InventoryID"]))
    assert set(issue_lines["SourceInventoryTransactionID"]).issubset(set(upstream["InventoryTransaction"]["InventoryTransactionID"]))
    assert set(issue_lines["InventoryReceiptDetailID"]).issubset(set(upstream["InventoryReceiptDetail"]["InventoryReceiptDetailID"]))


def test_requirement_and_issue_formulas_and_inventory_caps(tmp_path: Path) -> None:
    dataframes, _report, master, upstream = _generate(tmp_path, seed=42)
    requirements = dataframes["ProductionMaterialRequirement"]
    lines = dataframes["ProductionOrderLine"][["ProductionOrderLineID", "PlannedQuantity"]]
    bom = master["BOMLine"][["BOMLineID", "ComponentQuantity", "ScrapFactorPct", "UOM"]]
    merged = requirements.merge(lines, on="ProductionOrderLineID").merge(bom, on="BOMLineID")

    expected_required = merged["PlannedQuantity"] * merged["ComponentQuantity"]
    assert (abs(merged["RequiredQuantity"] - expected_required) <= 0.011).all()
    expected_scrap_adjusted = expected_required * (1 + merged["ScrapFactorPct"] / 100)
    for row, expected in zip(merged.itertuples(index=False), expected_scrap_adjusted):
        tolerance = 0.011 if not requires_integer_quantity(row.UOM) else 0.0001
        assert abs(row.ScrapAdjustedQuantity - round(expected if not requires_integer_quantity(row.UOM) else row.ScrapAdjustedQuantity, 2)) <= max(tolerance, 0.011)

    issue_lines = dataframes["MaterialIssueLine"]
    assert (abs(issue_lines["IssueValue"] - issue_lines["IssuedQuantity"] * issue_lines["UnitCost"]) <= 0.011).all()
    issued = issue_lines.groupby("InventoryID")["IssuedQuantity"].sum()
    available = upstream["Inventory"].set_index("InventoryID")["AvailableQuantity"]
    assert all(issued_quantity <= available[inventory_id] + 0.0001 for inventory_id, issued_quantity in issued.items())


def test_batches_operations_quality_and_scrap_are_consistent(tmp_path: Path) -> None:
    dataframes, _report, master, _upstream = _generate(tmp_path, seed=42)
    batches = dataframes["ProductionBatch"]
    operations = dataframes["OperationExecution"]
    inspections = dataframes["ProductionQualityInspection"]
    quality = dataframes["ProductionQualityResult"]
    scrap = dataframes["ScrapReworkEvent"]

    assert set(batches["ProductionOrderLineID"]).issubset(set(dataframes["ProductionOrderLine"]["ProductionOrderLineID"]))
    assert set(operations["ProductionBatchID"]).issubset(set(batches["ProductionBatchID"]))
    assert set(operations["RoutingOperationID"]).issubset(set(master["RoutingOperation"]["RoutingOperationID"]))
    shift_lookup = master["ProductionShift"].set_index("ShiftID")
    operations_with_shift = operations.join(shift_lookup[["ShiftCode", "WorkCenterID"]].rename(columns={"WorkCenterID": "ShiftWorkCenterID"}), on="ShiftID")
    assert set(operations_with_shift["ShiftCode"]) == {get_default_shift_code()}
    assert (operations_with_shift["WorkCenterID"] == operations_with_shift["ShiftWorkCenterID"]).all()
    for _batch_id, rows in operations.groupby("ProductionBatchID"):
        sorted_rows = rows.sort_values("OperationSequence")
        assert list(sorted_rows["OperationSequence"]) == sorted(list(sorted_rows["OperationSequence"]))
        assert (abs(sorted_rows["OutputQuantity"] - (sorted_rows["InputQuantity"] - sorted_rows["ScrapQuantity"])) <= 0.0001).all()
        assert (sorted_rows["ReworkQuantity"] <= sorted_rows["OutputQuantity"] + 0.0001).all()
    assert set(inspections["ProductionBatchID"]).issubset(set(batches["ProductionBatchID"]))
    assert set(inspections["OperationExecutionID"]).issubset(set(operations["OperationExecutionID"]))
    assert set(quality["ProductionInspectionID"]).issubset(set(inspections["ProductionInspectionID"]))
    assert (abs(quality["TestedQuantity"] - (quality["PassedQuantity"] + quality["FailedQuantity"])) <= 0.0001).all()
    assert quality["DefectCode"].notna().all()
    assert (quality["DefectCode"].astype(str).str.strip() != "").all()
    passed_quality = quality[quality["FailedQuantity"] == 0]
    failed_quality = quality[quality["FailedQuantity"] > 0]
    assert set(passed_quality["DefectCode"]) == {"NoDefect"}
    assert set(passed_quality["DefectSeverity"]) == {"None"}
    assert set(passed_quality["ResultStatus"]) == {"Passed"}
    if not failed_quality.empty:
        assert set(failed_quality["DefectCode"]).issubset(set(get_default_industry_profile().production.quality_defect_codes))
        assert not failed_quality["DefectCode"].isin(["NoDefect", "None"]).any()
        assert not failed_quality["DefectSeverity"].isin(["None"]).any()
        assert set(failed_quality["ResultStatus"]).issubset({"PartiallyFailed", "Failed"})
    assert not scrap.empty
    assert set(scrap["OperationExecutionID"]).issubset(set(operations["OperationExecutionID"]))


def test_finished_goods_inventory_genealogy_and_costs_are_consistent(tmp_path: Path) -> None:
    dataframes, _report, _master, upstream = _generate(tmp_path, seed=42)
    receipts = dataframes["FinishedGoodsReceipt"]
    inventory = dataframes["FinishedGoodsInventory"]
    genealogy = dataframes["ProductionGenealogy"]
    cost = dataframes["ProductionCostSummary"]
    issue_lines = dataframes["MaterialIssueLine"]

    assert set(receipts["ProductionBatchID"]).issubset(set(dataframes["ProductionBatch"]["ProductionBatchID"]))
    assert set(receipts["ProductionOrderLineID"]).issubset(set(dataframes["ProductionOrderLine"]["ProductionOrderLineID"]))
    assert receipts["PlantID"].nunique() == get_expected_plant_count()
    assert receipts["WarehouseID"].nunique() == get_expected_warehouse_count()
    assert inventory["PlantID"].nunique() == get_expected_plant_count()
    assert inventory["WarehouseID"].nunique() == get_expected_warehouse_count()
    assert (abs(receipts["ReceiptValue"] - receipts["GoodQuantity"] * receipts["UnitCost"]) <= 0.011).all()
    rolled = receipts.groupby(["ProductID", "PlantID", "WarehouseID"]).agg(
        OnHandQuantity=("GoodQuantity", "sum"),
        OnHandValue=("ReceiptValue", "sum"),
    )
    inv_indexed = inventory.set_index(["ProductID", "PlantID", "WarehouseID"])
    for key, row in rolled.iterrows():
        assert abs(inv_indexed.loc[key, "OnHandQuantity"] - row.OnHandQuantity) <= 0.0001
        assert abs(inv_indexed.loc[key, "OnHandValue"] - row.OnHandValue) <= 0.011
    assert set(genealogy["MaterialIssueLineID"]).issubset(set(issue_lines["MaterialIssueLineID"]))
    assert set(genealogy["InventoryReceiptDetailID"]).issubset(set(upstream["InventoryReceiptDetail"]["InventoryReceiptDetailID"]))
    receipt_supplier = dict(zip(upstream["InventoryReceiptDetail"]["InventoryReceiptDetailID"], upstream["InventoryReceiptDetail"]["SupplierID"]))
    assert all(row.SupplierID == receipt_supplier[row.InventoryReceiptDetailID] for row in genealogy.itertuples(index=False))
    assert (abs(cost["TotalProductionCost"] - (cost["MaterialCost"] + cost["LaborCost"] + cost["OverheadCost"] + cost["ScrapCost"])) <= 0.011).all()


def test_dates_uom_precision_determinism_and_export(tmp_path: Path) -> None:
    first, _first_report, master, upstream = _generate(tmp_path, seed=42)
    second, _second_report, _master, _upstream = _generate(tmp_path, seed=42)
    third, _third_report, _master, _upstream = _generate(tmp_path, seed=43)

    for table_name in PRODUCTION_TRANSACTION_TABLES:
        pd.testing.assert_frame_equal(first[table_name], second[table_name])
    assert not first["ProductionOrderHdr"].equals(third["ProductionOrderHdr"])

    for table_name, dataframe in first.items():
        for column in dataframe.columns:
            if "Date" in column:
                values = pd.to_datetime(dataframe[column], errors="coerce")
                assert values.min() >= pd.Timestamp("2025-01-01")
                assert values.max() <= pd.Timestamp("2025-12-31 23:59:59")

    product_uom = dict(zip(master["ProductMaster"]["ProductID"], master["ProductMaster"]["UOM"]))
    for row in first["ProductionOrderLine"].itertuples(index=False):
        if requires_integer_quantity(product_uom[row.ProductID]):
            assert is_whole_quantity(row.PlannedQuantity)
            assert is_whole_quantity(row.GoodQuantity)
    component_uom = dict(zip(upstream["ComponentMaster"]["ComponentID"], upstream["ComponentMaster"]["UOM"]))
    for row in first["MaterialIssueLine"].itertuples(index=False):
        if requires_integer_quantity(component_uom[row.ComponentID]):
            assert is_whole_quantity(row.IssuedQuantity)

    output = tmp_path / "transactions"
    paths = ProductionTransactionGenerator().export_transaction_data(first, output)
    assert {path.name for path in paths} == {f"{table}.csv" for table in PRODUCTION_TRANSACTION_TABLES}


def test_phase1_production_order_and_requirement_caps_are_config_driven(tmp_path: Path) -> None:
    dataframes, report, _master, _upstream = _generate(
        tmp_path,
        seed=42,
        generation_config=GenerationConfig(
            seed=42,
            max_production_orders=3,
            max_production_requirements=10,
        ),
    )

    assert report.is_valid
    assert len(dataframes["ProductionOrderHdr"]) <= 3
    assert len(dataframes["ProductionOrderLine"]) <= 3
    assert len(dataframes["ProductionMaterialRequirement"]) <= 10


def _generate(tmp_path: Path, seed: int, generation_config: GenerationConfig | None = None):
    schema_result = load_metadata_schema(METADATA)
    assert schema_result.report.is_valid
    assert schema_result.schema is not None
    plan_result = load_llm_plan_json(PLAN)
    assert plan_result.report.is_valid
    assert plan_result.plan is not None
    upstream_master = _master_upstream_fixture(tmp_path)
    master_generator = ProductionMasterDataGenerator()
    master_data, master_report = master_generator.generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=42,
        upstream_data_folder=upstream_master,
    )
    assert master_report.is_valid
    upstream = _execution_upstream_fixture(tmp_path, master_data)
    generator = ProductionTransactionGenerator(generation_config=generation_config)
    dataframes, report = generator.generate_transaction_data(
        schema_result.schema,
        plan_result.plan,
        master_data,
        {table: pd.read_csv(upstream / f"{table}.csv") for table in _UPSTREAM_TABLES},
        seed=seed,
    )
    return dataframes, report, master_data, {table: pd.read_csv(upstream / f"{table}.csv") for table in _UPSTREAM_TABLES}


_UPSTREAM_TABLES = [
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "Inventory",
    "InventoryTransaction",
    "InventoryReceiptDetail",
    "SupplierMaster",
]


def _master_upstream_fixture(tmp_path: Path) -> Path:
    folder = tmp_path / "master_upstream"
    folder.mkdir(exist_ok=True)
    components = [
        {"ComponentID": 100 + index, "ComponentName": f"Component {index}", "UOM": uom}
        for index, uom in enumerate(["EA", "Set", "KG", "Meter", "Liter", "EA", "Roll", "Unit"], start=1)
    ]
    pd.DataFrame(components).to_csv(folder / "ComponentMaster.csv", index=False)
    pd.DataFrame([{"PlantID": 1, "PlantName": "Detroit EV Assembly"}]).to_csv(folder / "Plant.csv", index=False)
    pd.DataFrame([{"WarehouseID": 1, "PlantID": 1, "WarehouseName": "Detroit RM"}]).to_csv(folder / "Warehouse.csv", index=False)
    return folder


def _execution_upstream_fixture(tmp_path: Path, master_data: dict[str, pd.DataFrame]) -> Path:
    folder = tmp_path / "execution_upstream"
    folder.mkdir(exist_ok=True)
    components = pd.read_csv(_master_upstream_fixture(tmp_path) / "ComponentMaster.csv")
    plants = pd.DataFrame([{"PlantID": 1, "PlantName": "Detroit EV Assembly"}])
    warehouses = pd.DataFrame([{"WarehouseID": 1, "PlantID": 1, "WarehouseName": "Detroit RM"}])
    inventory_rows = []
    txn_rows = []
    receipt_rows = []
    row_id = 1
    for component in components.itertuples(index=False):
        for plant_id, warehouse_id in [(1, 1)]:
            inventory_rows.append(
                {
                    "InventoryID": row_id,
                    "ComponentID": component.ComponentID,
                    "PlantID": plant_id,
                    "WarehouseID": warehouse_id,
                    "OnHandQuantity": 50000.0,
                    "ReservedQuantity": 0.0,
                    "AvailableQuantity": 50000.0,
                    "OnHandValue": 500000.0,
                }
            )
            txn_rows.append(
                {
                    "InventoryTransactionID": row_id,
                    "InspectionResultID": row_id,
                    "GoodsReceiptLineID": row_id,
                    "PurchaseOrderLineID": row_id,
                    "SupplierID": 1,
                    "ComponentID": component.ComponentID,
                    "PlantID": plant_id,
                    "WarehouseID": warehouse_id,
                    "TransactionDate": "2025-01-01",
                    "TransactionType": "StockIn",
                    "TransactionQuantity": 50000.0,
                    "UnitPrice": 12.5,
                    "InventoryValue": 625000.0,
                    "ReferenceDocument": f"IRD-{row_id:06d}",
                    "InventoryStatus": "Posted",
                }
            )
            receipt_rows.append(
                {
                    "InventoryReceiptDetailID": row_id,
                    "InspectionResultID": row_id,
                    "GoodsReceiptLineID": row_id,
                    "PurchaseOrderLineID": row_id,
                    "PurchaseOrderID": row_id,
                    "SupplierID": 1,
                    "ComponentID": component.ComponentID,
                    "PlantID": plant_id,
                    "WarehouseID": warehouse_id,
                    "AcceptedQuantity": 50000.0,
                    "DeliveredUnitPrice": 12.5,
                }
            )
            row_id += 1
    components.to_csv(folder / "ComponentMaster.csv", index=False)
    plants.to_csv(folder / "Plant.csv", index=False)
    warehouses.to_csv(folder / "Warehouse.csv", index=False)
    pd.DataFrame(inventory_rows).to_csv(folder / "Inventory.csv", index=False)
    pd.DataFrame(txn_rows).to_csv(folder / "InventoryTransaction.csv", index=False)
    pd.DataFrame(receipt_rows).to_csv(folder / "InventoryReceiptDetail.csv", index=False)
    pd.DataFrame([{"SupplierID": 1, "SupplierName": "Trace Supplier"}]).to_csv(folder / "SupplierMaster.csv", index=False)
    return folder
