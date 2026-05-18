"""Sales / Order-to-Cash module skeleton.

Sales is registered as a future MES module boundary in Sales Phase 1. Data
generation and execution are intentionally deferred to later Sales phases.
"""

from procurement_data_generator.modules.sales.plugin import SalesModulePlugin
from procurement_data_generator.modules.sales.metadata import build_sales_v1_metadata_dataframe, write_sales_v1_metadata_xlsx
from procurement_data_generator.modules.sales.role_catalog import SALES_V1_EXPECTED_TABLES, get_sales_role_catalog

__all__ = [
    "SALES_V1_EXPECTED_TABLES",
    "SalesModulePlugin",
    "build_sales_v1_metadata_dataframe",
    "get_sales_role_catalog",
    "write_sales_v1_metadata_xlsx",
]
