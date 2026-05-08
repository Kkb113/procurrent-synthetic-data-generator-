"""Report contract for SQL table creation and data loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SQLLoadReport:
    """Summary of a SQL load attempt."""

    status: str = "passed"
    tables_created: list[str] = field(default_factory=list)
    tables_loaded: list[str] = field(default_factory=list)
    rows_inserted_by_table: dict[str, int] = field(default_factory=dict)
    pk_constraints_created: list[str] = field(default_factory=list)
    fk_constraints_created: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    @property
    def total_rows_inserted(self) -> int:
        return sum(self.rows_inserted_by_table.values())

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.status = "failed"

    def complete(self) -> None:
        self.completed_at = datetime.now(timezone.utc).isoformat()
        if self.errors:
            self.status = "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "tables_created": self.tables_created,
            "tables_loaded": self.tables_loaded,
            "rows_inserted_by_table": self.rows_inserted_by_table,
            "total_rows_inserted": self.total_rows_inserted,
            "pk_constraints_created": self.pk_constraints_created,
            "fk_constraints_created": self.fk_constraints_created,
            "pk_constraints_created_count": len(self.pk_constraints_created),
            "fk_constraints_created_count": len(self.fk_constraints_created),
            "warnings": self.warnings,
            "errors": self.errors,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
