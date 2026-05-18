"""Sales transaction data generator skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SalesTransactionGenerator:
    """Placeholder for future Sales Order-to-Cash transaction generation."""

    operating_scope: Any | None = None
    generation_config: Any | None = None
    industry_profile: Any | None = None

    def generate_transaction_data(self, *args: Any, **kwargs: Any):
        """Sales transaction generation is intentionally deferred."""

        raise NotImplementedError("Sales transaction data generation is not implemented yet.")

