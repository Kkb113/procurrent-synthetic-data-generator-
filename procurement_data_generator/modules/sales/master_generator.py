"""Sales master data generator skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SalesMasterDataGenerator:
    """Placeholder for future Sales master/reference data generation."""

    operating_scope: Any | None = None
    generation_config: Any | None = None
    industry_profile: Any | None = None

    def generate_master_data(self, *args: Any, **kwargs: Any):
        """Sales master generation is intentionally deferred."""

        raise NotImplementedError("Sales master data generation is not implemented yet.")

