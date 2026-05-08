"""End-to-end backend pipeline orchestration for Phase 15."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from procurement_data_generator.core.audit.audit_report import AuditReportBuilder
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport, PipelineStageReport, utc_now_iso
from procurement_data_generator.core.erd.erd_validator import validate_erd_relationships
from procurement_data_generator.core.erd.mermaid_parser import parse_mermaid_erd_file
from procurement_data_generator.core.formulas.formula_engine import SafeFormulaEngine
from procurement_data_generator.core.llm.azure_openai_client import AzureOpenAIClient, AzureOpenAIConfig
from procurement_data_generator.core.llm.llm_client_base import LLMClientBase
from procurement_data_generator.core.llm.plan_loader import load_llm_plan_json
from procurement_data_generator.core.llm.plan_normalizer import normalize_column_generation_dependencies
from procurement_data_generator.core.llm.plan_validator import validate_generation_plan
from procurement_data_generator.core.llm.prompt_builder import build_llm_planning_prompt
from procurement_data_generator.core.metadata.metadata_reader import load_metadata_schema
from procurement_data_generator.core.sql.db_config import DatabaseConfig
from procurement_data_generator.core.sql.sql_loader import SQLServerLoader, save_sql_load_report
from procurement_data_generator.core.validation.reconciler import ProcurementDataQualityEngine
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.role_validator import validate_procurement_roles
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator


SQLLoaderFactory = Callable[[DatabaseConfig], SQLServerLoader]
LLMClientFactory = Callable[[], LLMClientBase]


class ProcurementPipelineRunner:
    """Run all completed backend phases from validated inputs to audit report."""

    def __init__(
        self,
        sql_loader_factory: SQLLoaderFactory | None = None,
        llm_client_factory: LLMClientFactory | None = None,
    ) -> None:
        self.sql_loader_factory = sql_loader_factory or (lambda config: SQLServerLoader(config))
        self.llm_client_factory = llm_client_factory or (
            lambda: AzureOpenAIClient(AzureOpenAIConfig.from_env())
        )

    def run_pipeline(
        self,
        metadata_path: str,
        erd_path: str,
        scenario_path: str | None,
        plan_path: str | None,
        output_folder: str,
        seed: int | None = None,
        load_sql: bool = False,
        allow_unvalidated_sql_load: bool = False,
        build_prompt: bool = False,
        generate_plan: bool = False,
        use_existing_plan: bool = False,
        if_table_exists: str = "replace",
        model_version: str = "v1",
    ) -> PipelineRunReport:
        run_folder = self.create_run_folder(output_folder)
        report = PipelineRunReport(
            run_id=run_folder.name,
            started_at=utc_now_iso(),
            input_files={
                "metadata": metadata_path,
                "erd": erd_path,
                "scenario": scenario_path,
                "plan": plan_path,
                "load_sql": load_sql,
                "build_prompt": build_prompt,
                "generate_plan": generate_plan,
                "model_version": model_version,
            },
            output_folder=str(run_folder),
            model_version=model_version,
        )
        self._create_subfolders(run_folder)

        schema = None
        relationships = []
        plan = None
        master_data: dict[str, pd.DataFrame] = {}
        transaction_data: dict[str, pd.DataFrame] = {}
        formula_data: dict[str, pd.DataFrame] = {}
        final_data: dict[str, pd.DataFrame] = {}
        data_quality_path: Path | None = None
        sql_report_path: Path | None = None
        active_plan_path: str | None = plan_path

        try:
            if generate_plan and plan_path and not use_existing_plan:
                return self._fail(
                    report,
                    "plan_source",
                    "Both generate_plan and plan_path were provided. Use one plan source per run.",
                    run_folder,
                )
            if not generate_plan and not plan_path:
                return self._fail(report, "plan_source", "A plan path is required when generate_plan is false.", run_folder)

            metadata_result = load_metadata_schema(metadata_path)
            self._stage_from_validation_report(
                report,
                "metadata_validation",
                metadata_result.report,
                run_folder / "metadata" / "metadata_validation_report.json",
                "Metadata validation completed.",
            )
            if not metadata_result.report.is_valid or metadata_result.schema is None:
                return self._fail(report, "metadata_validation", "Metadata validation failed.", run_folder)
            schema = metadata_result.schema
            report.expected_tables = [table.table_name for table in schema.ordered_tables]

            role_result = validate_procurement_roles(schema, model_version=model_version)
            self._stage_from_validation_report(
                report,
                "role_validation",
                role_result.report,
                run_folder / "metadata" / "role_validation_report.json",
                "Procurement role validation completed.",
            )
            if not role_result.report.is_valid:
                return self._fail(report, "role_validation", "Procurement role validation failed.", run_folder)

            relationships = parse_mermaid_erd_file(erd_path)
            erd_result = validate_erd_relationships(schema, relationships)
            self._stage_from_validation_report(
                report,
                "erd_validation",
                erd_result.report,
                run_folder / "metadata" / "erd_validation_report.json",
                "ERD validation completed.",
                extra={"summary": erd_result.summary.__dict__},
            )
            if not erd_result.report.is_valid:
                return self._fail(report, "erd_validation", "ERD validation failed.", run_folder)

            if generate_plan and not use_existing_plan:
                if not scenario_path:
                    return self._fail(report, "prompt_building", "Scenario path is required when generate_plan is true.", run_folder)
                prompt_text = self._run_prompt_stage(report, schema, relationships, scenario_path, run_folder, model_version)
                if self._last_stage_failed(report):
                    return self._fail(report, "prompt_building", "Prompt building failed.", run_folder)
                generated_plan_path = self._run_llm_plan_generation(report, prompt_text, run_folder)
                if self._last_stage_failed(report) or generated_plan_path is None:
                    return self._fail(report, "llm_plan_generation", "Azure OpenAI plan generation failed.", run_folder)
                active_plan_path = str(generated_plan_path)
            elif build_prompt:
                self._run_prompt_stage(report, schema, relationships, scenario_path, run_folder, model_version)
            else:
                self._skipped_stage(report, "prompt_building", "Prompt building skipped.")

            plan_result = load_llm_plan_json(active_plan_path)
            self._stage_from_validation_report(
                report,
                "plan_shape_validation",
                plan_result.report,
                run_folder / "metadata" / "plan_shape_validation_report.json",
                "LLM plan JSON shape validation completed.",
            )
            if not plan_result.report.is_valid or plan_result.plan is None:
                return self._fail(report, "plan_shape_validation", "Plan shape validation failed.", run_folder)
            plan = plan_result.plan

            if generate_plan and not use_existing_plan:
                plan, active_plan_path = self._run_plan_normalization(report, plan, schema, run_folder)
            else:
                self._skipped_stage(report, "plan_normalization", "Plan normalization skipped for existing plan mode.")

            plan_validation_result = validate_generation_plan(plan, schema, relationships, model_version=model_version)
            self._stage_from_validation_report(
                report,
                "plan_semantic_validation",
                plan_validation_result.report,
                run_folder / "metadata" / "plan_validation_report.json",
                "LLM plan semantic validation completed.",
                extra={"summary": plan_validation_result.summary.__dict__},
            )
            if not plan_validation_result.report.is_valid:
                return self._fail(report, "plan_semantic_validation", "Plan semantic validation failed.", run_folder)

            master_data = self._run_master_generation(report, schema, plan, seed, run_folder, model_version)
            if self._last_stage_failed(report):
                return self._fail(report, "master_generation", "Master data generation failed.", run_folder)

            transaction_data = self._run_transaction_generation(report, schema, plan, master_data, seed, run_folder, model_version)
            if self._last_stage_failed(report):
                return self._fail(report, "transaction_generation", "Transaction data generation failed.", run_folder)

            formula_data = self._run_formula_execution(report, {**master_data, **transaction_data}, schema, plan, run_folder)
            if self._last_stage_failed(report):
                return self._fail(report, "formula_execution", "Formula execution failed.", run_folder)

            final_data = self._run_final_data_merge(report, master_data, transaction_data, formula_data, run_folder)
            report.tables_generated = len(final_data)
            report.total_rows_generated = sum(len(dataframe) for dataframe in final_data.values())

            data_quality_path = self._run_data_quality_validation(report, final_data, schema, plan, run_folder, model_version)
            data_quality_report = json.loads(data_quality_path.read_text(encoding="utf-8"))
            report.data_quality_status = data_quality_report.get("overall_status", "not_run")
            if data_quality_report.get("overall_status") == "failed":
                return self._fail(report, "data_quality_validation", "Data quality validation failed.", run_folder)

            if load_sql:
                sql_report_path = self._run_sql_load(report, final_data, schema, data_quality_path, allow_unvalidated_sql_load, if_table_exists, run_folder)
            else:
                self._skipped_stage(report, "sql_load", "SQL load skipped.")
                report.sql_load_status = "skipped"

            self._run_audit_report(report, metadata_path, erd_path, scenario_path, active_plan_path, data_quality_path, sql_report_path, run_folder, model_version)
            final_status = self._determine_status(report, data_quality_report)
            report.complete(final_status)
            self.save_pipeline_report(report, run_folder)
            return report
        except Exception as exc:
            report.errors.append(str(exc))
            report.complete("failed")
            self.save_pipeline_report(report, run_folder)
            return report

    def create_run_folder(self, output_folder: str) -> Path:
        base = Path(output_folder)
        base.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_folder = base / f"run_{timestamp}"
        run_folder.mkdir(parents=True, exist_ok=False)
        return run_folder

    def save_pipeline_report(self, report: PipelineRunReport, run_folder: Path) -> tuple[Path, Path]:
        reports_folder = run_folder / "reports"
        reports_folder.mkdir(parents=True, exist_ok=True)
        json_path = reports_folder / "pipeline_run_report.json"
        markdown_path = reports_folder / "pipeline_run_report.md"
        json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        markdown_path.write_text(self._pipeline_markdown(report), encoding="utf-8")
        return json_path, markdown_path

    def _run_prompt_stage(self, report, schema, relationships, scenario_path, run_folder, model_version: str = "v1") -> str:
        stage = PipelineStageReport("prompt_building")
        report.add_stage(stage)
        stage.start()
        try:
            scenario = Path(scenario_path).read_text(encoding="utf-8") if scenario_path and Path(scenario_path).exists() else ""
            prompt = build_llm_planning_prompt(schema, relationships, scenario, model_version=model_version)
            output_path = run_folder / "prompt" / "llm_planning_prompt.txt"
            output_path.write_text(prompt, encoding="utf-8")
            stage.finish("passed", "LLM planning prompt built.", output_paths=[str(output_path)])
            return prompt
        except Exception as exc:
            stage.finish("failed", f"Prompt building failed: {exc}", errors_count=1)
            return ""

    def _run_llm_plan_generation(self, report, prompt: str, run_folder: Path) -> Path | None:
        stage = PipelineStageReport("llm_plan_generation")
        report.add_stage(stage)
        stage.start()
        raw_path = run_folder / "prompt" / "azure_openai_raw_response.txt"
        plan_path = run_folder / "prompt" / "generated_llm_plan.json"
        response_report_path = run_folder / "reports" / "llm_response_report.json"
        try:
            llm_client = self.llm_client_factory()
            llm_response = llm_client.generate_plan(prompt)
            raw_path.write_text(llm_response.raw_text or "", encoding="utf-8")
            response_report_path.write_text(json.dumps(llm_response.to_dict(), indent=2, default=str), encoding="utf-8")
            if llm_response.status != "passed" or llm_response.parsed_json is None:
                stage.finish(
                    "failed",
                    llm_response.error_message or "LLM response did not contain valid plan JSON.",
                    errors_count=1,
                    warnings_count=len(llm_response.warnings),
                    output_paths=[str(raw_path), str(response_report_path)],
                )
                return None
            plan_path.write_text(
                llm_response.extracted_json_text or json.dumps(llm_response.parsed_json, indent=2),
                encoding="utf-8",
            )
            stage.finish(
                "passed_with_warnings" if llm_response.warnings else "passed",
                "Azure OpenAI plan JSON generated and extracted.",
                warnings_count=len(llm_response.warnings),
                output_paths=[str(raw_path), str(plan_path), str(response_report_path)],
            )
            return plan_path
        except Exception as exc:
            response_report_path.write_text(
                json.dumps(
                    {
                        "provider": "Azure OpenAI",
                        "status": "failed",
                        "error_message": str(exc),
                        "raw_response_path": str(raw_path),
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            stage.finish("failed", f"Azure OpenAI plan generation failed: {exc}", errors_count=1, output_paths=[str(response_report_path)])
            return None

    def _run_plan_normalization(self, report, plan, schema, run_folder) -> tuple[Any, str]:
        stage = PipelineStageReport("plan_normalization")
        report.add_stage(stage)
        stage.start()
        result = normalize_column_generation_dependencies(plan, schema)
        normalized_path = run_folder / "prompt" / "generated_llm_plan_normalized.json"
        report_path = run_folder / "metadata" / "plan_normalization_report.json"
        normalized_path.write_text(json.dumps(result.plan.model_dump(mode="json"), indent=2, default=str), encoding="utf-8")
        payload = {
            "warnings": [warning.to_dict() for warning in result.warnings],
            "warnings_count": len(result.warnings),
            "changed": result.changed,
        }
        report_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        if result.warnings:
            warning_text = [
                (
                    f"Table: {warning.table_name}\n"
                    f"Column: {warning.column_name}\n"
                    f"Removed dependency: {warning.removed_dependency}\n"
                    f"Message: {warning.message}"
                )
                for warning in result.warnings
            ]
            report.warnings.extend(warning_text)
        stage.finish(
            "passed_with_warnings" if result.warnings else "passed",
            f"Plan normalization removed {len(result.warnings)} invalid depends_on_columns references.",
            errors_count=0,
            warnings_count=len(result.warnings),
            output_paths=[str(normalized_path), str(report_path)],
        )
        return result.plan, str(normalized_path)

    def _run_master_generation(self, report, schema, plan, seed, run_folder, model_version: str = "v1") -> dict[str, pd.DataFrame]:
        stage = PipelineStageReport("master_generation")
        report.add_stage(stage)
        stage.start()
        generator = ProcurementMasterDataGenerator()
        try:
            dataframes, validation_report = generator.generate_master_data(schema, plan, seed=seed, model_version=model_version)
        except TypeError:
            dataframes, validation_report = generator.generate_master_data(schema, plan, seed=seed)
        self._export_dataframes(dataframes, run_folder / "master_data")
        status = "failed" if not validation_report.is_valid else "passed_with_warnings" if validation_report.warnings else "passed"
        message = "Master data generation completed."
        output_paths = [str(run_folder / "master_data")]
        if validation_report.errors or validation_report.warnings:
            report_path = run_folder / "reports" / "master_generation_report.json"
            report_path.write_text(json.dumps(validation_report.model_dump(mode="json"), indent=2, default=str), encoding="utf-8")
            output_paths.append(str(report_path))
        if validation_report.errors:
            detailed_errors = self._format_validation_issues(validation_report.errors)
            report.errors.extend(detailed_errors)
            message = "\n".join([message, *detailed_errors])
        stage.finish(status, message, len(validation_report.errors), len(validation_report.warnings), output_paths)
        return dataframes

    def _run_transaction_generation(self, report, schema, plan, master_data, seed, run_folder, model_version: str = "v1") -> dict[str, pd.DataFrame]:
        stage = PipelineStageReport("transaction_generation")
        report.add_stage(stage)
        stage.start()
        generator = ProcurementTransactionGenerator()
        try:
            dataframes, validation_report = generator.generate_transaction_data(schema, plan, master_data, seed=seed, model_version=model_version)
        except TypeError:
            dataframes, validation_report = generator.generate_transaction_data(schema, plan, master_data, seed=seed)
        self._export_dataframes(dataframes, run_folder / "transaction_data")
        status = "failed" if not validation_report.is_valid else "passed_with_warnings" if validation_report.warnings else "passed"
        stage.finish(status, "Transaction data generation completed.", len(validation_report.errors), len(validation_report.warnings), [str(run_folder / "transaction_data")])
        return dataframes

    def _run_formula_execution(self, report, dataframes, schema, plan, run_folder) -> dict[str, pd.DataFrame]:
        stage = PipelineStageReport("formula_execution")
        report.add_stage(stage)
        stage.start()
        updated, formula_report = SafeFormulaEngine().execute_formulas(dataframes, plan, schema)
        self._export_dataframes(updated, run_folder / "formula_data")
        report_path = run_folder / "reports" / "formula_execution_report.json"
        report_path.write_text(json.dumps(self._formula_report_dict(formula_report), indent=2, default=str), encoding="utf-8")
        status = "failed" if formula_report.failed_count else "passed_with_warnings" if formula_report.warning_count or formula_report.skipped_count else "passed"
        stage.finish(status, "Formula execution completed.", formula_report.failed_count, formula_report.warning_count, [str(run_folder / "formula_data"), str(report_path)])
        return updated

    def _run_final_data_merge(self, report, master_data, transaction_data, formula_data, run_folder) -> dict[str, pd.DataFrame]:
        stage = PipelineStageReport("final_data_merge")
        report.add_stage(stage)
        stage.start()
        final_data = {**master_data, **transaction_data, **formula_data}
        self._export_dataframes(final_data, run_folder / "final_data")
        report.final_data_tables = sorted(final_data)
        stage.finish("passed", "Final data merged using master -> transaction -> formula override order.", output_paths=[str(run_folder / "final_data")])
        return final_data

    def _run_data_quality_validation(self, report, final_data, schema, plan, run_folder, model_version: str = "v1") -> Path:
        stage = PipelineStageReport("data_quality_validation")
        report.add_stage(stage)
        stage.start()
        engine = ProcurementDataQualityEngine()
        try:
            quality_report = engine.validate_and_reconcile(final_data, schema, plan, model_version=model_version)
        except TypeError:
            quality_report = engine.validate_and_reconcile(final_data, schema, plan)
        json_path = run_folder / "reports" / "data_quality_report.json"
        markdown_path = run_folder / "reports" / "data_quality_report.md"
        json_path.write_text(json.dumps(quality_report.to_dict(), indent=2, default=str), encoding="utf-8")
        markdown_path.write_text(self._data_quality_markdown(quality_report), encoding="utf-8")
        status = "failed" if quality_report.overall_status == "failed" else quality_report.overall_status
        report.data_quality_status = quality_report.overall_status
        message = "Final data quality validation completed."
        if quality_report.errors:
            detailed_errors = self._format_data_quality_issues(quality_report.errors)
            report.errors.extend(detailed_errors)
            message = "\n".join([message, *detailed_errors])
        stage.finish(status, message, quality_report.error_count, quality_report.warning_count, [str(json_path), str(markdown_path)])
        return json_path

    def _run_sql_load(self, report, final_data, schema, data_quality_path, allow_unvalidated_sql_load, if_table_exists, run_folder) -> Path:
        stage = PipelineStageReport("sql_load")
        report.add_stage(stage)
        stage.start()
        config = DatabaseConfig.from_env(if_table_exists_override=if_table_exists)
        loader = self.sql_loader_factory(config)
        sql_report = loader.load_dataset(final_data, schema, validation_report_path=data_quality_path, allow_unvalidated_load=allow_unvalidated_sql_load)
        json_path, markdown_path = save_sql_load_report(sql_report, run_folder / "reports")
        status = "passed" if sql_report.status == "passed" else "passed_with_warnings"
        report.sql_load_status = status
        stage.finish(status, "SQL load attempted.", len(sql_report.errors), len(sql_report.warnings), [str(json_path), str(markdown_path)])
        if sql_report.errors:
            report.warnings.extend(sql_report.errors)
        return json_path

    def _run_audit_report(self, report, metadata_path, erd_path, scenario_path, plan_path, data_quality_path, sql_report_path, run_folder, model_version: str = "v1") -> None:
        stage = PipelineStageReport("audit_report")
        report.add_stage(stage)
        stage.start()
        result = AuditReportBuilder().build_audit_report(
            metadata_path=metadata_path,
            erd_path=erd_path,
            scenario_path=scenario_path,
            llm_plan_path=plan_path,
            data_quality_report_path=str(data_quality_path),
            sql_load_report_path=str(sql_report_path) if sql_report_path else None,
            data_folders=[str(run_folder / "final_data")],
            formula_report_path=str(run_folder / "reports" / "formula_execution_report.json"),
            output_folder=str(run_folder / "reports"),
            model_version=model_version,
        )
        report.audit_report_path = str(result.markdown_path)
        stage.finish("passed", "Audit report generated.", output_paths=[str(result.json_path), str(result.markdown_path)])

    def _stage_from_validation_report(self, pipeline_report, name, validation_report, output_path, message, extra=None) -> None:
        stage = PipelineStageReport(name)
        pipeline_report.add_stage(stage)
        stage.start()
        payload = validation_report.model_dump(mode="json")
        if extra:
            payload.update(extra)
        output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        status = "failed" if not validation_report.is_valid else "passed_with_warnings" if validation_report.warnings else "passed"
        stage.finish(status, message, len(validation_report.errors), len(validation_report.warnings), [str(output_path)])

    def _skipped_stage(self, report: PipelineRunReport, stage_name: str, message: str) -> None:
        stage = PipelineStageReport(stage_name)
        report.add_stage(stage)
        stage.start()
        stage.finish("skipped", message)

    def _fail(self, report: PipelineRunReport, stage_name: str, message: str, run_folder: Path) -> PipelineRunReport:
        report.errors.append(message)
        report.current_stage = stage_name
        report.complete("failed")
        self.save_pipeline_report(report, run_folder)
        return report

    def _determine_status(self, report: PipelineRunReport, data_quality_report: dict[str, Any]) -> str:
        if report.errors:
            return "failed"
        if data_quality_report.get("overall_status") == "passed_with_warnings" or report.warnings:
            return "passed_with_warnings"
        if any(stage.status == "passed_with_warnings" for stage in report.stages):
            return "passed_with_warnings"
        return "passed"

    def _last_stage_failed(self, report: PipelineRunReport) -> bool:
        return bool(report.stages and report.stages[-1].status == "failed")

    def _export_dataframes(self, dataframes: dict[str, pd.DataFrame], folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for table_name, dataframe in dataframes.items():
            dataframe.to_csv(folder / f"{table_name}.csv", index=False)

    def _create_subfolders(self, run_folder: Path) -> None:
        for name in ["metadata", "prompt", "master_data", "transaction_data", "formula_data", "final_data", "reports"]:
            (run_folder / name).mkdir(parents=True, exist_ok=True)

    def _formula_report_dict(self, formula_report) -> dict[str, Any]:
        return {
            "total_rules": formula_report.total_rules,
            "applied_count": formula_report.applied_count,
            "skipped_count": formula_report.skipped_count,
            "failed_count": formula_report.failed_count,
            "warning_count": formula_report.warning_count,
            "error_count": formula_report.error_count,
            "status": formula_report.status,
            "results": [result.__dict__ for result in formula_report.results],
        }

    def _format_validation_issues(self, issues) -> list[str]:
        formatted = []
        for issue in issues:
            parts = []
            if issue.table_name:
                parts.append(f"Table: {issue.table_name}")
            if issue.column_name:
                parts.append(f"Column: {issue.column_name}")
            parts.append(f"Message: {issue.message}")
            parts.append(f"Suggested fix: {issue.suggested_fix}")
            formatted.append("\n".join(parts))
        return formatted

    def _format_data_quality_issues(self, issues) -> list[str]:
        formatted = []
        for issue in issues:
            parts = [f"Check: {issue.check_type}"]
            if issue.table_name:
                parts.append(f"Table: {issue.table_name}")
            if issue.column_name:
                parts.append(f"Column: {issue.column_name}")
            parts.append(f"Message: {issue.message}")
            parts.append(f"Suggested fix: {issue.suggested_fix}")
            formatted.append("\n".join(parts))
        return formatted

    def _data_quality_markdown(self, quality_report) -> str:
        lines = [
            "# Data Quality Report",
            "",
            f"- Overall status: {quality_report.overall_status}",
            f"- Checks run: {quality_report.checks_run}",
            f"- Checks passed: {quality_report.checks_passed}",
            f"- Checks failed: {quality_report.checks_failed}",
            f"- Errors: {quality_report.error_count}",
            f"- Warnings: {quality_report.warning_count}",
        ]
        return "\n".join(lines)

    def _pipeline_markdown(self, report: PipelineRunReport) -> str:
        lines = [
            "# Pipeline Run Report",
            "",
            f"- Run ID: {report.run_id}",
            f"- Status: {report.status}",
            f"- Model version: {report.model_version}",
            f"- Output folder: {report.output_folder}",
            f"- Tables generated: {report.tables_generated}",
            f"- Total rows generated: {report.total_rows_generated}",
            f"- Data quality status: {report.data_quality_status}",
            f"- SQL load status: {report.sql_load_status}",
            f"- Audit report: {report.audit_report_path or 'not_generated'}",
            "",
            "## Stages",
            "",
            "| Stage | Status | Errors | Warnings | Duration seconds |",
            "|---|---|---:|---:|---:|",
        ]
        for stage in report.stages:
            lines.append(f"| {stage.stage_name} | {stage.status} | {stage.errors_count} | {stage.warnings_count} | {stage.duration_seconds} |")
        return "\n".join(lines)
