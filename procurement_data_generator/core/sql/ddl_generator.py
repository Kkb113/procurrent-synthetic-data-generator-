"""SQL Server DDL generation from metadata contracts."""

from __future__ import annotations

import re

from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract, TableContract


class SQLDDLGenerator:
    """Generate SQL Server-compatible DDL from metadata."""

    def __init__(self, schema_name: str = "dbo") -> None:
        self.schema_name = schema_name

    def generate_create_schema_sql(self) -> str:
        schema = quote_identifier(self.schema_name)
        return f"IF SCHEMA_ID(N'{self.schema_name}') IS NULL EXEC(N'CREATE SCHEMA {schema}');"

    def generate_create_table_sql(self, table: TableContract) -> str:
        columns = []
        for column in table.columns:
            nullable = "NOT NULL" if column.nullable == "No" else "NULL"
            columns.append(f"    {quote_identifier(column.column_name)} {self.map_metadata_type_to_sql(column.data_type)} {nullable}")
        body = ",\n".join(columns)
        return f"CREATE TABLE {self.qualified_table_name(table.table_name)} (\n{body}\n);"

    def generate_pk_constraint_sql(self, table: TableContract) -> str | None:
        pk_columns = [column.column_name for column in table.columns if column.key_type == "PK"]
        if not pk_columns:
            return None
        columns = ", ".join(quote_identifier(column) for column in pk_columns)
        constraint_name = quote_identifier(f"PK_{table.table_name}")
        return f"ALTER TABLE {self.qualified_table_name(table.table_name)} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({columns});"

    def generate_fk_constraint_sql(self, table: TableContract) -> list[str]:
        statements: list[str] = []
        for column in table.columns:
            if column.key_type != "FK" or not column.related_table or not column.related_column:
                continue
            constraint_name = quote_identifier(f"FK_{table.table_name}_{column.related_table}_{column.column_name}")
            statements.append(
                "ALTER TABLE "
                f"{self.qualified_table_name(table.table_name)} ADD CONSTRAINT {constraint_name} "
                f"FOREIGN KEY ({quote_identifier(column.column_name)}) "
                f"REFERENCES {self.qualified_table_name(column.related_table)} ({quote_identifier(column.related_column)});"
            )
        return statements

    def generate_drop_table_sql(self, table_name: str) -> str:
        return f"IF OBJECT_ID(N'{self.schema_name}.{table_name}', N'U') IS NOT NULL DROP TABLE {self.qualified_table_name(table_name)};"

    def generate_table_exists_sql(self, table_name: str) -> str:
        return f"SELECT 1 WHERE OBJECT_ID(N'{self.schema_name}.{table_name}', N'U') IS NOT NULL;"

    def qualified_table_name(self, table_name: str) -> str:
        return f"{quote_identifier(self.schema_name)}.{quote_identifier(table_name)}"

    def map_metadata_type_to_sql(self, data_type: str) -> str:
        normalized = data_type.strip().lower()
        if normalized in {"int", "integer"}:
            return "INT"
        if normalized == "bigint":
            return "BIGINT"
        if normalized == "smallint":
            return "SMALLINT"
        if normalized == "tinyint":
            return "TINYINT"
        if normalized in {"float", "real", "money"}:
            return normalized.upper()
        if normalized in {"bit", "bool", "boolean"}:
            return "BIT"
        if normalized == "date":
            return "DATE"
        if normalized in {"datetime", "datetime2", "timestamp"}:
            return "DATETIME2"
        if normalized == "text":
            return "NVARCHAR(MAX)"
        if normalized == "string":
            return "NVARCHAR(255)"

        decimal_match = re.fullmatch(r"(decimal|numeric)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", normalized)
        if decimal_match:
            return f"{decimal_match.group(1).upper()}({decimal_match.group(2)},{decimal_match.group(3)})"
        if normalized in {"decimal", "numeric"}:
            return f"{normalized.upper()}(18,2)"

        varchar_match = re.fullmatch(r"(varchar|nvarchar|char|nchar)\s*\(\s*(\d+|max)\s*\)", normalized)
        if varchar_match:
            length = varchar_match.group(2).upper()
            return f"{varchar_match.group(1).upper()}({length})"
        if normalized in {"varchar", "nvarchar", "char", "nchar"}:
            return "NVARCHAR(255)"

        return "NVARCHAR(255)"

    def dependency_order(self, schema: SchemaContract) -> list[TableContract]:
        """Return parent-before-child table order using FK dependencies and ProcessOrder."""

        tables = {table.table_name: table for table in schema.ordered_tables}
        children_by_parent: dict[str, set[str]] = {name: set() for name in tables}
        indegree: dict[str, int] = {name: 0 for name in tables}
        for table in tables.values():
            parents = {column.related_table for column in table.columns if column.key_type == "FK" and column.related_table in tables}
            for parent in parents:
                if table.table_name not in children_by_parent[parent]:
                    children_by_parent[parent].add(table.table_name)
                    indegree[table.table_name] += 1

        order: list[TableContract] = []
        ready = sorted([name for name, degree in indegree.items() if degree == 0], key=lambda name: (tables[name].process_order, name))
        while ready:
            name = ready.pop(0)
            order.append(tables[name])
            for child in sorted(children_by_parent[name], key=lambda item: (tables[item].process_order, item)):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort(key=lambda item: (tables[item].process_order, item))

        if len(order) != len(tables):
            seen = {table.table_name for table in order}
            order.extend(table for table in schema.ordered_tables if table.table_name not in seen)
        return order


def quote_identifier(identifier: str) -> str:
    """Escape an identifier using SQL Server brackets."""

    return "[" + identifier.replace("]", "]]") + "]"
