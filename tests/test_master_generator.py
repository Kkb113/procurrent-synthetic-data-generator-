from __future__ import annotations

from pathlib import Path

import pytest
import pandas.testing as pdt

from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.shared.operating_scope import get_expected_plant_count, get_expected_warehouse_count


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "input" / "procurement_v2_metadata.xlsx"
PLAN = ROOT / "input" / "sample_generation_plan_v2_valid.json"
EXPECTED_MASTER_TABLES = {"SupplierMaster", "SupplierComponent", "ComponentMaster", "Plant", "Warehouse"}


def test_procurement_master_generation_uses_active_v2_model() -> None:
    data = _generate(seed=42)

    assert set(data) == EXPECTED_MASTER_TABLES
    assert len(data["Plant"]) == get_expected_plant_count()
    assert len(data["Warehouse"]) == get_expected_warehouse_count()
    assert data["SupplierMaster"]["SupplierID"].is_unique
    assert data["ComponentMaster"]["ComponentID"].is_unique
    assert set(data["Warehouse"]["PlantID"]) == set(data["Plant"]["PlantID"])


def test_procurement_v2_supplier_component_links_master_tables() -> None:
    data = _generate(seed=42)

    assert set(data["SupplierComponent"]["SupplierID"]).issubset(set(data["SupplierMaster"]["SupplierID"]))
    assert set(data["SupplierComponent"]["ComponentID"]).issubset(set(data["ComponentMaster"]["ComponentID"]))
    assert not data["SupplierComponent"].duplicated(["SupplierID", "ComponentID"]).any()


def test_procurement_v2_master_generation_is_deterministic_for_same_seed() -> None:
    first = _generate(seed=42)
    second = _generate(seed=42)

    for table_name in EXPECTED_MASTER_TABLES:
        pdt.assert_frame_equal(first[table_name], second[table_name])


def test_procurement_v1_master_generation_is_no_longer_supported() -> None:
    schema_result = load_metadata_schema(METADATA)
    plan_result = load_llm_plan_json(PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None

    with pytest.raises(ValueError, match="Procurement V1 is deprecated and no longer supported"):
        ProcurementMasterDataGenerator().generate_master_data(
            schema_result.schema,
            plan_result.plan,
            seed=42,
            model_version="v1",
        )


def _generate(seed: int):
    schema_result = load_metadata_schema(METADATA)
    plan_result = load_llm_plan_json(PLAN)
    assert schema_result.schema is not None
    assert plan_result.plan is not None

    dataframes, report = ProcurementMasterDataGenerator().generate_master_data(
        schema_result.schema,
        plan_result.plan,
        seed=seed,
        model_version="v2",
    )
    assert report.is_valid, [issue.message for issue in report.errors]
    return dataframes
