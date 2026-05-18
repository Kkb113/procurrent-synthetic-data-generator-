"""Dedicated Production v1 pipeline orchestration script."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import SQLServerLoader, save_sql_load_report
from procurement_data_generator.modules.production.data_validator import (
    validate_production_generated_data,
    write_production_quality_reports,
)
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.reconciler_rules import (
    PRODUCTION_MASTER_TABLES,
    PRODUCTION_TABLES,
    PRODUCTION_TRANSACTION_TABLES,
    UPSTREAM_TABLES,
)
from procurement_data_generator.modules.production.role_validator import validate_production_roles
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator


SQLLoaderFactory = Callable[[DatabaseConfig], SQLServerLoader]


@dataclass(frozen=True)
class ProductionPipelineResult:
    """Result summary for a Production pipeline run."""

    run_id: str
    status: str
    seed: int | None
    input_paths: dict[str, str]
    upstream_data_path: str
    generated_table_count: int
    row_counts_by_table: dict[str, int]
    validation_status: str
    validation_error_count: int
    validation_warning_count: int
    output_folders: dict[str, str]
    final_data_csv_count: int
    notes: list[str]
    errors: list[str]
    warnings: list[str]
    sql_load_status: str = "not_run"
    sql_load_report_path: str | None = None


def run_production_pipeline(
    metadata_path: str | Path,
    erd_path: str | Path,
    scenario_path: str | Path,
    plan_path: str | Path,
    upstream_data_path: str | Path,
    output_root: str | Path,
    seed: int | None = None,
    run_id: str | None = None,
    load_sql: bool = False,
    allow_unvalidated_sql_load: bool = False,
    if_table_exists: str = "replace",
    sql_loader_factory: SQLLoaderFactory | None = None,
    operating_scope: OperatingScope | None = None,
    generation_config: GenerationConfig | None = None,
) -> ProductionPipelineResult:
    """Run the dedicated Production v1 pipeline without touching Procurement dispatch."""

    metadata_path = Path(metadata_path)
    erd_path = Path(erd_path)
    scenario_path = Path(scenario_path)
    plan_path = Path(plan_path)
    upstream_data_path = Path(upstream_data_path)
    output_root = Path(output_root)
    run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    operating_scope = operating_scope or DEFAULT_OPERATING_SCOPE
    generation_config = generation_config or GenerationConfig(seed=seed if seed is not None else 42)

    run_folder = output_root / run_id
    master_folder = run_folder / "master_data"
    transaction_folder = run_folder / "transaction_data"
    final_folder = run_folder / "final_data"
    reports_folder = run_folder / "reports"
    metadata_folder = run_folder / "metadata"
    for folder in (master_folder, transaction_folder, final_folder, reports_folder, metadata_folder):
        folder.mkdir(parents=True, exist_ok=True)

    input_paths = {
        "metadata": str(metadata_path),
        "erd": str(erd_path),
        "scenario": str(scenario_path),
        "plan": str(plan_path),
    }
    output_folders = {
        "run": str(run_folder),
        "master_data": str(master_folder),
        "transaction_data": str(transaction_folder),
        "final_data": str(final_folder),
        "reports": str(reports_folder),
        "metadata": str(metadata_folder),
    }
    notes = [
        "Production v1 is a Production Execution module within MES context, not full MES.",
        "Acceptable warnings are inventory-constrained row-count warnings and selective scrap/rework row-count warnings.",
    ]
    errors: list[str] = []
    warnings: list[str] = []

    _copy_inputs(metadata_folder, metadata_path, erd_path, scenario_path, plan_path)
    missing_upstream = _missing_required_upstream_tables(upstream_data_path)
    if missing_upstream:
        errors.append(f"Missing required upstream Procurement tables: {', '.join(missing_upstream)}")
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result

    metadata_result = load_metadata_schema(metadata_path)
    if not metadata_result.report.is_valid or metadata_result.schema is None:
        errors.extend(issue.message for issue in metadata_result.report.errors)
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result
    schema = metadata_result.schema
    notes.extend(f"Metadata validation warning: {issue.message}" for issue in metadata_result.report.warnings)

    role_result = validate_production_roles(schema)
    if not role_result.report.is_valid:
        errors.extend(issue.message for issue in role_result.report.errors)
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result
    notes.extend(f"Role validation warning: {issue.message}" for issue in role_result.report.warnings)

    erd_relationships = _validate_production_erd_file(erd_path, errors, notes)
    if errors:
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result

    plan_result = load_llm_plan_json(plan_path)
    if not plan_result.report.is_valid or plan_result.plan is None:
        errors.extend(issue.message for issue in plan_result.report.errors)
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result
    plan = plan_result.plan

    semantic_plan_result = validate_generation_plan(plan, schema, erd_relationships, model_version="production_v1")
    if not semantic_plan_result.report.is_valid:
        errors.extend(issue.message for issue in semantic_plan_result.report.errors)
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result
    notes.extend(f"Plan validation warning: {issue.message}" for issue in semantic_plan_result.report.warnings)

    master_generator = ProductionMasterDataGenerator(
        operating_scope=operating_scope,
        generation_config=generation_config,
    )
    master_data, master_report = master_generator.generate_master_data(
        schema,
        plan,
        seed=seed,
        upstream_data_folder=upstream_data_path,
    )
    if not master_report.is_valid:
        errors.extend(issue.message for issue in master_report.errors)
    warnings.extend(issue.message for issue in master_report.warnings)
    if errors:
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            {},
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result
    master_generator.export_master_data(master_data, master_folder)

    transaction_generator = ProductionTransactionGenerator(
        operating_scope=operating_scope,
        generation_config=generation_config,
    )
    master_context = transaction_generator.load_master_data(master_folder)
    upstream_context = transaction_generator.load_upstream_data(upstream_data_path, master_context)
    transaction_data, transaction_report = transaction_generator.generate_transaction_data(
        schema,
        plan,
        master_context,
        upstream_context,
        seed=seed,
    )
    if not transaction_report.is_valid:
        errors.extend(issue.message for issue in transaction_report.errors)
    warnings.extend(issue.message for issue in transaction_report.warnings)
    if errors:
        result = _build_result(
            run_id,
            "failed",
            seed,
            input_paths,
            upstream_data_path,
            _row_counts(master_data) | _row_counts(transaction_data),
            "not_run",
            0,
            0,
            output_folders,
            notes,
            errors,
            warnings,
        )
        _write_pipeline_reports(result, reports_folder)
        return result
    transaction_generator.export_transaction_data(transaction_data, transaction_folder)

    _merge_final_data(master_folder, transaction_folder, final_folder)
    quality_result = validate_production_generated_data(schema, master_folder, transaction_folder, upstream_data_path)
    quality_json_path, _quality_md_path = write_production_quality_reports(quality_result, reports_folder)
    errors.extend(f"{issue.check_type}: {issue.message}" for issue in quality_result.errors)
    warnings.extend(f"{issue.check_type}: {issue.message}" for issue in quality_result.warnings)

    all_data = {**master_data, **transaction_data}
    sql_load_status = "skipped"
    sql_load_report_path: str | None = None
    if load_sql:
        sql_report_path, sql_load_status, sql_warnings = _run_sql_load(
            all_data,
            schema,
            quality_json_path,
            reports_folder,
            allow_unvalidated_sql_load,
            if_table_exists,
            sql_loader_factory,
        )
        sql_load_report_path = str(sql_report_path)
        warnings.extend(sql_warnings)
    else:
        notes.append("SQL load skipped.")

    result = _build_result(
        run_id,
        _status_for(len(quality_result.errors), len(warnings)),
        seed,
        input_paths,
        upstream_data_path,
        _row_counts(all_data),
        quality_result.status,
        len(quality_result.errors),
        len(quality_result.warnings),
        output_folders,
        notes,
        errors,
        warnings,
        sql_load_status=sql_load_status,
        sql_load_report_path=sql_load_report_path,
    )
    _write_pipeline_reports(result, reports_folder)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the dedicated Production v1 pipeline.")
    parser.add_argument("--metadata", required=True, help="Path to Production metadata XLSX.")
    parser.add_argument("--erd", required=True, help="Path to Production Mermaid ERD.")
    parser.add_argument("--scenario", required=True, help="Path to Production business scenario TXT.")
    parser.add_argument("--plan", required=True, help="Path to Production plan JSON.")
    parser.add_argument("--upstream-data", required=True, help="Procurement v2 final_data folder.")
    parser.add_argument("--output", required=True, help="Production run output root folder.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic random seed.")
    parser.add_argument("--profile-id", "--industry-profile", dest="profile_id", default=None, help="Industry profile ID, for example ev_manufacturing, generic_mes, or food_manufacturing.")
    parser.add_argument("--run-id", default=None, help="Optional run id. Defaults to timestamp run id.")
    parser.add_argument("--load-sql", default="false", choices=["true", "false"], help="Whether to load Production final data to SQL.")
    parser.add_argument("--allow-unvalidated-sql-load", action="store_true", help="Allow SQL load without a passing quality report.")
    parser.add_argument("--if-table-exists", default="replace", choices=["replace", "append", "fail"], help="SQL table handling mode.")
    args = parser.parse_args()

    result = run_production_pipeline(
        metadata_path=args.metadata,
        erd_path=args.erd,
        scenario_path=args.scenario,
        plan_path=args.plan,
        upstream_data_path=args.upstream_data,
        output_root=args.output,
        seed=args.seed,
        run_id=args.run_id,
        load_sql=args.load_sql == "true",
        allow_unvalidated_sql_load=args.allow_unvalidated_sql_load,
        if_table_exists=args.if_table_exists,
        generation_config=GenerationConfig(seed=args.seed if args.seed is not None else 42, profile_id=args.profile_id),
    )
    print("Production pipeline completed.")
    print(f"Run ID: {result.run_id}")
    print(f"Status: {result.status}")
    print(f"Output folder: {result.output_folders['run']}")
    print(f"Tables generated: {result.generated_table_count}")
    print(f"Final data CSVs: {result.final_data_csv_count}")
    print(f"Validation status: {result.validation_status}")
    print(f"SQL load status: {result.sql_load_status}")
    print(f"Errors: {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Pipeline report: {Path(result.output_folders['reports']) / 'production_pipeline_report.md'}")
    return 0 if result.status in {"passed", "passed_with_warnings"} else 1


def _copy_inputs(output_folder: Path, *paths: Path) -> None:
    for path in paths:
        if path.exists():
            shutil.copy2(path, output_folder / path.name)


def _missing_required_upstream_tables(upstream_data_path: Path) -> list[str]:
    if not upstream_data_path.exists():
        return list(UPSTREAM_TABLES)
    return [table_name for table_name in UPSTREAM_TABLES if not (upstream_data_path / f"{table_name}.csv").exists()]


def _validate_production_erd_file(erd_path: Path, errors: list[str], notes: list[str]):
    if not erd_path.exists():
        errors.append(f"Production ERD file does not exist: {erd_path}")
        return []
    text = erd_path.read_text(encoding="utf-8")
    required_snippets = [
        "ProductionOrderHdr ||--o{ ProductionOrderLine",
        "ProductionOrderLine ||--o{ ProductionMaterialRequirement",
        "ProductionMaterialRequirement ||--o{ MaterialIssueLine",
        "ProductionBatch ||--o{ OperationExecution",
        "FinishedGoodsReceipt ||--o{ ProductionGenealogy",
        "InventoryReceiptDetail ||--o{ ProductionGenealogy",
        "InventoryTransaction ||--o{ ProductionGenealogy",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in text]
    if missing:
        errors.append("Production ERD is missing required lifecycle/integration relationships: " + "; ".join(missing))
    relationships = parse_mermaid_erd_file(erd_path)
    if not relationships:
        errors.append("Production ERD did not contain parseable Mermaid relationships.")
    else:
        notes.append("Production ERD checked with basic lifecycle/integration text checks because it includes cross-module Procurement tables.")
    return relationships


def _merge_final_data(master_folder: Path, transaction_folder: Path, final_folder: Path) -> None:
    for table_name in PRODUCTION_TABLES:
        source_folder = master_folder if table_name in PRODUCTION_MASTER_TABLES else transaction_folder
        shutil.copy2(source_folder / f"{table_name}.csv", final_folder / f"{table_name}.csv")


def _row_counts(dataframes: dict[str, Any]) -> dict[str, int]:
    return {table_name: len(dataframe) for table_name, dataframe in sorted(dataframes.items())}


def _run_sql_load(
    dataframes: dict[str, Any],
    schema,
    quality_report_path: Path,
    reports_folder: Path,
    allow_unvalidated_sql_load: bool,
    if_table_exists: str,
    sql_loader_factory: SQLLoaderFactory | None,
) -> tuple[Path, str, list[str]]:
    config = DatabaseConfig.from_env(if_table_exists_override=if_table_exists)
    loader = (sql_loader_factory or (lambda config: SQLServerLoader(config)))(config)
    sql_report = loader.load_dataset(
        dataframes,
        schema,
        validation_report_path=quality_report_path,
        allow_unvalidated_load=allow_unvalidated_sql_load,
    )
    json_path, _markdown_path = save_sql_load_report(sql_report, reports_folder)
    status = "passed" if sql_report.status == "passed" else "passed_with_warnings"
    warnings = [f"SQL load warning: {warning}" for warning in sql_report.warnings]
    warnings.extend(f"SQL load error: {error}" for error in sql_report.errors)
    return json_path, status, warnings


def _status_for(error_count: int, warning_count: int) -> str:
    if error_count > 0:
        return "failed"
    if warning_count > 0:
        return "passed_with_warnings"
    return "passed"


def _build_result(
    run_id: str,
    status: str,
    seed: int | None,
    input_paths: dict[str, str],
    upstream_data_path: Path,
    row_counts: dict[str, int],
    validation_status: str,
    validation_error_count: int,
    validation_warning_count: int,
    output_folders: dict[str, str],
    notes: list[str],
    errors: list[str],
    warnings: list[str],
    sql_load_status: str = "not_run",
    sql_load_report_path: str | None = None,
) -> ProductionPipelineResult:
    final_data_path = Path(output_folders["final_data"])
    final_csv_count = len(list(final_data_path.glob("*.csv"))) if final_data_path.exists() else 0
    return ProductionPipelineResult(
        run_id=run_id,
        status=status,
        seed=seed,
        input_paths=input_paths,
        upstream_data_path=str(upstream_data_path),
        generated_table_count=len(row_counts),
        row_counts_by_table=row_counts,
        validation_status=validation_status,
        validation_error_count=validation_error_count,
        validation_warning_count=validation_warning_count,
        output_folders=output_folders,
        final_data_csv_count=final_csv_count,
        notes=notes,
        errors=errors,
        warnings=warnings,
        sql_load_status=sql_load_status,
        sql_load_report_path=sql_load_report_path,
    )


def _write_pipeline_reports(result: ProductionPipelineResult, reports_folder: Path) -> tuple[Path, Path]:
    reports_folder.mkdir(parents=True, exist_ok=True)
    json_path = reports_folder / "production_pipeline_report.json"
    md_path = reports_folder / "production_pipeline_report.md"
    payload = asdict(result)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_format_pipeline_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _format_pipeline_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Production v1 Pipeline Report",
        "",
        f"- Run ID: {payload['run_id']}",
        f"- Status: {payload['status']}",
        f"- Seed: {payload['seed']}",
        f"- Validation status: {payload['validation_status']}",
        f"- Validation errors: {payload['validation_error_count']}",
        f"- Validation warnings: {payload['validation_warning_count']}",
        f"- SQL load status: {payload.get('sql_load_status', 'not_run')}",
        f"- Generated table count: {payload['generated_table_count']}",
        f"- Final data CSV count: {payload['final_data_csv_count']}",
        f"- Upstream data: {payload['upstream_data_path']}",
        "",
        "## Output Folders",
    ]
    for key, value in payload["output_folders"].items():
        lines.append(f"- {key}: {value}")
    if payload.get("sql_load_report_path"):
        lines.append(f"- sql_load_report: {payload['sql_load_report_path']}")
    lines.extend(["", "## Row Counts"])
    for table_name, row_count in payload["row_counts_by_table"].items():
        lines.append(f"- {table_name}: {row_count}")
    lines.extend(["", "## Notes"])
    lines.extend(f"- {note}" for note in payload["notes"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in payload["warnings"] or ["None."])
    lines.extend(["", "## Errors"])
    lines.extend(f"- {error}" for error in payload["errors"] or ["None."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
