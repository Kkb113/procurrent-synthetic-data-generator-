"""Report contracts for generated data validation and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataQualityIssue:
    """One validation or reconciliation finding."""

    level: str
    check_type: str
    table_name: str | None
    column_name: str | None
    message: str
    suggested_fix: str
    rule_id: str | None = None
    sample_failed_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "check_type": self.check_type,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "rule_id": self.rule_id,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "sample_failed_rows": self.sample_failed_rows,
        }


@dataclass
class TableQualitySummary:
    """Row and check summary for one table."""

    table_name: str
    row_count: int
    target_rows: int | None = None
    checks_run: int = 0
    errors: int = 0
    warnings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "row_count": self.row_count,
            "target_rows": self.target_rows,
            "checks_run": self.checks_run,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ReconciliationSummary:
    """Summary for one reconciliation check."""

    check_type: str
    status: str
    rows_checked: int = 0
    mismatches: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_type": self.check_type,
            "status": self.status,
            "rows_checked": self.rows_checked,
            "mismatches": self.mismatches,
            "message": self.message,
        }


@dataclass
class DataQualityReport:
    """Final data quality report used before SQL loading."""

    checks_run: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    table_summaries: dict[str, TableQualitySummary] = field(default_factory=dict)
    issues: list[DataQualityIssue] = field(default_factory=list)
    reconciliation_summaries: list[ReconciliationSummary] = field(default_factory=list)

    @property
    def errors(self) -> list[DataQualityIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[DataQualityIssue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def overall_status(self) -> str:
        if self.error_count:
            return "failed"
        if self.warning_count:
            return "passed_with_warnings"
        return "passed"

    def record_check(self, passed: bool = True) -> None:
        self.checks_run += 1
        if passed:
            self.checks_passed += 1
        else:
            self.checks_failed += 1

    def add_issue(
        self,
        level: str,
        check_type: str,
        message: str,
        suggested_fix: str,
        table_name: str | None = None,
        column_name: str | None = None,
        rule_id: str | None = None,
        sample_failed_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.issues.append(
            DataQualityIssue(
                level=level,
                check_type=check_type,
                table_name=table_name,
                column_name=column_name,
                rule_id=rule_id,
                message=message,
                suggested_fix=suggested_fix,
                sample_failed_rows=sample_failed_rows or [],
            )
        )
        if table_name and table_name in self.table_summaries:
            summary = self.table_summaries[table_name]
            if level == "error":
                summary.errors += 1
            elif level == "warning":
                summary.warnings += 1

    def add_reconciliation_summary(self, summary: ReconciliationSummary) -> None:
        self.reconciliation_summaries.append(summary)

    def merge(self, other: "DataQualityReport") -> None:
        self.checks_run += other.checks_run
        self.checks_passed += other.checks_passed
        self.checks_failed += other.checks_failed
        self.issues.extend(other.issues)
        self.reconciliation_summaries.extend(other.reconciliation_summaries)
        for table_name, incoming in other.table_summaries.items():
            if table_name not in self.table_summaries:
                self.table_summaries[table_name] = incoming
            else:
                current = self.table_summaries[table_name]
                current.checks_run += incoming.checks_run
                current.errors += incoming.errors
                current.warnings += incoming.warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "checks_run": self.checks_run,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "table_summaries": {name: summary.to_dict() for name, summary in self.table_summaries.items()},
            "reconciliation_summaries": [summary.to_dict() for summary in self.reconciliation_summaries],
            "issues": [issue.to_dict() for issue in self.issues],
        }
