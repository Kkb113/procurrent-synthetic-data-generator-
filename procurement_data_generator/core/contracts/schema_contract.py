"""Pydantic contracts for procurement metadata schema input."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Area = Literal["Master", "Procurement", "Production", "Sales", "MES", "Logistics", "Receiving", "Quality", "Inventory", "Finance"]
KeyType = Literal["PK", "FK"]
Nullable = Literal["Yes", "No"]
GenerationType = Literal[
    "sequence_id",
    "foreign_key",
    "vendor_name",
    "material_name",
    "plant_name",
    "warehouse_name",
    "faker_company",
    "faker_person",
    "category",
    "status",
    "integer_range",
    "decimal_range",
    "date_range",
    "date_offset",
    "calculated",
]


class ColumnContract(BaseModel):
    """Metadata contract for one table column."""

    model_config = ConfigDict(extra="forbid")

    column_name: str
    data_type: str
    key_type: Optional[KeyType] = None
    related_table: Optional[str] = None
    related_column: Optional[str] = None
    nullable: Nullable
    generation_type: GenerationType
    allowed_values: list[str] = Field(default_factory=list)
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    formula: Optional[str] = None


class TableContract(BaseModel):
    """Metadata contract for one table and its columns."""

    model_config = ConfigDict(extra="forbid")

    table_name: str
    process_order: int
    area: Area
    table_role: str
    target_rows: int
    columns: list[ColumnContract]


class SchemaContract(BaseModel):
    """Top-level metadata schema contract."""

    model_config = ConfigDict(extra="forbid")

    tables: dict[str, TableContract]

    @property
    def ordered_tables(self) -> list[TableContract]:
        """Tables sorted by configured process order and then table name."""

        return sorted(self.tables.values(), key=lambda table: (table.process_order, table.table_name))
