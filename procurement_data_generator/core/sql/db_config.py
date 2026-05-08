"""Database configuration loading for SQL Server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


VALID_IF_TABLE_EXISTS = {"replace", "append", "fail"}


@dataclass(frozen=True)
class DatabaseConfig:
    """Connection and loading options for the local SQL target."""

    server: str = "localhost"
    database: str = "ProcurementMES"
    schema: str = "dbo"
    driver: str = "ODBC Driver 17 for SQL Server"
    trusted_connection: bool = True
    username: str | None = None
    password: str | None = None
    if_table_exists: str = "replace"
    batch_size: int = 1000

    @classmethod
    def from_env(
        cls,
        env_path: str | Path | None = None,
        if_table_exists_override: str | None = None,
    ) -> "DatabaseConfig":
        """Load database config from .env/environment."""

        if env_path is not None:
            load_dotenv(env_path, override=True)
        else:
            load_dotenv()

        if_table_exists = if_table_exists_override or os.getenv("IF_TABLE_EXISTS", "replace")
        if if_table_exists not in VALID_IF_TABLE_EXISTS:
            raise ValueError("IF_TABLE_EXISTS must be one of: replace, append, fail.")

        batch_size_raw = os.getenv("BATCH_SIZE", "1000")
        try:
            batch_size = int(batch_size_raw)
        except ValueError as exc:
            raise ValueError("BATCH_SIZE must be an integer.") from exc
        if batch_size <= 0:
            raise ValueError("BATCH_SIZE must be greater than 0.")

        return cls(
            server=os.getenv("DB_SERVER", "localhost"),
            database=os.getenv("DB_NAME", "ProcurementMES"),
            schema=os.getenv("DB_SCHEMA", "dbo"),
            driver=os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
            trusted_connection=_parse_bool(os.getenv("DB_TRUSTED_CONNECTION", "yes")),
            username=os.getenv("DB_USERNAME") or None,
            password=os.getenv("DB_PASSWORD") or None,
            if_table_exists=if_table_exists,
            batch_size=batch_size,
        )

    def build_pyodbc_connection_string(self) -> str:
        """Build a pyodbc connection string without logging secrets."""

        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={self.server}",
            f"DATABASE={self.database}",
        ]
        if self.trusted_connection:
            parts.append("Trusted_Connection=yes")
        else:
            if not self.username or self.password is None:
                raise ValueError("DB_USERNAME and DB_PASSWORD are required when DB_TRUSTED_CONNECTION=no.")
            parts.extend([f"UID={self.username}", f"PWD={self.password}"])
        return ";".join(parts) + ";"

    def masked_summary(self) -> dict[str, str | int | bool | None]:
        """Return safe config fields for reports/logs."""

        return {
            "server": self.server,
            "database": self.database,
            "schema": self.schema,
            "driver": self.driver,
            "trusted_connection": self.trusted_connection,
            "username": self.username,
            "password": "***" if self.password else None,
            "if_table_exists": self.if_table_exists,
            "batch_size": self.batch_size,
        }


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}
