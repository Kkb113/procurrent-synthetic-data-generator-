"""Validation reporting contracts used across the data generation tool."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field


IssueLevel = Literal["error", "warning"]


class ValidationIssue(BaseModel):
    """A single validation issue found while reading user input."""

    level: IssueLevel
    table_name: Optional[str] = None
    column_name: Optional[str] = None
    message: str
    suggested_fix: str


class ValidationReport(BaseModel):
    """Aggregated validation status for metadata and later pipeline steps."""

    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    total_tables_detected: int = 0
    total_columns_detected: int = 0

    @computed_field
    @property
    def is_valid(self) -> bool:
        """True when no validation errors were found."""

        return len(self.errors) == 0

    def add_error(
        self,
        message: str,
        suggested_fix: str,
        table_name: Optional[str] = None,
        column_name: Optional[str] = None,
    ) -> None:
        """Append an error issue to the report."""

        self.errors.append(
            ValidationIssue(
                level="error",
                table_name=table_name,
                column_name=column_name,
                message=message,
                suggested_fix=suggested_fix,
            )
        )

    def add_warning(
        self,
        message: str,
        suggested_fix: str,
        table_name: Optional[str] = None,
        column_name: Optional[str] = None,
    ) -> None:
        """Append a warning issue to the report."""

        self.warnings.append(
            ValidationIssue(
                level="warning",
                table_name=table_name,
                column_name=column_name,
                message=message,
                suggested_fix=suggested_fix,
            )
        )
