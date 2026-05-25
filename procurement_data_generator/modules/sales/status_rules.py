"""Pure Sales status and quantity tolerance rules."""

from __future__ import annotations


SALES_QUANTITY_TOLERANCE = 0.011


def quantity_equal(left: float, right: float, tolerance: float = SALES_QUANTITY_TOLERANCE) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def line_status(
    ordered_quantity: float,
    reserved_quantity: float,
    shipped_quantity: float,
    tolerance: float = SALES_QUANTITY_TOLERANCE,
) -> str:
    if quantity_equal(shipped_quantity, ordered_quantity, tolerance):
        return "Closed"
    if shipped_quantity > 0 and reserved_quantity + tolerance < ordered_quantity:
        return "Backordered"
    if shipped_quantity > 0:
        return "PartiallyShipped"
    return "Backordered"


def order_status(line_statuses: tuple[str, ...]) -> str:
    if all(status == "Closed" for status in line_statuses):
        return "Closed"
    if any(status == "Backordered" for status in line_statuses):
        return "Backordered"
    if any(status == "PartiallyShipped" for status in line_statuses):
        return "PartiallyShipped"
    return "Backordered"


def finished_goods_inventory_status(on_hand_quantity: float, reserved_quantity: float, available_quantity: float) -> str:
    if on_hand_quantity <= 0:
        return "OutOfStock"
    if reserved_quantity > 0 and available_quantity <= 0:
        return "Hold"
    if available_quantity > 0 and available_quantity <= on_hand_quantity * 0.1:
        return "LowStock"
    return "Available"


def invoice_status(total_invoice_amount: float, paid_amount: float) -> str:
    if paid_amount >= round(total_invoice_amount, 2):
        return "Paid"
    if paid_amount > 0:
        return "PartiallyPaid"
    return "Open"


def return_line_status(restocked_quantity: float, scrapped_quantity: float) -> str:
    if restocked_quantity > 0 and scrapped_quantity == 0:
        return "Restocked"
    if scrapped_quantity > 0 and restocked_quantity == 0:
        return "Scrapped"
    return "Received"
