"""Core procurement master/reference data generator for Phase 8."""

from __future__ import annotations

import random
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from faker import Faker

from procurement_data_generator.core.contracts.llm_plan_contract import DomainProfile, LLMGenerationPlan, MaterialCategory
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.contracts.validation_report import ValidationReport
from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.llm.plan_validator import is_date_type, is_numeric_type, is_string_type
from procurement_data_generator.modules.procurement.financial_realism_profiles import (
    generate_contract_price,
    generate_standard_cost,
)
from procurement_data_generator.modules.procurement.name_generators import (
    ARTIFICIAL_NUMERIC_SUFFIX_PATTERN,
    NameGenerationError,
    ProcurementNameGenerator,
)
from procurement_data_generator.modules.procurement.role_catalog import PROCUREMENT_V1_UNSUPPORTED_MESSAGE
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_industry_profile_or_default
from procurement_data_generator.modules.shared.industry_profiles.profile_value_provider import IndustryProfileValueProvider
from procurement_data_generator.modules.shared.operating_scope import (
    get_expected_plant_count,
    get_expected_warehouse_count,
)


V2_MASTER_TABLE_ROLES = {
    "supplier_master",
    "component_master",
    "plant_dimension",
    "warehouse_dimension",
    "supplier_component",
}

V2_MASTER_TABLES = {
    "SupplierMaster",
    "ComponentMaster",
    "Plant",
    "Warehouse",
    "SupplierComponent",
}

NAME_GENERATION_TYPES = {
    "vendor_name",
    "material_name",
    "plant_name",
    "warehouse_name",
    "faker_company",
    "faker_person",
}

NAME_COLUMN_NAMES = {
    "vendorname",
    "rawmaterialname",
    "materialname",
    "plantname",
    "warehousename",
    "suppliername",
    "carriername",
    "companyname",
}

GENERIC_ARTIFICIAL_NAME_BASES = {
    "vendor",
    "supplier",
    "material",
    "raw material",
    "rawmaterial",
    "warehouse",
    "plant",
    "carrier",
    "company",
    "person",
}

GENERIC_ARTIFICIAL_NAME_SUFFIX_PATTERN = re.compile(r"^\s*(?P<base>[A-Za-z ]+?)\s+(?P<number>[1-9]|[1-9][0-9])\s*$")


class ProcurementMasterDataGenerator:
    """Generate procurement master/reference tables as pandas DataFrames."""

    def __init__(
        self,
        industry_profile: IndustryProfile | None = None,
        profile_id: str | None = None,
        operating_scope: OperatingScope | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self.name_generator = ProcurementNameGenerator()
        self.operating_scope = operating_scope or DEFAULT_OPERATING_SCOPE
        self.generation_config = generation_config or GenerationConfig()
        effective_profile_id = profile_id or self.generation_config.profile_id
        self.industry_profile = industry_profile or get_industry_profile_or_default(effective_profile_id)
        self.profile_values = IndustryProfileValueProvider(self.industry_profile)

    def generate_master_data(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        seed: int | None = None,
        model_version: str = "v2",
    ) -> tuple[dict[str, pd.DataFrame], ValidationReport]:
        """Generate master/reference dataframes and validate the result."""

        report = ValidationReport()
        if model_version != "v2":
            raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
        dataframes = self._generate_v2_master_data(schema, plan, seed, report)
        self.validate_generated_master_data(dataframes, schema, plan, report, model_version=model_version)
        return dataframes, report

    def get_master_tables(self, schema: SchemaContract, model_version: str = "v2") -> list[TableContract]:
        """Return metadata tables whose TableRole is a master/reference role."""

        if model_version != "v2":
            raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
        return [table for table in schema.ordered_tables if table.table_role in V2_MASTER_TABLE_ROLES]

    def get_target_rows(self, table: TableContract, plan: LLMGenerationPlan) -> int:
        """Use plan row_count_plan when present, otherwise metadata TargetRows."""

        for row_count in plan.row_count_plan:
            if row_count.table_name == table.table_name:
                return row_count.target_rows
        return table.target_rows

    def generate_table(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        existing_dataframes: dict[str, pd.DataFrame],
        seed: int | None,
        existing_names: dict[str, set[str]],
        report: ValidationReport,
    ) -> pd.DataFrame:
        """Generate one master table."""

        count = self.get_target_rows(table, plan)
        rng = random.Random(seed)
        faker = Faker()
        if seed is not None:
            faker.seed_instance(seed)

        data: dict[str, list[Any]] = {}
        generation_columns = self._ordered_columns_for_generation(table)
        for column_index, column in enumerate(generation_columns):
            column_seed = None if seed is None else seed + column_index * 37
            data[column.column_name] = self.generate_column_values(
                table=table,
                column=column,
                count=count,
                plan=plan,
                existing_dataframes=existing_dataframes,
                current_table_data=data,
                seed=column_seed,
                rng=rng,
                faker=faker,
                existing_names=existing_names,
                report=report,
            )

        original_column_order = [column.column_name for column in table.columns]
        return pd.DataFrame(data)[original_column_order]

    def generate_column_values(
        self,
        table: TableContract,
        column: ColumnContract,
        count: int,
        plan: LLMGenerationPlan,
        existing_dataframes: dict[str, pd.DataFrame],
        current_table_data: dict[str, list[Any]],
        seed: int | None,
        rng: random.Random,
        faker: Faker,
        existing_names: dict[str, set[str]],
        report: ValidationReport,
    ) -> list[Any]:
        """Generate values for one metadata column."""

        if column.key_type == "PK" or column.generation_type == "sequence_id":
            return list(range(1, count + 1))
        if column.key_type == "FK" or column.generation_type == "foreign_key":
            return self._generate_foreign_key_values(table, column, count, existing_dataframes, rng, report)

        try:
            semantic_values = self._generate_semantic_column_values(
                table,
                column,
                count,
                plan,
                seed,
                rng,
                faker,
                existing_names,
                existing_dataframes,
                current_table_data,
            )
        except NameGenerationError as exc:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message=str(exc),
                suggested_fix="Provide more domain profile variety or lower the target row count.",
            )
            return [None] * count
        if semantic_values is not None:
            return semantic_values

        try:
            if column.generation_type == "vendor_name":
                names = self.name_generator.generate_vendor_names(count, plan.domain_profile, seed, existing_names["vendor"])
                existing_names["vendor"].update(names)
                return names
            if column.generation_type == "material_name":
                names = self.name_generator.generate_material_names(count, plan.domain_profile, seed, existing_names["material"])
                existing_names["material"].update(names)
                return names
            if column.generation_type == "plant_name":
                names = self.name_generator.generate_plant_names(count, plan.domain_profile, seed, existing_names["plant"])
                existing_names["plant"].update(names)
                return names
            if column.generation_type == "warehouse_name":
                names = self._generate_warehouse_names_for_assigned_plants(
                    count=count,
                    domain_profile=plan.domain_profile,
                    existing_dataframes=existing_dataframes,
                    current_table_data=current_table_data,
                    seed=seed,
                    existing_names=existing_names["warehouse"],
                )
                existing_names["warehouse"].update(names)
                return names
            if column.generation_type == "faker_company":
                names = self.name_generator.generate_faker_company_names(count, seed, existing_names["faker_company"])
                existing_names["faker_company"].update(names)
                return names
            if column.generation_type == "faker_person":
                names = self.name_generator.generate_faker_person_names(count, seed, existing_names["faker_person"])
                existing_names["faker_person"].update(names)
                return names
        except NameGenerationError as exc:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message=str(exc),
                suggested_fix="Provide more domain profile variety or lower the target row count.",
            )
            return [None] * count

        if column.generation_type == "category":
            return self._generate_category_values(table, column, count, plan, rng)
        if column.generation_type == "status":
            return self._generate_status_values(column, count, rng)
        if column.generation_type == "integer_range":
            return self._generate_integer_values(column, count, rng)
        if column.generation_type == "decimal_range":
            return self._generate_decimal_values(column, count, rng)
        if column.generation_type == "date_range":
            return self._generate_date_values(column, count, rng)
        if column.generation_type == "date_offset":
            report.add_warning(
                table_name=table.table_name,
                column_name=column.column_name,
                message="date_offset has only basic Phase 8 support; using date_range-style generation.",
                suggested_fix="Use full date dependencies in the later transaction/formula phases.",
            )
            return self._generate_date_values(column, count, rng)
        if column.generation_type == "calculated":
            if column.nullable == "Yes":
                report.add_warning(
                    table_name=table.table_name,
                    column_name=column.column_name,
                    message="Calculated column skipped in Phase 8.",
                    suggested_fix="Full formula execution is handled in Phase 10.",
                )
                return [None] * count
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Non-null calculated column cannot be generated in Phase 8.",
                suggested_fix="Make the column nullable for Phase 8 or wait for Phase 10 formula execution.",
            )
            return [None] * count

        if column.nullable == "Yes":
            report.add_warning(
                table_name=table.table_name,
                column_name=column.column_name,
                message=f"GenerationType {column.generation_type} is unsupported in Phase 8; filled with null.",
                suggested_fix="Use a supported master-data GenerationType.",
            )
            return [None] * count

        report.add_error(
            table_name=table.table_name,
            column_name=column.column_name,
            message=f"GenerationType {column.generation_type} is unsupported for a non-null column in Phase 8.",
            suggested_fix="Use a supported master-data GenerationType or make the column nullable.",
        )
        return [None] * count

    def validate_generated_master_data(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        report: ValidationReport,
        model_version: str = "v2",
    ) -> None:
        """Validate generated master dataframes."""

        if model_version != "v2":
            raise ValueError(PROCUREMENT_V1_UNSUPPORTED_MESSAGE)
        for table in self.get_master_tables(schema, model_version=model_version):
            dataframe = dataframes.get(table.table_name)
            target_rows = self.get_target_rows(table, plan)
            if dataframe is None:
                report.add_error(
                    table_name=table.table_name,
                    message="Master table DataFrame was not generated.",
                    suggested_fix="Generate one DataFrame for each master table role.",
                )
                continue
            if len(dataframe) != target_rows:
                report.add_error(
                    table_name=table.table_name,
                    message=f"Generated row count {len(dataframe)} does not match target {target_rows}.",
                    suggested_fix="Generate exactly the target row count for this table.",
                )
            for column in table.columns:
                if column.column_name not in dataframe.columns:
                    report.add_error(
                        table_name=table.table_name,
                        column_name=column.column_name,
                        message="Metadata column missing from generated DataFrame.",
                        suggested_fix="Generate every metadata column for each master table.",
                    )
                    continue
                series = dataframe[column.column_name]
                if column.key_type == "PK":
                    if series.isna().any():
                        report.add_error(
                            table_name=table.table_name,
                            column_name=column.column_name,
                            message="Primary key contains null values.",
                            suggested_fix="Generate non-null unique PK values.",
                        )
                    if not series.is_unique:
                        report.add_error(
                            table_name=table.table_name,
                            column_name=column.column_name,
                            message="Primary key contains duplicate values.",
                            suggested_fix="Generate unique PK values.",
                        )
                if column.key_type == "FK":
                    self._validate_fk_column(table, column, series, dataframes, report)
                if column.nullable == "No" and series.isna().any():
                    report.add_error(
                        table_name=table.table_name,
                        column_name=column.column_name,
                        message="Nullable = No column contains null values.",
                        suggested_fix="Generate non-null values for required columns.",
                    )
                if column.allowed_values:
                    allowed_as_text = {str(value) for value in column.allowed_values}
                    invalid_values = sorted({str(value) for value in series.dropna()} - allowed_as_text)
                    if invalid_values:
                        report.add_error(
                            table_name=table.table_name,
                            column_name=column.column_name,
                            message=f"Generated values outside AllowedValues: {', '.join(map(str, invalid_values))}.",
                            suggested_fix="Use only metadata AllowedValues.",
                        )
                self._validate_numeric_range(table, column, series, report)
                self._validate_date_range(table, column, series, report)
                self._validate_name_column(table, column, series, report)

        self._validate_v2_master_business_rules(dataframes, schema, report)

    def export_master_data(self, dataframes: dict[str, pd.DataFrame], output_folder: str | Path) -> list[Path]:
        """Export generated master dataframes to CSV files."""

        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        paths = []
        for table_name, dataframe in dataframes.items():
            path = output_path / f"{table_name}.csv"
            dataframe.to_csv(path, index=False)
            paths.append(path)
        return paths

    def _generate_v2_master_data(
        self,
        schema: SchemaContract,
        plan: LLMGenerationPlan,
        seed: int | None,
        report: ValidationReport,
    ) -> dict[str, pd.DataFrame]:
        """Generate Procurement v2 master/support tables only."""

        dataframes: dict[str, pd.DataFrame] = {}
        tables = [table for table in schema.ordered_tables if table.table_role in V2_MASTER_TABLE_ROLES]
        for table in self._order_master_tables(tables, report):
            table_seed = None if seed is None else seed + table.process_order * 1000
            rng = random.Random(table_seed)
            if table.table_role == "supplier_master":
                dataframe = self._generate_v2_supplier_master(table, plan, table_seed, rng)
            elif table.table_role == "component_master":
                dataframe = self._generate_v2_component_master(table, plan, table_seed, rng)
            elif table.table_role == "plant_dimension":
                dataframe = self._generate_v2_plant(table, plan, table_seed, rng)
            elif table.table_role == "warehouse_dimension":
                dataframe = self._generate_v2_warehouse(table, plan, dataframes, table_seed, rng, report)
            elif table.table_role == "supplier_component":
                dataframe = self._generate_v2_supplier_component(table, plan, dataframes, table_seed, rng, report)
            else:
                continue
            dataframes[table.table_name] = dataframe
        return dataframes

    def _generate_v2_supplier_master(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        seed: int | None,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        domain_profile = self._profile_domain_profile(plan)
        locations = self._shuffled_us_locations(count, rng)
        supplier_cities = self._column_allowed_values(table, "SupplierCity")
        supplier_states = self._column_allowed_values(table, "SupplierState")
        supplier_countries = self._column_allowed_values(table, "SupplierCountry")
        names = self.name_generator.generate_vendor_names(count, domain_profile, seed, set())
        values_by_column: dict[str, list[Any]] = {
            "SupplierID": list(range(1, count + 1)),
            "SupplierCode": [f"SUP-{index:05d}" for index in range(1, count + 1)],
            "SupplierName": names,
            "SupplierCity": self._repeat_allowed_or_location(supplier_cities, locations, "city", count),
            "SupplierState": self._repeat_allowed_or_location(supplier_states, locations, "state", count),
            "SupplierCountry": self._repeat_allowed_or_location(supplier_countries, locations, "country", count, self.profile_values.default_country),
            "SupplierZipCode": [locations[index]["zip"] for index in range(count)],
        }
        return self._build_v2_dataframe(table, count, plan, rng, values_by_column, status_primary="Active")

    def _generate_v2_component_master(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        seed: int | None,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        domain_profile = self._profile_domain_profile(plan)
        names = self.name_generator.generate_material_names(count, domain_profile, seed, set())
        allowed_categories = self._profile_component_categories(table)
        component_categories = [allowed_categories[index % len(allowed_categories)] for index in range(count)]
        rng.shuffle(component_categories)
        standard_costs = [
            generate_standard_cost(category, rng, self.industry_profile.procurement)
            for category in component_categories
        ]
        values_by_column: dict[str, list[Any]] = {
            "ComponentID": list(range(1, count + 1)),
            "ComponentCode": [f"CMP-{index:05d}" for index in range(1, count + 1)],
            "ComponentName": names,
            "ComponentCategory": component_categories,
            "StandardCost": standard_costs,
            "CurrencyCode": [self._column_value_or_default(table, "CurrencyCode", self.profile_values.default_currency)] * count,
            "SafetyCriticalFlag": [
                1 if self.profile_values.is_procurement_safety_critical_category(category) or rng.random() < 0.18 else 0
                for category in component_categories
            ],
        }
        return self._build_v2_dataframe(table, count, plan, rng, values_by_column, status_primary="Active")

    def _generate_v2_plant(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        seed: int | None,
        rng: random.Random,
    ) -> pd.DataFrame:
        count = get_expected_plant_count()
        locations = self._shuffled_us_locations(count, rng)
        plant_types = self.industry_profile.procurement.plant_type_names or ("Manufacturing Plant",)
        plant_cities = self._column_allowed_values(table, "PlantCity")
        plant_states = self._column_allowed_values(table, "PlantState")
        plant_countries = self._column_allowed_values(table, "PlantCountry")
        values_by_column: dict[str, list[Any]] = {
            "PlantID": list(range(1, count + 1)),
            "PlantCode": [f"PLT-{locations[index]['city'][:3].upper()}-{index + 1:02d}" for index in range(count)],
            "PlantName": [f"{(plant_cities[index % len(plant_cities)] if plant_cities else locations[index]['city'])} {plant_types[index % len(plant_types)]}" for index in range(count)],
            "PlantCity": self._repeat_allowed_or_location(plant_cities, locations, "city", count),
            "PlantState": self._repeat_allowed_or_location(plant_states, locations, "state", count),
            "PlantCountry": self._repeat_allowed_or_location(plant_countries, locations, "country", count, self.profile_values.default_country),
            "PlantZipCode": [locations[index]["zip"] for index in range(count)],
        }
        return self._build_v2_dataframe(table, count, plan, rng, values_by_column, status_primary="Active")

    def _generate_v2_warehouse(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        existing_dataframes: dict[str, pd.DataFrame],
        seed: int | None,
        rng: random.Random,
        report: ValidationReport,
    ) -> pd.DataFrame:
        count = get_expected_warehouse_count()
        plant_df = existing_dataframes.get("Plant")
        if plant_df is None or plant_df.empty:
            report.add_error(
                table_name=table.table_name,
                column_name="PlantID",
                message="Plant must be generated before Warehouse in Procurement v2.",
                suggested_fix="Keep Plant before Warehouse in metadata ProcessOrder.",
            )
            return pd.DataFrame({column.column_name: [None] * count for column in table.columns})

        allowed_types = self._column_allowed_values(table, "WarehouseType") or [
            _warehouse_type_label(value) for value in self.industry_profile.procurement.warehouse_type_names
        ]
        plant_rows = plant_df.to_dict("records")
        values_by_column: dict[str, list[Any]] = {
            "WarehouseID": list(range(1, count + 1)),
            "PlantID": [],
            "WarehouseCode": [],
            "WarehouseName": [],
            "WarehouseType": [],
            "WarehouseLocation": [],
            "WarehouseCity": [],
            "WarehouseState": [],
            "WarehouseCountry": [],
            "WarehouseZipCode": [],
        }
        for index in range(count):
            plant = plant_rows[index % len(plant_rows)]
            warehouse_type = allowed_types[index % len(allowed_types)]
            city = str(plant["PlantCity"])
            state = str(plant["PlantState"])
            zip_code = str(plant["PlantZipCode"])
            values_by_column["PlantID"].append(plant["PlantID"])
            values_by_column["WarehouseCode"].append(f"WH-{city[:3].upper()}-{index + 1:03d}")
            values_by_column["WarehouseName"].append(f"{city} {warehouse_type} Warehouse")
            values_by_column["WarehouseType"].append(warehouse_type)
            values_by_column["WarehouseLocation"].append(f"Building {chr(65 + index % 26)}, {city} Manufacturing Campus")
            values_by_column["WarehouseCity"].append(city)
            values_by_column["WarehouseState"].append(state)
            values_by_column["WarehouseCountry"].append(str(plant.get("PlantCountry", self.profile_values.default_country)))
            values_by_column["WarehouseZipCode"].append(zip_code)
        return self._build_v2_dataframe(table, count, plan, rng, values_by_column, status_primary="Active")

    def _profile_component_categories(self, table: TableContract) -> list[str]:
        profile_categories = list(self.industry_profile.procurement.component_category_codes)
        allowed_categories = self._column_allowed_values(table, "ComponentCategory")
        if not allowed_categories:
            return profile_categories
        compatible_categories = [category for category in profile_categories if category in allowed_categories]
        return compatible_categories or allowed_categories

    def _profile_domain_profile(self, plan: LLMGenerationPlan) -> DomainProfile:
        procurement = self.industry_profile.procurement
        material_categories = []
        for category_name, examples in procurement.component_material_examples.items():
            specs = procurement.component_specification_patterns.get(category_name, ())
            material_categories.append(
                MaterialCategory(
                    category_name=category_name,
                    material_examples=list(examples),
                    specification_patterns=list(specs),
                )
            )
        if not material_categories:
            material_categories = [
                MaterialCategory(
                    category_name=category,
                    material_examples=list(procurement.component_name_patterns),
                    specification_patterns=["Industrial Grade", "Standard Pack", "Grade A"],
                )
                for category in procurement.component_categories
            ]
        return DomainProfile(
            industry=self.industry_profile.industry_name,
            business_context=self.industry_profile.industry_description,
            vendor_categories=list(procurement.supplier_name_patterns or procurement.component_categories),
            material_categories=material_categories,
            warehouse_types=list(procurement.warehouse_type_names or plan.domain_profile.warehouse_types),
            plant_locations=list(plan.domain_profile.plant_locations),
            carrier_name_patterns=list(plan.domain_profile.carrier_name_patterns),
            inspection_test_categories=list(plan.domain_profile.inspection_test_categories),
        )

    def _generate_v2_supplier_component(
        self,
        table: TableContract,
        plan: LLMGenerationPlan,
        existing_dataframes: dict[str, pd.DataFrame],
        seed: int | None,
        rng: random.Random,
        report: ValidationReport,
    ) -> pd.DataFrame:
        count = self.get_target_rows(table, plan)
        supplier_df = existing_dataframes.get("SupplierMaster")
        component_df = existing_dataframes.get("ComponentMaster")
        if supplier_df is None or supplier_df.empty or component_df is None or component_df.empty:
            report.add_error(
                table_name=table.table_name,
                message="SupplierMaster and ComponentMaster must be generated before SupplierComponent.",
                suggested_fix="Keep supplier/component parent tables before SupplierComponent.",
            )
            return pd.DataFrame({column.column_name: [None] * count for column in table.columns})

        supplier_ids = list(supplier_df["SupplierID"])
        component_records = component_df[["ComponentID", "StandardCost"]].to_dict("records")
        pairs: list[tuple[int, int]] = []
        preferred_components: set[int] = set()
        for index, component in enumerate(component_records[: min(count, len(component_records))]):
            supplier_id = supplier_ids[index % len(supplier_ids)]
            component_id = int(component["ComponentID"])
            pairs.append((supplier_id, component_id))
            preferred_components.add(component_id)

        seen = set(pairs)
        all_pairs = [(supplier_id, int(component["ComponentID"])) for component in component_records for supplier_id in supplier_ids]
        rng.shuffle(all_pairs)
        for pair in all_pairs:
            if len(pairs) == count:
                break
            if pair in seen:
                continue
            pairs.append(pair)
            seen.add(pair)

        if len(pairs) < count:
            report.add_warning(
                table_name=table.table_name,
                message="Could not create requested SupplierComponent rows without duplicate supplier/component pairs.",
                suggested_fix="Increase suppliers/components or reduce SupplierComponent target rows.",
            )

        component_cost = {int(row["ComponentID"]): float(row["StandardCost"]) for row in component_records}
        min_order_column = self._column(table, "MinOrderQuantity")
        lead_time_column = self._column(table, "LeadTimeDays")
        price_column = self._column(table, "ContractPrice")
        values_by_column: dict[str, list[Any]] = {
            "SupplierComponentID": list(range(1, len(pairs) + 1)),
            "SupplierID": [pair[0] for pair in pairs],
            "ComponentID": [pair[1] for pair in pairs],
            "PreferredSupplierFlag": [1 if pair[1] in preferred_components and pairs.index(pair) < len(component_records) else 0 for pair in pairs],
            "MinOrderQuantity": self._generate_decimal_values(min_order_column, len(pairs), rng) if min_order_column else [1.0] * len(pairs),
            "LeadTimeDays": self._generate_integer_values(lead_time_column, len(pairs), rng) if lead_time_column else [14] * len(pairs),
            "ContractPrice": [],
            "CurrencyCode": [self._column_value_or_default(table, "CurrencyCode", self.profile_values.default_currency)] * len(pairs),
        }
        minimum = float(_parse_number(price_column.min_value if price_column else None, 1.0))
        maximum = float(_parse_number(price_column.max_value if price_column else None, 5000.0))
        for _, component_id in pairs:
            base_cost = component_cost.get(component_id, 100.0)
            price = min(max(generate_contract_price(base_cost, rng), minimum), maximum)
            values_by_column["ContractPrice"].append(round(price, _decimal_scale(price_column.data_type) if price_column else 2))
        return self._build_v2_dataframe(table, len(pairs), plan, rng, values_by_column, status_primary="Active")

    def _build_v2_dataframe(
        self,
        table: TableContract,
        count: int,
        plan: LLMGenerationPlan,
        rng: random.Random,
        values_by_column: dict[str, list[Any]],
        status_primary: str = "Active",
    ) -> pd.DataFrame:
        data: dict[str, list[Any]] = {}
        for column in table.columns:
            if column.column_name in values_by_column:
                data[column.column_name] = values_by_column[column.column_name]
                continue
            if column.key_type == "PK" or column.generation_type == "sequence_id":
                data[column.column_name] = list(range(1, count + 1))
            elif column.column_name == "CurrencyCode":
                data[column.column_name] = [self._column_value_or_default(table, column.column_name, self.profile_values.default_currency)] * count
            elif column.column_name.endswith("Country"):
                data[column.column_name] = [self._column_value_or_default(table, column.column_name, self.profile_values.default_country)] * count
            elif column.generation_type == "category":
                data[column.column_name] = self._generate_category_values(table, column, count, plan, rng)
            elif column.generation_type == "status":
                data[column.column_name] = self._generate_weighted_status_values(column.allowed_values, count, rng, status_primary)
            elif column.generation_type == "integer_range":
                data[column.column_name] = self._generate_integer_values(column, count, rng)
            elif column.generation_type == "decimal_range":
                data[column.column_name] = self._generate_decimal_values(column, count, rng)
            else:
                data[column.column_name] = [None] * count if column.nullable == "Yes" else self._generate_category_values(table, column, count, plan, rng)
        return pd.DataFrame(data)[[column.column_name for column in table.columns]]

    def _validate_v2_master_business_rules(
        self,
        dataframes: dict[str, pd.DataFrame],
        schema: SchemaContract,
        report: ValidationReport,
    ) -> None:
        if set(dataframes) != V2_MASTER_TABLES:
            missing = sorted(V2_MASTER_TABLES - set(dataframes))
            extra = sorted(set(dataframes) - V2_MASTER_TABLES)
            if missing:
                report.add_error(message=f"Procurement v2 master generation is missing tables: {', '.join(missing)}.", suggested_fix="Generate exactly the five v2 master/support tables.")
            if extra:
                report.add_error(message=f"Procurement v2 master generation produced non-master tables: {', '.join(extra)}.", suggested_fix="Do not generate transaction tables in V2-5.")

        self._validate_constant_value(dataframes, "SupplierMaster", "SupplierCountry", self._schema_column_value_or_default(schema, "SupplierMaster", "SupplierCountry", self.profile_values.default_country), report)
        self._validate_constant_value(dataframes, "Plant", "PlantCountry", self._schema_column_value_or_default(schema, "Plant", "PlantCountry", self.profile_values.default_country), report)
        self._validate_constant_value(dataframes, "Warehouse", "WarehouseCountry", self._schema_column_value_or_default(schema, "Warehouse", "WarehouseCountry", self.profile_values.default_country), report)
        self._validate_constant_value(dataframes, "ComponentMaster", "CurrencyCode", self._schema_column_value_or_default(schema, "ComponentMaster", "CurrencyCode", self.profile_values.default_currency), report)
        self._validate_constant_value(dataframes, "SupplierComponent", "CurrencyCode", self._schema_column_value_or_default(schema, "SupplierComponent", "CurrencyCode", self.profile_values.default_currency), report)
        self._validate_unique_column(dataframes, "SupplierMaster", "SupplierName", report)
        self._validate_unique_column(dataframes, "ComponentMaster", "ComponentName", report)
        self._validate_unique_column(dataframes, "Plant", "PlantName", report)
        self._validate_unique_column(dataframes, "Warehouse", "WarehouseName", report)
        self._validate_warehouse_location_alignment(dataframes, report)
        self._validate_supplier_component_rules(dataframes, report)
        for table_name, dataframe in dataframes.items():
            table = schema.tables.get(table_name)
            if table is None:
                continue
            for column in table.columns:
                if column.generation_type == "status" and column.column_name in dataframe.columns:
                    values = column.allowed_values
                    if len(values) > 1 and len(dataframe) >= 3 and dataframe[column.column_name].nunique(dropna=True) <= 1:
                        report.add_warning(
                            table_name=table_name,
                            column_name=column.column_name,
                            message="Status column has no variety despite multiple AllowedValues.",
                            suggested_fix="Derive or sample statuses so master/support data is realistic.",
                        )

    def _validate_constant_value(
        self,
        dataframes: dict[str, pd.DataFrame],
        table_name: str,
        column_name: str,
        expected_value: str,
        report: ValidationReport,
    ) -> None:
        dataframe = dataframes.get(table_name)
        if dataframe is None or column_name not in dataframe.columns:
            return
        invalid = sorted(set(dataframe[column_name].dropna()) - {expected_value})
        if invalid:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message=f"Procurement v2 requires {column_name} = {expected_value}; found {invalid[:5]}.",
                suggested_fix=f"Generate only {expected_value} for this column.",
            )

    def _validate_unique_column(
        self,
        dataframes: dict[str, pd.DataFrame],
        table_name: str,
        column_name: str,
        report: ValidationReport,
    ) -> None:
        dataframe = dataframes.get(table_name)
        if dataframe is None or column_name not in dataframe.columns:
            return
        values = dataframe[column_name].dropna()
        if not values.is_unique:
            report.add_error(
                table_name=table_name,
                column_name=column_name,
                message="Procurement v2 master name column contains duplicate values.",
                suggested_fix="Generate unique business names for master/support tables.",
            )

    def _validate_warehouse_location_alignment(self, dataframes: dict[str, pd.DataFrame], report: ValidationReport) -> None:
        warehouse_df = dataframes.get("Warehouse")
        plant_df = dataframes.get("Plant")
        if warehouse_df is None or plant_df is None:
            return
        plant_lookup = plant_df.set_index("PlantID")[["PlantCity", "PlantState", "PlantZipCode"]].to_dict("index")
        for _, warehouse in warehouse_df.iterrows():
            plant = plant_lookup.get(warehouse.get("PlantID"))
            if not plant:
                continue
            if (
                warehouse.get("WarehouseCity") != plant["PlantCity"]
                or warehouse.get("WarehouseState") != plant["PlantState"]
                or str(warehouse.get("WarehouseZipCode")) != str(plant["PlantZipCode"])
            ):
                report.add_error(
                    table_name="Warehouse",
                    column_name="PlantID",
                    message="Warehouse city/state/zip does not align with assigned PlantID.",
                    suggested_fix="Generate warehouse location values from the parent Plant row.",
                )
                return

    def _validate_supplier_component_rules(self, dataframes: dict[str, pd.DataFrame], report: ValidationReport) -> None:
        supplier_component_df = dataframes.get("SupplierComponent")
        component_df = dataframes.get("ComponentMaster")
        if supplier_component_df is None or component_df is None:
            return
        if supplier_component_df.duplicated(["SupplierID", "ComponentID"]).any():
            report.add_error(
                table_name="SupplierComponent",
                message="Duplicate SupplierID + ComponentID combinations found.",
                suggested_fix="Generate unique supplier-component eligibility pairs.",
            )
        mapped_components = set(supplier_component_df["ComponentID"].dropna())
        component_ids = set(component_df["ComponentID"].dropna())
        if len(supplier_component_df) >= len(component_df) and not component_ids.issubset(mapped_components):
            report.add_error(
                table_name="SupplierComponent",
                column_name="ComponentID",
                message="At least one ComponentID has no eligible supplier.",
                suggested_fix="Assign at least one supplier to every component when enough SupplierComponent rows exist.",
            )
        preferred_counts = supplier_component_df.groupby("ComponentID")["PreferredSupplierFlag"].sum()
        if (preferred_counts > 1).any():
            report.add_error(
                table_name="SupplierComponent",
                column_name="PreferredSupplierFlag",
                message="More than one preferred supplier exists for a component.",
                suggested_fix="Mark at most one preferred supplier per ComponentID.",
            )
        component_cost = component_df.set_index("ComponentID")["StandardCost"].astype(float)
        merged = supplier_component_df.join(component_cost, on="ComponentID")
        ratios = merged["ContractPrice"].astype(float) / merged["StandardCost"].astype(float)
        if ((ratios < 0.9) | (ratios > 1.25)).any():
            report.add_error(
                table_name="SupplierComponent",
                column_name="ContractPrice",
                message="ContractPrice is not reasonably related to ComponentMaster.StandardCost.",
                suggested_fix="Generate ContractPrice around StandardCost * 0.9 to 1.25.",
            )

    def _generate_weighted_status_values(self, values: list[str], count: int, rng: random.Random, primary: str = "Active") -> list[str]:
        allowed = values or [primary]
        if count <= 0:
            return []
        if len(allowed) == 1:
            return [allowed[0]] * count
        primary_value = primary if primary in allowed else allowed[0]
        secondary_values = [value for value in allowed if value != primary_value]
        result = [primary_value] * count
        secondary_count = min(max(1, round(count * 0.12)), count - 1)
        for index in range(secondary_count):
            result[index] = secondary_values[index % len(secondary_values)]
        rng.shuffle(result)
        return result

    def _shuffled_us_locations(self, count: int, rng: random.Random) -> list[dict[str, str]]:
        locations = list(self.profile_values.location_catalog())
        rng.shuffle(locations)
        return [locations[index % len(locations)] for index in range(count)]

    def _column(self, table: TableContract, column_name: str) -> ColumnContract | None:
        return next((column for column in table.columns if column.column_name == column_name), None)

    def _column_allowed_values(self, table: TableContract, column_name: str) -> list[str]:
        column = self._column(table, column_name)
        return list(column.allowed_values) if column else []

    def _column_value_or_default(self, table: TableContract, column_name: str, default: str) -> str:
        values = self._column_allowed_values(table, column_name)
        return str(values[0]) if values else default

    def _schema_column_value_or_default(self, schema: SchemaContract, table_name: str, column_name: str, default: str) -> str:
        table = schema.tables.get(table_name)
        if table is None:
            return default
        return self._column_value_or_default(table, column_name, default)

    def _repeat_allowed_or_location(
        self,
        allowed_values: list[str],
        locations: list[dict[str, str]],
        location_key: str,
        count: int,
        fallback: str | None = None,
    ) -> list[str]:
        if allowed_values:
            return [str(allowed_values[index % len(allowed_values)]) for index in range(count)]
        return [str(locations[index].get(location_key, fallback or "")) for index in range(count)]

    def _order_master_tables(self, tables: list[TableContract], report: ValidationReport) -> list[TableContract]:
        table_by_name = {table.table_name: table for table in tables}
        remaining = set(table_by_name)
        ordered: list[TableContract] = []
        while remaining:
            progressed = False
            for table_name in sorted(remaining, key=lambda name: table_by_name[name].process_order):
                table = table_by_name[table_name]
                master_parent_names = {
                    column.related_table
                    for column in table.columns
                    if column.key_type == "FK" and column.related_table in table_by_name
                }
                if master_parent_names.issubset({table.table_name for table in ordered}):
                    ordered.append(table)
                    remaining.remove(table_name)
                    progressed = True
            if not progressed:
                report.add_warning(
                    message="Could not fully resolve master FK order; falling back to ProcessOrder.",
                    suggested_fix="Ensure master FK parent tables have earlier ProcessOrder or valid metadata relationships.",
                )
                ordered.extend(sorted((table_by_name[name] for name in remaining), key=lambda item: item.process_order))
                break
        return sorted(ordered, key=lambda table: ordered.index(table))

    def _ordered_columns_for_generation(self, table: TableContract) -> list[ColumnContract]:
        def priority(column: ColumnContract) -> tuple[int, str]:
            if column.key_type == "PK":
                return (0, column.column_name)
            if column.key_type == "FK":
                return (1, column.column_name)
            if table.table_role == "warehouse_dimension" and column.generation_type == "warehouse_name":
                return (3, column.column_name)
            return (2, column.column_name)

        return sorted(table.columns, key=priority)

    def _generate_foreign_key_values(
        self,
        table: TableContract,
        column: ColumnContract,
        count: int,
        existing_dataframes: dict[str, pd.DataFrame],
        rng: random.Random,
        report: ValidationReport,
    ) -> list[Any]:
        if not column.related_table or not column.related_column:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="FK column is missing RelatedTable or RelatedColumn.",
                suggested_fix="Provide FK metadata before generating master data.",
            )
            return [None] * count
        parent_df = existing_dataframes.get(column.related_table)
        if parent_df is None or column.related_column not in parent_df.columns:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message=f"Parent table {column.related_table}.{column.related_column} is not generated yet.",
                suggested_fix="Generate FK parent master tables before child tables.",
            )
            return [None] * count
        parent_values = list(parent_df[column.related_column].dropna())
        if not parent_values:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Parent key column has no values.",
                suggested_fix="Generate non-null parent PK values before FK values.",
            )
            return [None] * count
        return [parent_values[index % len(parent_values)] for index in rng.sample(range(count), count)]

    def _generate_semantic_column_values(
        self,
        table: TableContract,
        column: ColumnContract,
        count: int,
        plan: LLMGenerationPlan,
        seed: int | None,
        rng: random.Random,
        faker: Faker,
        existing_names: dict[str, set[str]],
        existing_dataframes: dict[str, pd.DataFrame],
        current_table_data: dict[str, list[Any]],
    ) -> list[Any] | None:
        lower_name = column.column_name.lower()
        if table.table_role == "vendor_dimension" and lower_name in {"vendorname", "vendor_name", "suppliername", "supplier_name"}:
            names = self.name_generator.generate_vendor_names(count, plan.domain_profile, seed, existing_names["vendor"])
            existing_names["vendor"].update(names)
            return names
        if table.table_role == "material_dimension" and lower_name in {
            "rawmaterialname",
            "raw_material_name",
            "materialname",
            "material_name",
            "itemname",
            "item_name",
        }:
            names = self.name_generator.generate_material_names(count, plan.domain_profile, seed, existing_names["material"])
            existing_names["material"].update(names)
            return names
        if table.table_role == "plant_dimension" and lower_name in {"plantname", "plant_name", "sitename", "site_name"}:
            names = self.name_generator.generate_plant_names(count, plan.domain_profile, seed, existing_names["plant"])
            existing_names["plant"].update(names)
            return names
        if table.table_role == "warehouse_dimension" and lower_name in {"warehousename", "warehouse_name"}:
            names = self._generate_warehouse_names_for_assigned_plants(
                count=count,
                domain_profile=plan.domain_profile,
                existing_dataframes=existing_dataframes,
                current_table_data=current_table_data,
                seed=seed,
                existing_names=existing_names["warehouse"],
            )
            existing_names["warehouse"].update(names)
            return names
        if "email" in lower_name:
            return [faker.unique.email() for _ in range(count)]
        if "phone" in lower_name:
            return [faker.phone_number() for _ in range(count)]
        if lower_name in {"city", "location"} or lower_name.endswith("city"):
            locations = plan.domain_profile.plant_locations or list(ProcurementNameGenerator.fallback_locations)
            return [locations[index % len(locations)] for index in range(count)]
        if "country" in lower_name:
            return ["India"] * count
        if "paymentterms" in lower_name.replace("_", "") or "payment_terms" in lower_name:
            return self._choice_values(["Net 30", "Net 45", "Net 60", "Advance"], count, rng)
        if "leadtime" in lower_name.replace("_", ""):
            return [rng.randint(3, 45) for _ in range(count)]
        if "qualityrating" in lower_name.replace("_", ""):
            return [round(rng.uniform(70, 100), 2) for _ in range(count)]
        if lower_name in {"uom", "unitofmeasure", "unit_of_measure"} or lower_name.endswith("uom"):
            return self._choice_values(column.allowed_values or ["PCS", "KG", "Litre", "Meter", "Box", "Roll"], count, rng)
        if "cost" in lower_name or "price" in lower_name:
            return self._generate_decimal_values(column, count, rng)
        if "reorder" in lower_name or "safetystock" in lower_name.replace("_", ""):
            return self._generate_integer_values(column, count, rng)
        return None

    def _generate_category_values(
        self,
        table: TableContract,
        column: ColumnContract,
        count: int,
        plan: LLMGenerationPlan,
        rng: random.Random,
    ) -> list[str]:
        if column.allowed_values:
            return self._choice_values(column.allowed_values, count, rng)
        if table.table_role == "vendor_dimension" and plan.domain_profile.vendor_categories:
            return self._choice_values(plan.domain_profile.vendor_categories, count, rng)
        if table.table_role == "material_dimension" and plan.domain_profile.material_categories:
            values = [category.category_name for category in plan.domain_profile.material_categories]
            return self._choice_values(values, count, rng)
        if table.table_role == "warehouse_dimension" and plan.domain_profile.warehouse_types:
            return self._choice_values(plan.domain_profile.warehouse_types, count, rng)
        return self._choice_values(["General", "Standard", "Operational"], count, rng)

    def _generate_status_values(self, column: ColumnContract, count: int, rng: random.Random) -> list[str]:
        values = column.allowed_values or ["Active", "Inactive"]
        if "Active" in values:
            return ["Inactive" if "Inactive" in values and rng.random() < 0.08 else "Active" for _ in range(count)]
        return self._choice_values(values, count, rng)

    def _generate_integer_values(self, column: ColumnContract, count: int, rng: random.Random) -> list[int]:
        minimum = int(_parse_number(column.min_value, 1))
        maximum = int(_parse_number(column.max_value, 100))
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        return [rng.randint(minimum, maximum) for _ in range(count)]

    def _generate_decimal_values(self, column: ColumnContract, count: int, rng: random.Random) -> list[float]:
        minimum = float(_parse_number(column.min_value, 1.0))
        maximum = float(_parse_number(column.max_value, 100.0))
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        scale = _decimal_scale(column.data_type)
        return [round(rng.uniform(minimum, maximum), scale) for _ in range(count)]

    def _generate_date_values(self, column: ColumnContract, count: int, rng: random.Random) -> list[date]:
        start_date = _parse_date(column.min_value, self.operating_scope.date_start)
        end_date = _parse_date(column.max_value, self.operating_scope.date_end)
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        day_span = (end_date - start_date).days
        return [start_date + timedelta(days=rng.randint(0, day_span)) for _ in range(count)]

    def _choice_values(self, values: list[str], count: int, rng: random.Random) -> list[str]:
        return [values[rng.randrange(len(values))] for _ in range(count)]

    def _current_or_existing_plant_names(self, existing_dataframes: dict[str, pd.DataFrame]) -> list[str] | None:
        for dataframe in existing_dataframes.values():
            for column_name in dataframe.columns:
                if column_name.lower() == "plantname":
                    return list(dataframe[column_name].dropna())
            if any(column.lower() == "plantid" for column in dataframe.columns) and "Description" in dataframe.columns:
                return list(dataframe["Description"].dropna())
        return None

    def _generate_warehouse_names_for_assigned_plants(
        self,
        count: int,
        domain_profile,
        existing_dataframes: dict[str, pd.DataFrame],
        current_table_data: dict[str, list[Any]],
        seed: int | None,
        existing_names: set[str],
    ) -> list[str]:
        plant_lookup = self._plant_id_to_name_lookup(existing_dataframes)
        assigned_plant_ids = current_table_data.get("PlantID")
        if not plant_lookup or not assigned_plant_ids:
            return self.name_generator.generate_warehouse_names(
                count,
                domain_profile,
                plant_names=self._current_or_existing_plant_names(existing_dataframes),
                seed=seed,
                existing_names=existing_names,
            )

        rng = random.Random(seed)
        warehouse_types = self.name_generator._warehouse_types(domain_profile)
        warehouse_types.extend(
            warehouse_type
            for warehouse_type in self.name_generator.fallback_warehouse_types
            if warehouse_type not in warehouse_types
        )
        candidates_by_row: list[list[str]] = []
        for plant_id in assigned_plant_ids:
            plant_name = plant_lookup.get(plant_id)
            base_name = _plant_base_name(plant_name) if plant_name else None
            if not base_name:
                base_name = str(plant_id)
            row_candidates = [f"{base_name} {warehouse_type}" for warehouse_type in warehouse_types]
            rng.shuffle(row_candidates)
            candidates_by_row.append(row_candidates)

        selected: list[str] = []
        seen = set(existing_names)
        max_options = max((len(candidates) for candidates in candidates_by_row), default=0)
        for option_index in range(max_options):
            for row_index, row_candidates in enumerate(candidates_by_row):
                if row_index < len(selected):
                    continue
                if option_index >= len(row_candidates):
                    continue
                candidate = row_candidates[option_index]
                if candidate and candidate not in seen and not ARTIFICIAL_NUMERIC_SUFFIX_PATTERN.search(candidate):
                    selected.append(candidate)
                    seen.add(candidate)
            if len(selected) == count:
                return selected

        raise NameGenerationError(
            f"Unable to generate {count} unique warehouse names aligned to assigned PlantID values. "
            "Increase warehouse type variety or lower the warehouse target count."
        )

    def _plant_id_to_name_lookup(self, existing_dataframes: dict[str, pd.DataFrame]) -> dict[Any, str]:
        for dataframe in existing_dataframes.values():
            plant_id_column = next((column for column in dataframe.columns if column.lower() == "plantid"), None)
            plant_name_column = next((column for column in dataframe.columns if column.lower() == "plantname"), None)
            if plant_id_column and plant_name_column is None and "Description" in dataframe.columns:
                plant_name_column = "Description"
            if plant_id_column and plant_name_column:
                return dict(zip(dataframe[plant_id_column], dataframe[plant_name_column]))
        return {}

    def _validate_fk_column(
        self,
        table: TableContract,
        column: ColumnContract,
        series: pd.Series,
        dataframes: dict[str, pd.DataFrame],
        report: ValidationReport,
    ) -> None:
        parent_df = dataframes.get(column.related_table or "")
        if parent_df is None or not column.related_column or column.related_column not in parent_df.columns:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="FK parent DataFrame or parent column is missing.",
                suggested_fix="Generate FK parent table before validating child FKs.",
            )
            return
        parent_values = set(parent_df[column.related_column].dropna())
        invalid = sorted(set(series.dropna()) - parent_values)
        if invalid:
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message=f"FK contains values not present in parent key: {invalid[:5]}.",
                suggested_fix="Generate FK values from parent key values only.",
            )

    def _validate_numeric_range(
        self,
        table: TableContract,
        column: ColumnContract,
        series: pd.Series,
        report: ValidationReport,
    ) -> None:
        if not is_numeric_type(column.data_type):
            return
        minimum = _parse_number(column.min_value, None)
        maximum = _parse_number(column.max_value, None)
        numeric = pd.to_numeric(series.dropna(), errors="coerce")
        if minimum is not None and (numeric < float(minimum)).any():
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Generated numeric value is below MinValue.",
                suggested_fix="Clamp generated values to metadata MinValue.",
            )
        if maximum is not None and (numeric > float(maximum)).any():
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Generated numeric value is above MaxValue.",
                suggested_fix="Clamp generated values to metadata MaxValue.",
            )

    def _validate_date_range(
        self,
        table: TableContract,
        column: ColumnContract,
        series: pd.Series,
        report: ValidationReport,
    ) -> None:
        if not is_date_type(column.data_type):
            return
        minimum = _parse_date(column.min_value, None)
        maximum = _parse_date(column.max_value, None)
        values = [value for value in series.dropna()]
        if minimum is not None and any(_parse_date(value, minimum) < minimum for value in values):
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Generated date value is before MinValue.",
                suggested_fix="Generate dates within metadata range.",
            )
        if maximum is not None and any(_parse_date(value, maximum) > maximum for value in values):
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Generated date value is after MaxValue.",
                suggested_fix="Generate dates within metadata range.",
            )

    def _validate_name_column(
        self,
        table: TableContract,
        column: ColumnContract,
        series: pd.Series,
        report: ValidationReport,
    ) -> None:
        if not _is_name_like_column(column):
            return
        values = [str(value) for value in series.dropna()]
        if any(_has_artificial_numeric_name_suffix(value) for value in values):
            report.add_error(
                table_name=table.table_name,
                column_name=column.column_name,
                message="Generated name contains an artificial numeric suffix.",
                suggested_fix="Use meaningful unique name combinations instead of numeric suffixes.",
            )
        if column.generation_type in {"vendor_name", "material_name", "plant_name", "warehouse_name"}:
            if len(values) != len(set(values)):
                report.add_error(
                    table_name=table.table_name,
                    column_name=column.column_name,
                    message="Generated name column contains duplicate values.",
                    suggested_fix="Generate unique names for master name columns.",
                )


def _parse_number(value: Any, default: float | int | None) -> float | int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any, default: date | None) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.to_datetime(value).date()
    except (TypeError, ValueError):
        return default


def _decimal_scale(data_type: str) -> int:
    match = re.search(r"\(\s*\d+\s*,\s*(\d+)\s*\)", data_type)
    if match:
        return int(match.group(1))
    return 2


def _plant_base_name(plant_name: str) -> str:
    suffixes = (
        " Manufacturing Plant",
        " Assembly Plant",
        " Component Facility",
        " Production Site",
        " Fabrication Unit",
        " Processing Plant",
        " Operations Facility",
    )
    for suffix in suffixes:
        if plant_name.endswith(suffix):
            return plant_name[: -len(suffix)]
    return plant_name.split()[0] if plant_name.split() else ""


def _warehouse_type_label(value: str) -> str:
    text = str(value).strip()
    suffix = " Warehouse"
    if text.endswith(suffix):
        return text[: -len(suffix)]
    return text


def _is_name_like_column(column: ColumnContract) -> bool:
    normalized_name = re.sub(r"[^a-z0-9]", "", column.column_name.lower())
    if normalized_name in NAME_COLUMN_NAMES:
        return True
    return column.generation_type in NAME_GENERATION_TYPES


def _has_artificial_numeric_name_suffix(value: str) -> bool:
    match = GENERIC_ARTIFICIAL_NAME_SUFFIX_PATTERN.match(str(value).strip())
    if not match:
        return False
    base = " ".join(match.group("base").lower().split())
    compact_base = base.replace(" ", "")
    return base in GENERIC_ARTIFICIAL_NAME_BASES or compact_base in GENERIC_ARTIFICIAL_NAME_BASES


def _format_issue(index: int, table_name: str | None, column_name: str | None, message: str, suggested_fix: str) -> list[str]:
    lines = [f"{index}. Table: {table_name or 'N/A'}"]
    if column_name:
        lines.append(f"   Column: {column_name}")
    lines.append(f"   Message: {message}")
    lines.append(f"   Suggested fix: {suggested_fix}")
    return lines


def format_master_generation_report(
    dataframes: dict[str, pd.DataFrame],
    report: ValidationReport,
    output_folder: str | Path | None = None,
    model_version: str | None = None,
) -> str:
    """Format master generation output for CLI usage."""

    lines = [
        "Master data generation completed.",
    ]
    if model_version is not None:
        lines.append(f"Model version: {model_version}")
    lines.append(f"Tables generated: {len(dataframes)}")
    for table_name, dataframe in dataframes.items():
        lines.append(f"{table_name} rows: {len(dataframe)}")
    lines.extend(
        [
            f"Validation errors: {len(report.errors)}",
            f"Validation warnings: {len(report.warnings)}",
        ]
    )
    if output_folder is not None:
        lines.append(f"Output folder: {output_folder}")
    lines.append(f"Generation status: {'passed' if report.is_valid else 'failed'}")

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for index, issue in enumerate(report.errors, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for index, issue in enumerate(report.warnings, start=1):
            lines.extend(_format_issue(index, issue.table_name, issue.column_name, issue.message, issue.suggested_fix))
    return "\n".join(lines)
