"""Expected versus actual row-count audit artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from procurement_data_generator.core.contracts.schema_contract import SchemaContract
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema


@dataclass(frozen=True)
class RowCountAuditInput:
    """One module's metadata and generated final-data folder."""

    module_id: str
    metadata_path: str | Path | None
    data_folder: str | Path | None


@dataclass(frozen=True)
class RowCountAuditResult:
    """Generated row-count audit and artifact paths."""

    report: dict[str, Any]
    json_path: Path
    markdown_path: Path


class RowCountAuditBuilder:
    """Build row-count audit JSON and Markdown artifacts."""

    def build_for_schema(
        self,
        *,
        module_id: str,
        schema: SchemaContract,
        actual_counts: Mapping[str, int],
        output_folder: str | Path,
    ) -> RowCountAuditResult:
        """Write an audit report from an already validated schema."""

        report = self._build_report(
            [
                _module_payload(
                    module_id=module_id,
                    schema=schema,
                    actual_counts={str(name): int(count) for name, count in actual_counts.items()},
                    metadata_path=None,
                    data_folder=None,
                )
            ]
        )
        return self._write(report, output_folder)

    def build_for_inputs(
        self,
        inputs: list[RowCountAuditInput] | tuple[RowCountAuditInput, ...],
        output_folder: str | Path,
    ) -> RowCountAuditResult:
        """Write an audit report from module metadata paths and data folders."""

        modules: list[dict[str, Any]] = []
        for audit_input in inputs:
            schema = _load_schema(audit_input.metadata_path)
            actual_counts = _collect_csv_row_counts(audit_input.data_folder)
            modules.append(
                _module_payload(
                    module_id=audit_input.module_id,
                    schema=schema,
                    actual_counts=actual_counts,
                    metadata_path=audit_input.metadata_path,
                    data_folder=audit_input.data_folder,
                )
            )
        return self._write(self._build_report(modules), output_folder)

    def _build_report(self, modules: list[dict[str, Any]]) -> dict[str, Any]:
        totals = {
            "expected_rows": sum(module["summary"]["expected_rows"] for module in modules),
            "actual_rows": sum(module["summary"]["actual_rows"] for module in modules),
            "matched_tables": sum(module["summary"]["matched_tables"] for module in modules),
            "below_target_tables": sum(module["summary"]["below_target_tables"] for module in modules),
            "above_target_tables": sum(module["summary"]["above_target_tables"] for module in modules),
            "missing_tables": sum(module["summary"]["missing_tables"] for module in modules),
            "extra_tables": sum(module["summary"]["extra_tables"] for module in modules),
        }
        totals["delta_rows"] = totals["actual_rows"] - totals["expected_rows"]
        return {
            "report_type": "row_count_audit",
            "modules": modules,
            "summary": totals,
        }

    def _write(self, report: dict[str, Any], output_folder: str | Path) -> RowCountAuditResult:
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        json_path = output_path / "row_count_audit.json"
        markdown_path = output_path / "row_count_audit.md"
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        markdown_path.write_text(render_row_count_audit_markdown(report), encoding="utf-8")
        return RowCountAuditResult(report=report, json_path=json_path, markdown_path=markdown_path)


def render_row_count_audit_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown row-count audit."""

    summary = report.get("summary", {})
    lines = [
        "# Row Count Audit",
        "",
        f"- Expected rows: {summary.get('expected_rows', 0)}",
        f"- Actual rows: {summary.get('actual_rows', 0)}",
        f"- Delta rows: {summary.get('delta_rows', 0)}",
        f"- Matched tables: {summary.get('matched_tables', 0)}",
        f"- Below target tables: {summary.get('below_target_tables', 0)}",
        f"- Above target tables: {summary.get('above_target_tables', 0)}",
        f"- Missing tables: {summary.get('missing_tables', 0)}",
        f"- Extra tables: {summary.get('extra_tables', 0)}",
    ]
    for module in report.get("modules", []):
        lines.extend(
            [
                "",
                f"## {module.get('module_id', 'unknown')}",
                "",
                "| Table | Role | Expected | Actual | Delta | Status |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for table in module.get("tables", []):
            lines.append(
                "| "
                f"{table.get('table_name')} | "
                f"{table.get('table_role') or ''} | "
                f"{_display_count(table.get('expected_rows'))} | "
                f"{_display_count(table.get('actual_rows'))} | "
                f"{_display_count(table.get('delta_rows'))} | "
                f"{table.get('status')} |"
            )
    return "\n".join(lines) + "\n"


def _module_payload(
    *,
    module_id: str,
    schema: SchemaContract | None,
    actual_counts: Mapping[str, int],
    metadata_path: str | Path | None,
    data_folder: str | Path | None,
) -> dict[str, Any]:
    expected = _expected_table_rows(schema)
    table_names = sorted(set(expected) | set(actual_counts))
    tables = [
        _table_payload(
            table_name=table_name,
            expected_rows=expected.get(table_name, {}).get("target_rows"),
            actual_rows=actual_counts.get(table_name),
            table_role=expected.get(table_name, {}).get("table_role"),
            area=expected.get(table_name, {}).get("area"),
        )
        for table_name in table_names
    ]
    summary = _module_summary(tables)
    return {
        "module_id": module_id,
        "metadata_path": str(metadata_path) if metadata_path is not None else None,
        "data_folder": str(data_folder) if data_folder is not None else None,
        "summary": summary,
        "tables": tables,
    }


def _table_payload(
    *,
    table_name: str,
    expected_rows: int | None,
    actual_rows: int | None,
    table_role: str | None,
    area: str | None,
) -> dict[str, Any]:
    if expected_rows is None:
        status = "extra"
        delta_rows = actual_rows
    elif actual_rows is None:
        status = "missing"
        delta_rows = -expected_rows
    else:
        delta_rows = actual_rows - expected_rows
        if delta_rows == 0:
            status = "matched"
        elif delta_rows < 0:
            status = "below_target"
        else:
            status = "above_target"
    return {
        "table_name": table_name,
        "table_role": table_role,
        "area": area,
        "expected_rows": expected_rows,
        "actual_rows": actual_rows,
        "delta_rows": delta_rows,
        "status": status,
    }


def _module_summary(tables: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "expected_rows": sum(int(table["expected_rows"] or 0) for table in tables),
        "actual_rows": sum(int(table["actual_rows"] or 0) for table in tables),
        "matched_tables": _count_status(tables, "matched"),
        "below_target_tables": _count_status(tables, "below_target"),
        "above_target_tables": _count_status(tables, "above_target"),
        "missing_tables": _count_status(tables, "missing"),
        "extra_tables": _count_status(tables, "extra"),
    } | {
        "delta_rows": sum(int(table["actual_rows"] or 0) for table in tables)
        - sum(int(table["expected_rows"] or 0) for table in tables)
    }


def _count_status(tables: list[dict[str, Any]], status: str) -> int:
    return sum(1 for table in tables if table["status"] == status)


def _expected_table_rows(schema: SchemaContract | None) -> dict[str, dict[str, Any]]:
    if schema is None:
        return {}
    return {
        table.table_name: {
            "target_rows": table.target_rows,
            "table_role": table.table_role,
            "area": table.area,
        }
        for table in schema.ordered_tables
    }


def _load_schema(metadata_path: str | Path | None) -> SchemaContract | None:
    if metadata_path is None:
        return None
    result = load_metadata_schema(metadata_path)
    if not result.report.is_valid:
        return None
    return result.schema


def _collect_csv_row_counts(data_folder: str | Path | None) -> dict[str, int]:
    if data_folder is None:
        return {}
    folder = Path(data_folder)
    if not folder.exists():
        return {}
    return {csv_path.stem: len(pd.read_csv(csv_path)) for csv_path in sorted(folder.glob("*.csv"))}


def _display_count(value: Any) -> str:
    return "-" if value is None else str(value)
