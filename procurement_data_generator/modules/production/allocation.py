"""Production raw-material allocation pools and lookup maps."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

from procurement_data_generator.modules.shared.quantity_precision import (
    apply_quantity_precision,
    requires_integer_quantity,
)


@dataclass
class InventoryLot:
    """Mutable allocation lot for Production raw-material consumption."""

    inventory_id: int
    component_id: int
    plant_id: int
    warehouse_id: int
    available_quantity: float


@dataclass
class InventoryTransactionLot:
    """Mutable inventory transaction lot aligned to an inventory bucket."""

    transaction_id: int
    component_id: int
    plant_id: int
    warehouse_id: int
    remaining_quantity: float
    unit_price: float
    inventory_receipt_detail_id: int
    receipt_row: Any


@dataclass(frozen=True)
class ProductionAllocationContext:
    """Precomputed allocation maps used by Production transaction generation."""

    products: tuple[Any, ...]
    bom_by_product: dict[int, tuple[Any, ...]]
    routing_by_product: dict[int, tuple[Any, ...]]
    bom_lines_by_bom: dict[int, tuple[Any, ...]]
    inventory_lots_by_component: dict[int, list[InventoryLot]]
    txn_lots_by_inventory_key: dict[tuple[int, int, int], list[InventoryTransactionLot]]
    component_uom: dict[int, str]


def allocate_bom(
    bom_lines: tuple[Any, ...],
    planned_quantity: float,
    allocation_context: ProductionAllocationContext,
    rng: random.Random,
) -> list[tuple[Any, float, float, InventoryLot, InventoryTransactionLot, Any]] | None:
    """Allocate all BOM components, rolling back if any component is short."""

    allocations = []
    for bom_line in bom_lines:
        uom = str(bom_line.UOM)
        required_quantity = float(bom_line.ComponentQuantity) * planned_quantity
        scrap_adjusted = required_quantity * (1 + float(bom_line.ScrapFactorPct) / 100)
        scrap_adjusted = apply_quantity_precision(
            scrap_adjusted,
            uom,
            minimum=1 if requires_integer_quantity(uom) else 0.01,
        )
        required_quantity = apply_quantity_precision(
            required_quantity,
            uom,
            minimum=1 if requires_integer_quantity(uom) else 0.01,
        )
        allocation = allocate_component(
            component_id=int(bom_line.ComponentID),
            quantity=scrap_adjusted,
            allocation_context=allocation_context,
            rng=rng,
        )
        if allocation is None:
            for _, _, consumed_quantity, inventory_lot, txn_lot, _ in reversed(allocations):
                inventory_lot.available_quantity += consumed_quantity
                txn_lot.remaining_quantity += consumed_quantity
            return None
        inventory_lot, txn_lot, receipt_row = allocation
        allocations.append((bom_line, required_quantity, scrap_adjusted, inventory_lot, txn_lot, receipt_row))
    return allocations


def allocate_component(
    component_id: int,
    quantity: float,
    allocation_context: ProductionAllocationContext,
    rng: random.Random,
) -> tuple[InventoryLot, InventoryTransactionLot, Any] | None:
    """Consume a component quantity from one matching inventory and transaction lot."""

    inventory_candidates = allocation_context.inventory_lots_by_component.get(component_id)
    if not inventory_candidates:
        return None
    start_index = rng.randrange(len(inventory_candidates))
    for offset in range(len(inventory_candidates)):
        inventory_lot = inventory_candidates[(start_index + offset) % len(inventory_candidates)]
        if inventory_lot.available_quantity + 0.0001 < quantity:
            continue
        txn_candidates = allocation_context.txn_lots_by_inventory_key.get(
            (component_id, inventory_lot.plant_id, inventory_lot.warehouse_id),
            [],
        )
        for txn_lot in txn_candidates:
            if txn_lot.remaining_quantity + 0.0001 < quantity:
                continue
            inventory_lot.available_quantity = round(inventory_lot.available_quantity - quantity, 6)
            txn_lot.remaining_quantity = round(txn_lot.remaining_quantity - quantity, 6)
            return inventory_lot, txn_lot, txn_lot.receipt_row
    return None


def build_allocation_context(master: Any, upstream: Any) -> ProductionAllocationContext:
    """Precompute BOM, routing, inventory, and receipt maps for Production allocation."""

    receipts_by_id = {
        int(row.InventoryReceiptDetailID): row
        for row in upstream.inventory_receipt_detail.itertuples(index=False)
    }
    receipts_by_inspection = {
        int(row.InspectionResultID): row
        for row in upstream.inventory_receipt_detail.itertuples(index=False)
        if hasattr(row, "InspectionResultID")
    }
    inventory_lots_by_component: dict[int, list[InventoryLot]] = {}
    for row in upstream.inventory.sort_values(["ComponentID", "InventoryID"]).itertuples(index=False):
        available_quantity = float(getattr(row, "AvailableQuantity", 0.0) or 0.0)
        if available_quantity <= 0:
            continue
        component_id = int(row.ComponentID)
        inventory_lots_by_component.setdefault(component_id, []).append(
            InventoryLot(
                inventory_id=int(row.InventoryID),
                component_id=component_id,
                plant_id=int(row.PlantID),
                warehouse_id=int(row.WarehouseID),
                available_quantity=available_quantity,
            )
        )

    txn_lots_by_inventory_key: dict[tuple[int, int, int], list[InventoryTransactionLot]] = {}
    sorted_transactions = upstream.inventory_transaction.sort_values(
        ["ComponentID", "PlantID", "WarehouseID", "InventoryTransactionID"]
    )
    for row in sorted_transactions.itertuples(index=False):
        remaining_quantity = float(getattr(row, "TransactionQuantity", 0.0) or 0.0)
        if remaining_quantity <= 0:
            continue
        receipt_id = receipt_id_from_reference(getattr(row, "ReferenceDocument", None))
        receipt_row = receipts_by_id.get(receipt_id) or receipts_by_inspection.get(int(getattr(row, "InspectionResultID", -1)))
        if receipt_row is None:
            continue
        component_id = int(row.ComponentID)
        plant_id = int(row.PlantID)
        warehouse_id = int(row.WarehouseID)
        txn_lots_by_inventory_key.setdefault((component_id, plant_id, warehouse_id), []).append(
            InventoryTransactionLot(
                transaction_id=int(row.InventoryTransactionID),
                component_id=component_id,
                plant_id=plant_id,
                warehouse_id=warehouse_id,
                remaining_quantity=remaining_quantity,
                unit_price=float(getattr(row, "UnitPrice", 0.0) or 0.0),
                inventory_receipt_detail_id=int(receipt_row.InventoryReceiptDetailID),
                receipt_row=receipt_row,
            )
        )

    return ProductionAllocationContext(
        products=tuple(master.product_master.itertuples(index=False)),
        bom_by_product={
            int(product_id): tuple(rows.itertuples(index=False))
            for product_id, rows in master.bom_header.groupby("ProductID", sort=False)
        },
        routing_by_product={
            int(product_id): tuple(rows.itertuples(index=False))
            for product_id, rows in master.routing_header.groupby("ProductID", sort=False)
        },
        bom_lines_by_bom={
            int(bom_id): tuple(rows.itertuples(index=False))
            for bom_id, rows in master.bom_line.groupby("BOMID", sort=False)
        },
        inventory_lots_by_component=inventory_lots_by_component,
        txn_lots_by_inventory_key=txn_lots_by_inventory_key,
        component_uom=component_uom_lookup(upstream.component_master),
    )


def component_uom_lookup(component_master: pd.DataFrame) -> dict[int, str]:
    uom_column = next((column for column in ["UOM", "UnitOfMeasure", "Unit_Of_Measure"] if column in component_master.columns), None)
    if uom_column is None:
        return {int(row.ComponentID): "EA" for row in component_master.itertuples(index=False)}
    return {int(row.ComponentID): str(getattr(row, uom_column)) for row in component_master.itertuples(index=False)}


def receipt_id_from_reference(reference: Any) -> int:
    text = str(reference or "")
    digits = "".join(character for character in text if character.isdigit())
    return int(digits) if digits else -1
