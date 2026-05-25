"""Procurement-specific generated data validation rules.

This module preserves the existing Procurement v2 validation behavior while
moving Procurement-owned lifecycle and operating-scope checks out of the core
generic validation layer.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from procurement_data_generator.core.contracts.data_quality_report import DataQualityReport, TableQualitySummary
from procurement_data_generator.core.contracts.llm_plan_contract import LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.modules.procurement.quantity_precision import is_whole_quantity, requires_integer_quantity
from procurement_data_generator.modules.procurement.role_catalog import PROCUREMENT_V1_UNSUPPORTED_MESSAGE
from procurement_data_generator.modules.shared.operating_scope import (
    get_expected_plant_count,
    get_expected_warehouse_count,
)


ARTIFICIAL_NUMERIC_SUFFIX_PATTERN = re.compile(r"\s(?:[1-9]|[1-9][0-9])$")
NUMERIC_TYPE_TOKENS = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "money", "real")
DATE_TYPE_TOKENS = ("date", "datetime", "datetime2", "timestamp")


class ProcurementGeneratedDataValidator:
    """Validate Procurement generated DataFrames with generic and v2 rules."""

    def validate_dataset(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        plan: LLMGenerationPlan | None = None,
        model_version: str = "v2",
    ) -> DataQualityReport:
        if model_version != "v2":
            raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
        report = DataQualityReport()
        target_rows_by_table = self._target_rows_by_table(schema, plan)

        for table in schema.ordered_tables:
            dataframe = dataframes.get(table.table_name)
            if dataframe is None:
                report.record_check(False)
                report.add_issue(
                    level="error",
                    check_type="TABLE_EXISTENCE",
                    table_name=table.table_name,
                    message=f"Required table {table.table_name} is missing from generated data.",
                    suggested_fix="Provide a DataFrame or CSV for every table in metadata before SQL loading.",
                )
                continue

            report.table_summaries[table.table_name] = TableQualitySummary(
                table_name=table.table_name,
                row_count=len(dataframe),
                target_rows=target_rows_by_table.get(table.table_name, table.target_rows),
            )
            self._validate_row_count(table, dataframe, target_rows_by_table.get(table.table_name, table.target_rows), report)
            self._validate_columns(table, dataframe, report)
            self._validate_pk(table, dataframe, report)
            self._validate_required_values(table, dataframe, report)
            self._validate_allowed_values(table, dataframe, report)
            self._validate_numeric_and_date_ranges(table, dataframe, report)
            self._validate_infinity(table, dataframe, report)
            self._validate_non_negative_quantities(table, dataframe, report)
            self._validate_name_quality(table, dataframe, report)

        self._validate_foreign_keys(dataframes, schema, report)
        if self._schema_contains_procurement_v2_tables(schema):
            self._validate_v2_dataset_rules(dataframes, schema, report)
        return report

    def _schema_contains_procurement_v2_tables(self, schema: SchemaContract) -> bool:
        active_v2_table_names = {
            "SupplierMaster",
            "SupplierComponent",
            "ComponentMaster",
            "Plant",
            "Warehouse",
            "PurchaseRequisition",
            "PurchaseReqLine",
            "InventoryReceiptDetail",
            "InventoryTransaction",
        }
        return any(table.table_name in active_v2_table_names for table in schema.ordered_tables)

    def _validate_row_count(self, table: TableContract, dataframe: pd.DataFrame, target_rows: int, report: DataQualityReport) -> None:
        report.record_check(len(dataframe) == target_rows)
        report.table_summaries[table.table_name].checks_run += 1
        if len(dataframe) != target_rows:
            level = "warning"
            message = f"{table.table_name} has {len(dataframe)} rows; target is {target_rows}."
            fix = "Review row generation targets. Derived inventory snapshots may naturally differ because they are grouped outputs."
            report.add_issue(level, "ROW_COUNT", message, fix, table_name=table.table_name)

    def _validate_columns(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        for column in table.columns:
            exists = column.column_name in dataframe.columns
            report.record_check(exists)
            report.table_summaries[table.table_name].checks_run += 1
            if not exists:
                report.add_issue(
                    level="error",
                    check_type="COLUMN_EXISTENCE",
                    table_name=table.table_name,
                    column_name=column.column_name,
                    message=f"Required column {table.table_name}.{column.column_name} is missing.",
                    suggested_fix="Generate every column listed in metadata.",
                )

    def _validate_pk(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        pk_columns = [column for column in table.columns if column.key_type == "PK"]
        for column in pk_columns:
            if column.column_name not in dataframe.columns:
                continue
            series = dataframe[column.column_name]
            non_null = series.notna().all()
            unique = series.is_unique
            report.record_check(non_null)
            report.table_summaries[table.table_name].checks_run += 1
            if not non_null:
                report.add_issue(
                    "error",
                    "PK_NON_NULL",
                    "Primary key contains null values.",
                    "Generate non-null primary key values.",
                    table_name=table.table_name,
                    column_name=column.column_name,
                    sample_failed_rows=self._sample_rows(dataframe[series.isna()]),
                )
            report.record_check(unique)
            report.table_summaries[table.table_name].checks_run += 1
            if not unique:
                duplicates = dataframe[series.duplicated(keep=False)]
                report.add_issue(
                    "error",
                    "PK_UNIQUE",
                    "Primary key contains duplicate values.",
                    "Generate unique primary key values.",
                    table_name=table.table_name,
                    column_name=column.column_name,
                    sample_failed_rows=self._sample_rows(duplicates),
                )

    def _validate_required_values(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        for column in table.columns:
            if column.column_name not in dataframe.columns:
                continue
            if column.nullable != "No":
                continue
            series = dataframe[column.column_name]
            passed = series.notna().all()
            report.record_check(passed)
            report.table_summaries[table.table_name].checks_run += 1
            if not passed:
                report.add_issue(
                    "error",
                    "NOT_NULL",
                    f"Nullable = No column {column.column_name} contains null values.",
                    "Populate all required values.",
                    table_name=table.table_name,
                    column_name=column.column_name,
                    sample_failed_rows=self._sample_rows(dataframe[series.isna()]),
                )

    def _validate_allowed_values(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        for column in table.columns:
            if column.column_name not in dataframe.columns or not column.allowed_values:
                continue
            series = dataframe[column.column_name].dropna()
            allowed = {str(value) for value in column.allowed_values}
            invalid_mask = ~series.astype(str).isin(allowed)
            passed = not invalid_mask.any()
            report.record_check(passed)
            report.table_summaries[table.table_name].checks_run += 1
            if not passed:
                invalid_indexes = invalid_mask[invalid_mask].index
                report.add_issue(
                    "error",
                    "ALLOWED_VALUES",
                    f"{column.column_name} contains values outside AllowedValues.",
                    "Use only the metadata AllowedValues for category/status fields.",
                    table_name=table.table_name,
                    column_name=column.column_name,
                    sample_failed_rows=self._sample_rows(dataframe.loc[invalid_indexes]),
                )

    def _validate_numeric_and_date_ranges(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        for column in table.columns:
            if column.column_name not in dataframe.columns:
                continue
            if column.min_value is None and column.max_value is None:
                continue
            if self._is_numeric_type(column.data_type):
                self._validate_numeric_range(table, column, dataframe, report)
            elif self._is_date_type(column.data_type):
                self._validate_date_range(table, column, dataframe, report)

    def _validate_numeric_range(self, table: TableContract, column: ColumnContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        series = pd.to_numeric(dataframe[column.column_name], errors="coerce")
        mask = pd.Series(False, index=dataframe.index)
        if column.min_value is not None:
            mask = mask | (series < float(column.min_value))
        if column.max_value is not None:
            mask = mask | (series > float(column.max_value))
        passed = not mask.fillna(False).any()
        report.record_check(passed)
        report.table_summaries[table.table_name].checks_run += 1
        if not passed:
            report.add_issue(
                "error",
                "NUMERIC_RANGE",
                f"{column.column_name} contains values outside MinValue/MaxValue.",
                "Generate values within metadata numeric bounds.",
                table_name=table.table_name,
                column_name=column.column_name,
                sample_failed_rows=self._sample_rows(dataframe[mask.fillna(False)]),
            )

    def _validate_date_range(self, table: TableContract, column: ColumnContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        series = pd.to_datetime(dataframe[column.column_name], errors="coerce")
        mask = series.isna() & dataframe[column.column_name].notna()
        if column.min_value is not None:
            mask = mask | (series < pd.to_datetime(column.min_value))
        if column.max_value is not None:
            mask = mask | (series > pd.to_datetime(column.max_value))
        passed = not mask.fillna(False).any()
        report.record_check(passed)
        report.table_summaries[table.table_name].checks_run += 1
        if not passed:
            report.add_issue(
                "error",
                "DATE_RANGE",
                f"{column.column_name} contains invalid dates or dates outside MinValue/MaxValue.",
                "Generate valid dates within metadata date bounds.",
                table_name=table.table_name,
                column_name=column.column_name,
                sample_failed_rows=self._sample_rows(dataframe[mask.fillna(False)]),
            )

    def _validate_infinity(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        numeric = dataframe.apply(pd.to_numeric, errors="coerce")
        infinity_mask = pd.DataFrame(np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)), index=dataframe.index, columns=dataframe.columns)
        passed = not infinity_mask.any().any()
        report.record_check(passed)
        report.table_summaries[table.table_name].checks_run += 1
        if not passed:
            columns = [column for column in dataframe.columns if infinity_mask[column].any()]
            for column_name in columns:
                report.add_issue(
                    "error",
                    "INFINITY",
                    "Positive or negative Infinity found in generated data.",
                    "Use guarded division and replace Infinity with null before validation.",
                    table_name=table.table_name,
                    column_name=column_name,
                    sample_failed_rows=self._sample_rows(dataframe[infinity_mask[column_name]]),
                )

    def _validate_non_negative_quantities(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        for column_name in dataframe.columns:
            if "quantity" not in column_name.lower() and not column_name.lower().endswith("qty"):
                continue
            numeric = pd.to_numeric(dataframe[column_name], errors="coerce")
            mask = numeric < 0
            passed = not mask.fillna(False).any()
            report.record_check(passed)
            report.table_summaries[table.table_name].checks_run += 1
            if not passed:
                report.add_issue(
                    "error",
                    "NON_NEGATIVE_QUANTITY",
                    f"{column_name} contains negative quantity values.",
                    "Generate non-negative procurement quantities.",
                    table_name=table.table_name,
                    column_name=column_name,
                    sample_failed_rows=self._sample_rows(dataframe[mask.fillna(False)]),
                )

    def _validate_name_quality(self, table: TableContract, dataframe: pd.DataFrame, report: DataQualityReport) -> None:
        for column_name in dataframe.columns:
            lowered = column_name.lower()
            if "name" not in lowered:
                continue
            suffix_mask = dataframe[column_name].dropna().astype(str).str.contains(ARTIFICIAL_NUMERIC_SUFFIX_PATTERN)
            passed = not suffix_mask.any()
            report.record_check(passed)
            report.table_summaries[table.table_name].checks_run += 1
            if not passed:
                report.add_issue(
                    "error",
                    "ARTIFICIAL_NAME_SUFFIX",
                    f"{column_name} contains artificial numeric suffixes.",
                    "Use meaningful domain-aware unique names instead of numeric suffixes.",
                    table_name=table.table_name,
                    column_name=column_name,
                    sample_failed_rows=self._sample_rows(dataframe.loc[suffix_mask[suffix_mask].index]),
                )
            if table.area == "Master" and dataframe[column_name].notna().any():
                unique = dataframe[column_name].is_unique
                report.record_check(unique)
                report.table_summaries[table.table_name].checks_run += 1
                if not unique:
                    report.add_issue(
                        "error",
                        "DUPLICATE_MASTER_NAME",
                        f"Master name column {column_name} contains duplicates.",
                        "Generate unique master/reference names.",
                        table_name=table.table_name,
                        column_name=column_name,
                        sample_failed_rows=self._sample_rows(dataframe[dataframe[column_name].duplicated(keep=False)]),
                    )

    def _validate_v2_dataset_rules(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract, report: DataQualityReport) -> None:
        expected_tables = {
            "SupplierMaster",
            "SupplierComponent",
            "ComponentMaster",
            "Plant",
            "Warehouse",
            "PurchaseRequisition",
            "PurchaseReqLine",
            "RFQHeader",
            "RFQLine",
            "SupplierQuotation",
            "SupplierQuotationLn",
            "PurchaseOrderHdr",
            "PurchaseOrderLine",
            "POSchedule",
            "ShipmentHdr",
            "ShipmentLine",
            "GoodsReceiptHeader",
            "GoodsReceiptLine",
            "IncomingInspection",
            "InspectionResult",
            "InventoryReceiptDetail",
            "InventoryTransaction",
            "Inventory",
            "SupplierInvoice",
            "PaymentTransaction",
        }
        report.record_check("InventoryBalance" not in dataframes)
        if "InventoryBalance" in dataframes:
            report.add_issue(
                "error",
                "V2_NO_INVENTORY_BALANCE",
                "InventoryBalance is not part of Procurement v2 final data.",
                "Remove InventoryBalance from v2 outputs.",
                table_name="InventoryBalance",
            )
        for table_name in sorted(expected_tables):
            report.record_check(table_name in dataframes)
            if table_name not in dataframes:
                report.add_issue(
                    "error",
                    "V2_EXPECTED_TABLE",
                    f"Procurement v2 expected table {table_name} is missing.",
                    "Provide all 25 Procurement v2 tables.",
                    table_name=table_name,
                )
        self._validate_v2_constant(dataframes, "SupplierMaster", "SupplierCountry", self._expected_column_value(schema, "SupplierMaster", "SupplierCountry", "USA"), "V2_USA_SUPPLIER_COUNTRY", report)
        self._validate_v2_constant(dataframes, "Plant", "PlantCountry", self._expected_column_value(schema, "Plant", "PlantCountry", "USA"), "V2_USA_PLANT_COUNTRY", report)
        self._validate_v2_constant(dataframes, "Warehouse", "WarehouseCountry", self._expected_column_value(schema, "Warehouse", "WarehouseCountry", "USA"), "V2_USA_WAREHOUSE_COUNTRY", report)
        for table_name in ("ComponentMaster", "SupplierComponent", "SupplierQuotation", "PurchaseOrderHdr", "SupplierInvoice", "PaymentTransaction"):
            self._validate_v2_constant(dataframes, table_name, "CurrencyCode", self._expected_column_value(schema, table_name, "CurrencyCode", "USD"), "V2_USD_CURRENCY", report)
        self._validate_v2_operating_scope(dataframes, report)
        self._validate_v2_warehouse_master_location(dataframes, report)
        self._validate_v2_quantity_precision(dataframes, report)
        self._validate_v2_status_diversity(dataframes, schema, report)

    def _validate_v2_operating_scope(self, dataframes: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        plant = dataframes.get("Plant")
        warehouse = dataframes.get("Warehouse")
        if plant is None or warehouse is None or "PlantID" not in plant.columns or "WarehouseID" not in warehouse.columns:
            return

        expected_plant_count = get_expected_plant_count()
        expected_warehouse_count = get_expected_warehouse_count()
        plant_count_ok = len(plant) == expected_plant_count
        warehouse_count_ok = len(warehouse) == expected_warehouse_count
        report.record_check(plant_count_ok)
        if not plant_count_ok:
            report.add_issue(
                "error",
                "V2_OPERATING_SCOPE_PLANT_COUNT",
                f"Procurement v2 must generate exactly {expected_plant_count} Plant row.",
                "Use the shared operating scope plant count during Procurement v2 generation.",
                table_name="Plant",
                sample_failed_rows=self._sample_rows(plant),
            )
        report.record_check(warehouse_count_ok)
        if not warehouse_count_ok:
            report.add_issue(
                "error",
                "V2_OPERATING_SCOPE_WAREHOUSE_COUNT",
                f"Procurement v2 must generate exactly {expected_warehouse_count} Warehouse row.",
                "Use the shared operating scope warehouse count during Procurement v2 generation.",
                table_name="Warehouse",
                sample_failed_rows=self._sample_rows(warehouse),
            )

        plant_ids = plant["PlantID"].dropna().unique()
        warehouse_ids = warehouse["WarehouseID"].dropna().unique()
        if len(plant_ids) != 1 or len(warehouse_ids) != 1:
            return
        single_plant_id = plant_ids[0]
        single_warehouse_id = warehouse_ids[0]

        if "PlantID" in warehouse.columns:
            mask = warehouse["PlantID"].eq(single_plant_id)
            report.record_check(bool(mask.all()))
            if not mask.all():
                report.add_issue(
                    "error",
                    "V2_OPERATING_SCOPE_WAREHOUSE_PLANT",
                    "Warehouse.PlantID must reference the single Procurement PlantID.",
                    "Assign the single PlantID from Plant to the Warehouse row.",
                    table_name="Warehouse",
                    column_name="PlantID",
                    sample_failed_rows=self._sample_rows(warehouse[~mask]),
                )

        for table_name, dataframe in dataframes.items():
            if table_name == "InventoryBalance":
                continue
            if "PlantID" in dataframe.columns:
                mask = dataframe["PlantID"].eq(single_plant_id)
                report.record_check(bool(mask.all()))
                if not mask.all():
                    report.add_issue(
                        "error",
                        "V2_OPERATING_SCOPE_PLANT_REFERENCE",
                        f"{table_name}.PlantID must use the single Procurement PlantID.",
                        "Carry the single PlantID through all Procurement v2 location references.",
                        table_name=table_name,
                        column_name="PlantID",
                        sample_failed_rows=self._sample_rows(dataframe[~mask]),
                    )
            if "WarehouseID" in dataframe.columns:
                mask = dataframe["WarehouseID"].eq(single_warehouse_id)
                report.record_check(bool(mask.all()))
                if not mask.all():
                    report.add_issue(
                        "error",
                        "V2_OPERATING_SCOPE_WAREHOUSE_REFERENCE",
                        f"{table_name}.WarehouseID must use the single Procurement WarehouseID.",
                        "Carry the single WarehouseID through all Procurement v2 location references.",
                        table_name=table_name,
                        column_name="WarehouseID",
                        sample_failed_rows=self._sample_rows(dataframe[~mask]),
                    )

    def _validate_v2_constant(
        self,
        dataframes: dict[str, pd.DataFrame],
        table_name: str,
        column_name: str,
        expected: str | None,
        check_type: str,
        report: DataQualityReport,
    ) -> None:
        if expected is None:
            return
        dataframe = dataframes.get(table_name)
        if dataframe is None or column_name not in dataframe.columns:
            return
        mask = dataframe[column_name].fillna("").astype(str).eq(expected)
        report.record_check(bool(mask.all()))
        if not mask.all():
            report.add_issue(
                "error",
                check_type,
                f"{table_name}.{column_name} must be {expected} in Procurement v2.",
                f"Generate only {expected} for {column_name}.",
                table_name=table_name,
                column_name=column_name,
                sample_failed_rows=self._sample_rows(dataframe[~mask]),
            )

    def _expected_column_value(self, schema: SchemaContract, table_name: str, column_name: str, fallback: str) -> str | None:
        table = schema.tables.get(table_name)
        if table is None:
            return fallback
        column = next((column for column in table.columns if column.column_name == column_name), None)
        if column is None:
            return fallback
        values = [str(value).strip() for value in column.allowed_values if str(value).strip()]
        if len(values) > 1:
            return None
        return values[0] if values else fallback

    def _validate_v2_warehouse_master_location(self, dataframes: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        warehouse = dataframes.get("Warehouse")
        plant = dataframes.get("Plant")
        if warehouse is None or plant is None:
            return
        required = {"WarehouseID", "PlantID", "WarehouseCity", "WarehouseState", "WarehouseZipCode"}
        if not required.issubset(warehouse.columns) or not {"PlantID", "PlantCity", "PlantState", "PlantZipCode"}.issubset(plant.columns):
            return
        merged = warehouse.merge(
            plant[["PlantID", "PlantCity", "PlantState", "PlantZipCode"]],
            on="PlantID",
            how="left",
            suffixes=("_warehouse", "_plant"),
        )
        mask = (
            merged["WarehouseCity"].astype(str).eq(merged["PlantCity"].astype(str))
            & merged["WarehouseState"].astype(str).eq(merged["PlantState"].astype(str))
            & merged["WarehouseZipCode"].astype(str).eq(merged["PlantZipCode"].astype(str))
        )
        report.record_check(bool(mask.all()))
        if not mask.all():
            report.add_issue(
                "error",
                "V2_WAREHOUSE_PLANT_LOCATION",
                "Warehouse city/state/zip must align with the assigned PlantID.",
                "Generate warehouse location fields from the parent Plant row.",
                table_name="Warehouse",
                sample_failed_rows=self._sample_rows(merged[~mask]),
            )

    def _validate_v2_quantity_precision(self, dataframes: dict[str, pd.DataFrame], report: DataQualityReport) -> None:
        component = dataframes.get("ComponentMaster")
        if component is None or not {"ComponentID", "UOM"}.issubset(component.columns):
            return
        component_precision = component[["ComponentID", "UOM"]].copy()
        component_precision["__requires_integer_quantity"] = component_precision["UOM"].map(requires_integer_quantity)
        specs = {
            "PurchaseReqLine": ["RequestedQuantity"],
            "RFQLine": ["RFQQuantity"],
            "SupplierQuotationLn": ["QuotedQuantity"],
            "PurchaseOrderLine": ["OrderedQuantity"],
            "ShipmentLine": ["ShippedQuantity"],
            "GoodsReceiptLine": ["ShippedQuantity", "ReceivedQuantity", "DamagedQuantity", "ShortQuantity"],
            "InventoryReceiptDetail": ["OrderedQuantity", "ShippedQuantity", "ReceivedQuantity", "InspectedQuantity", "AcceptedQuantity", "RejectedQuantity"],
            "InventoryTransaction": ["TransactionQuantity"],
            "Inventory": ["OnHandQuantity", "AvailableQuantity"],
        }
        for table_name, quantity_columns in specs.items():
            dataframe = dataframes.get(table_name)
            if dataframe is None or "ComponentID" not in dataframe.columns:
                continue
            merged = dataframe.merge(component_precision, on="ComponentID", how="left")
            integer_required = merged["__requires_integer_quantity"].map(lambda value: bool(value) if pd.notna(value) else False)
            for column_name in quantity_columns:
                if column_name not in merged.columns:
                    continue
                quantity = pd.to_numeric(merged[column_name], errors="coerce")
                mask = (~integer_required) | quantity.map(is_whole_quantity)
                passed = bool(mask.all())
                report.record_check(passed)
                if not passed:
                    report.add_issue(
                        "error",
                        "V2_INTEGER_QUANTITY_PRECISION",
                        f"{table_name}.{column_name} must be a whole number for countable component UOMs.",
                        "Generate integer quantities for countable component UOMs.",
                        table_name=table_name,
                        column_name=column_name,
                        sample_failed_rows=self._sample_rows(merged[~mask]),
                    )

    def _validate_v2_status_diversity(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract, report: DataQualityReport) -> None:
        key_status_columns = {
            ("PurchaseRequisition", "Status"),
            ("PurchaseReqLine", "LineStatus"),
            ("RFQHeader", "RFQStatus"),
            ("RFQLine", "LineStatus"),
            ("SupplierQuotation", "QuotationStatus"),
            ("SupplierQuotationLn", "LineStatus"),
            ("PurchaseOrderHdr", "POStatus"),
            ("PurchaseOrderLine", "LineStatus"),
            ("POSchedule", "ScheduleStatus"),
            ("ShipmentHdr", "ShipmentStatus"),
            ("GoodsReceiptHeader", "ReceiptStatus"),
            ("IncomingInspection", "InspectionStatus"),
            ("InspectionResult", "ResultStatus"),
            ("InventoryTransaction", "TransactionType"),
            ("Inventory", "InventoryStatus"),
            ("SupplierInvoice", "InvoiceStatus"),
            ("PaymentTransaction", "PaymentStatus"),
        }
        full_received_single_status_columns = {
            ("PurchaseOrderHdr", "POStatus"),
            ("PurchaseOrderLine", "LineStatus"),
            ("POSchedule", "ScheduleStatus"),
            ("ShipmentHdr", "ShipmentStatus"),
            ("GoodsReceiptHeader", "ReceiptStatus"),
            ("IncomingInspection", "InspectionStatus"),
            ("InspectionResult", "ResultStatus"),
            ("InventoryTransaction", "TransactionType"),
        }
        for table_name, column_name in key_status_columns:
            if (table_name, column_name) in full_received_single_status_columns:
                continue
            dataframe = dataframes.get(table_name)
            table = schema.tables.get(table_name)
            if dataframe is None or table is None or column_name not in dataframe.columns:
                continue
            column = next((item for item in table.columns if item.column_name == column_name), None)
            if column is None or len(column.allowed_values) <= 1 or len(dataframe) <= 100:
                continue
            passed = dataframe[column_name].nunique(dropna=True) > 1
            report.record_check(passed)
            if not passed:
                report.add_issue(
                    "warning",
                    "V2_STATUS_DIVERSITY",
                    f"{table_name}.{column_name} has only one status value.",
                    "Derive lifecycle statuses so v2 process tables have realistic diversity.",
                    table_name=table_name,
                    column_name=column_name,
                )

    def _validate_foreign_keys(self, dataframes: dict[str, pd.DataFrame], schema: SchemaContract, report: DataQualityReport) -> None:
        for table in schema.tables.values():
            child = dataframes.get(table.table_name)
            if child is None:
                continue
            for column in table.columns:
                if column.key_type != "FK":
                    continue
                if column.column_name not in child.columns:
                    continue
                parent = dataframes.get(column.related_table or "")
                if parent is None or not column.related_column or column.related_column not in parent.columns:
                    report.record_check(False)
                    report.add_issue(
                        "error",
                        "FK_PARENT_EXISTS",
                        f"FK parent {column.related_table}.{column.related_column} is missing.",
                        "Load parent tables before validating child FK columns.",
                        table_name=table.table_name,
                        column_name=column.column_name,
                    )
                    continue
                series = child[column.column_name]
                non_null = series.dropna()
                invalid_mask = series.notna() & ~series.isin(parent[column.related_column].dropna())
                passed = not invalid_mask.any()
                report.record_check(passed)
                if table.table_name in report.table_summaries:
                    report.table_summaries[table.table_name].checks_run += 1
                if not passed:
                    report.add_issue(
                        "error",
                        "FK_INTEGRITY",
                        f"{table.table_name}.{column.column_name} contains values missing from parent {column.related_table}.{column.related_column}.",
                        "Generate child FK values from existing parent keys only.",
                        table_name=table.table_name,
                        column_name=column.column_name,
                        sample_failed_rows=self._sample_rows(child[invalid_mask]),
                    )
                if column.nullable == "No":
                    no_nulls = len(non_null) == len(series)
                    report.record_check(no_nulls)
                    if not no_nulls:
                        report.add_issue(
                            "error",
                            "FK_NOT_NULL",
                            f"Required FK {column.column_name} contains nulls.",
                            "Populate required FK values.",
                            table_name=table.table_name,
                            column_name=column.column_name,
                            sample_failed_rows=self._sample_rows(child[series.isna()]),
                        )

    def _target_rows_by_table(self, schema: SchemaContract, plan: LLMGenerationPlan | None) -> dict[str, int]:
        targets = {table.table_name: table.target_rows for table in schema.tables.values()}
        if plan is not None:
            for row_count in plan.row_count_plan:
                targets[row_count.table_name] = row_count.target_rows
        return targets

    def _is_numeric_type(self, data_type: str) -> bool:
        normalized = data_type.lower().split("(", 1)[0]
        return any(normalized.startswith(token) for token in NUMERIC_TYPE_TOKENS)

    def _is_date_type(self, data_type: str) -> bool:
        normalized = data_type.lower().split("(", 1)[0]
        return any(normalized.startswith(token) for token in DATE_TYPE_TOKENS)

    def _sample_rows(self, dataframe: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
        return [_json_safe(row) for row in dataframe.head(limit).to_dict(orient="records")]


def get_procurement_validation_rules() -> tuple[str, ...]:
    """Return the active Procurement generated-data validation rule groups."""

    return (
        "generic_metadata",
        "procurement_v2_expected_tables",
        "procurement_v2_operating_scope",
        "procurement_v2_location_consistency",
        "procurement_v2_quantity_precision",
        "procurement_v2_status_diversity",
    )


ProcurementGeneratedDataValidationRules = ProcurementGeneratedDataValidator
GeneratedDataValidator = ProcurementGeneratedDataValidator


def _json_safe(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if pd.isna(value):
            output[key] = None
        elif isinstance(value, (np.integer,)):
            output[key] = int(value)
        elif isinstance(value, (np.floating,)):
            output[key] = float(value)
        elif isinstance(value, float) and math.isinf(value):
            output[key] = str(value)
        else:
            output[key] = value
    return output
