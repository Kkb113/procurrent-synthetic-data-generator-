"""Sales-specific validation rule skeleton."""

from __future__ import annotations


SALES_V1_PLANNED_VALIDATION_RULES = (
    "sales_order_quantity_lifecycle",
    "sales_reservation_not_exceed_finished_goods_available",
    "sales_pick_not_exceed_reserved",
    "sales_ship_not_exceed_picked",
    "sales_invoice_quantity_equals_shipped",
    "sales_payment_not_exceed_invoice_total",
    "sales_return_not_exceed_shipped",
    "sales_traceability_links_complete",
)


def get_sales_validation_rules() -> tuple[str, ...]:
    """Return planned Sales validation rule IDs.

    These are not active validation implementations yet.
    """

    return SALES_V1_PLANNED_VALIDATION_RULES


def validate_sales_generated_data(*args, **kwargs):
    """Sales generated-data validation is intentionally deferred."""

    raise NotImplementedError("Sales validation is not implemented yet. Sales validation starts in a later Sales phase.")


__all__ = ["SALES_V1_PLANNED_VALIDATION_RULES", "get_sales_validation_rules", "validate_sales_generated_data"]

