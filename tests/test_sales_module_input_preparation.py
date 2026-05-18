from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.pipeline_service import METADATA_SHEET_NAME, PipelineService
from procurement_data_generator.modules.sales.metadata import build_sales_v1_metadata_dataframe


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_combined_metadata_can_be_filtered_for_sales(tmp_path: Path) -> None:
    combined_metadata = _combined_metadata()
    combined_path = tmp_path / "combined_metadata.xlsx"
    with pd.ExcelWriter(combined_path, engine="openpyxl") as writer:
        combined_metadata.to_excel(writer, sheet_name=METADATA_SHEET_NAME, index=False)

    split_paths = PipelineService()._split_combined_metadata_by_module(
        combined_path,
        tmp_path,
        ("procurement", "production", "sales"),
    )

    assert set(split_paths) == {"procurement", "production", "sales"}
    procurement_tables = _table_names(split_paths["procurement"])
    production_tables = _table_names(split_paths["production"])
    sales_tables = _table_names(split_paths["sales"])
    assert "SalesOrderHdr" not in procurement_tables
    assert "SalesOrderHdr" not in production_tables
    assert "SalesOrderHdr" in sales_tables
    assert "SalesCreditMemo" not in sales_tables
    assert len(sales_tables) == 18


@pytest.mark.unit
def test_combined_erd_can_be_filtered_for_procurement_production_and_sales(tmp_path: Path) -> None:
    combined_metadata = _combined_metadata()
    combined_path = tmp_path / "combined_metadata.xlsx"
    with pd.ExcelWriter(combined_path, engine="openpyxl") as writer:
        combined_metadata.to_excel(writer, sheet_name=METADATA_SHEET_NAME, index=False)
    service = PipelineService()
    metadata_paths = service._split_combined_metadata_by_module(combined_path, tmp_path, ("procurement", "production", "sales"))
    combined_erd_path = tmp_path / "combined_erd.mmd"
    combined_erd_path.write_text(_combined_erd(), encoding="utf-8")

    erd_paths = service._split_combined_erd_by_module(
        combined_erd_path,
        metadata_paths,
        tmp_path,
        ("procurement", "production", "sales"),
    )

    procurement_erd = erd_paths["procurement"].read_text(encoding="utf-8")
    production_erd = erd_paths["production"].read_text(encoding="utf-8")
    sales_erd = erd_paths["sales"].read_text(encoding="utf-8")
    assert "SalesOrderHdr" not in procurement_erd
    assert "SalesOrderHdr" not in production_erd
    assert "SupplierQuotation ||--o{ PurchaseOrderHdr" not in production_erd
    assert "SalesOrderHdr ||--o{ SalesOrderLine" in sales_erd
    assert "FinishedGoodsInventory ||--o{ SalesInventoryReservation" in sales_erd
    assert "ProductionGenealogy ||--o{ SalesShipmentTraceability" in sales_erd
    assert "InventoryReceiptDetail ||--o{ SalesShipmentTraceability" in sales_erd
    assert "SupplierMaster ||--o{ SalesShipmentTraceability" in sales_erd
    assert "SupplierQuotation ||--o{ PurchaseOrderHdr" not in sales_erd


@pytest.mark.unit
def test_generic_module_input_preparation_can_prepare_sales_without_execution(tmp_path: Path) -> None:
    combined_metadata_path = tmp_path / "combined_metadata.xlsx"
    with pd.ExcelWriter(combined_metadata_path, engine="openpyxl") as writer:
        _combined_metadata().to_excel(writer, sheet_name=METADATA_SHEET_NAME, index=False)
    service = PipelineService()
    metadata_paths = service._split_combined_metadata_by_module(combined_metadata_path, tmp_path, ("sales",))

    assert metadata_paths == {}
    # Single-module filtering is intentionally skipped; default Sales metadata remains available for future execution prep.
    assert Path("input/sales_v1_metadata.xlsx").exists()
    assert Path("input/sales_v1_erd.mmd").exists()


def _combined_metadata() -> pd.DataFrame:
    procurement = pd.read_excel(ROOT / "input" / "procurement_v2_metadata.xlsx", sheet_name=METADATA_SHEET_NAME, engine="openpyxl", dtype=object)
    production = pd.read_excel(ROOT / "input" / "production_v1_metadata.xlsx", sheet_name=METADATA_SHEET_NAME, engine="openpyxl", dtype=object)
    sales = build_sales_v1_metadata_dataframe()
    return pd.concat([procurement, production, sales], ignore_index=True)


def _combined_erd() -> str:
    return "\n".join(
        [
            (ROOT / "input" / "procurement_v2_erd.mmd").read_text(encoding="utf-8"),
            (ROOT / "input" / "production_v1_erd.mmd").read_text(encoding="utf-8").replace("erDiagram", "", 1),
            (ROOT / "input" / "sales_v1_erd.mmd").read_text(encoding="utf-8").replace("erDiagram", "", 1),
        ]
    )


def _table_names(path: Path) -> set[str]:
    metadata = pd.read_excel(path, sheet_name=METADATA_SHEET_NAME, engine="openpyxl", dtype=object)
    return set(metadata["TableName"].dropna().astype(str))

