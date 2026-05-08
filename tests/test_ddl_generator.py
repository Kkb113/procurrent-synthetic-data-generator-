from __future__ import annotations

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract
from procurement_data_generator.core.sql.ddl_generator import SQLDDLGenerator, quote_identifier


def test_int_maps_to_int() -> None:
    assert SQLDDLGenerator().map_metadata_type_to_sql("int") == "INT"


def test_decimal_maps_to_decimal_with_scale() -> None:
    assert SQLDDLGenerator().map_metadata_type_to_sql("decimal(18,2)") == "DECIMAL(18,2)"


def test_varchar_maps_to_varchar_with_length() -> None:
    assert SQLDDLGenerator().map_metadata_type_to_sql("varchar(200)") == "VARCHAR(200)"


def test_string_maps_to_nvarchar_255() -> None:
    assert SQLDDLGenerator().map_metadata_type_to_sql("string") == "NVARCHAR(255)"


def test_nullable_no_creates_not_null() -> None:
    sql = SQLDDLGenerator().generate_create_table_sql(_schema().tables["Vendor"])

    assert "[VendorID] INT NOT NULL" in sql


def test_nullable_yes_creates_null() -> None:
    table = _schema().tables["Vendor"].model_copy(
        update={"columns": [_col("OptionalText", "varchar(50)", "category", "Yes")]}
    )
    sql = SQLDDLGenerator().generate_create_table_sql(table)

    assert "[OptionalText] VARCHAR(50) NULL" in sql


def test_pk_constraint_generated() -> None:
    sql = SQLDDLGenerator().generate_pk_constraint_sql(_schema().tables["Vendor"])

    assert sql == "ALTER TABLE [dbo].[Vendor] ADD CONSTRAINT [PK_Vendor] PRIMARY KEY ([VendorID]);"


def test_fk_constraint_generated() -> None:
    sql = SQLDDLGenerator().generate_fk_constraint_sql(_schema().tables["PurchaseOrderHeader"])[0]

    assert "CONSTRAINT [FK_PurchaseOrderHeader_Vendor_VendorID]" in sql
    assert "FOREIGN KEY ([VendorID]) REFERENCES [dbo].[Vendor] ([VendorID])" in sql


def test_bracket_escaping_works() -> None:
    assert quote_identifier("Bad]Name") == "[Bad]]Name]"


def test_create_table_sql_contains_expected_columns() -> None:
    sql = SQLDDLGenerator().generate_create_table_sql(_schema().tables["PurchaseOrderHeader"])

    assert "CREATE TABLE [dbo].[PurchaseOrderHeader]" in sql
    assert "[PurchaseOrderID] INT NOT NULL" in sql
    assert "[TotalAmount] DECIMAL(18,2) NOT NULL" in sql


def _schema() -> SchemaContract:
    return SchemaContract(
        tables={
            "Vendor": TableContract(
                table_name="Vendor",
                process_order=1,
                area="Master",
                table_role="vendor_dimension",
                target_rows=1,
                columns=[
                    _col("VendorID", "int", "sequence_id", "No", "PK"),
                    _col("VendorName", "varchar(200)", "vendor_name", "No"),
                ],
            ),
            "PurchaseOrderHeader": TableContract(
                table_name="PurchaseOrderHeader",
                process_order=2,
                area="Procurement",
                table_role="purchase_order_header",
                target_rows=1,
                columns=[
                    _col("PurchaseOrderID", "int", "sequence_id", "No", "PK"),
                    _col("VendorID", "int", "foreign_key", "No", "FK", "Vendor", "VendorID"),
                    _col("TotalAmount", "decimal(18,2)", "decimal_range", "No"),
                ],
            ),
        }
    )


def _col(
    column_name: str,
    data_type: str,
    generation_type: str,
    nullable: str,
    key_type: str | None = None,
    related_table: str | None = None,
    related_column: str | None = None,
) -> ColumnContract:
    return ColumnContract(
        column_name=column_name,
        data_type=data_type,
        key_type=key_type,
        related_table=related_table,
        related_column=related_column,
        nullable=nullable,
        generation_type=generation_type,
    )
