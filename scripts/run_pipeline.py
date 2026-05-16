"""CLI script for Phase 15 end-to-end backend pipeline orchestration."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the procurement data generation backend pipeline.")
    parser.add_argument("--metadata", required=True, help="Path to metadata XLSX file.")
    parser.add_argument("--erd", required=True, help="Path to Mermaid ERD file.")
    parser.add_argument("--scenario", help="Path to business scenario text file.")
    parser.add_argument("--plan", help="Path to existing LLM generation plan JSON.")
    parser.add_argument("--output", default="output/runs", help="Base output folder for timestamped run folders.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic seed.")
    parser.add_argument("--load-sql", default="false", choices=["true", "false"], help="Whether to run SQL load.")
    parser.add_argument("--allow-unvalidated-sql-load", action="store_true", help="Allow SQL load without a quality report.")
    parser.add_argument("--build-prompt", default="false", choices=["true", "false"], help="Build and save the LLM planning prompt without calling an LLM.")
    parser.add_argument("--generate-plan", default="false", choices=["true", "false"], help="Generate the LLM plan with Azure OpenAI.")
    parser.add_argument("--use-existing-plan", action="store_true", help="Use --plan even when --generate-plan true.")
    parser.add_argument("--raw-llm-output", help="Optional extra path to copy the raw Azure OpenAI response.")
    parser.add_argument("--generated-plan-output", help="Optional extra path to copy the generated plan JSON.")
    parser.add_argument("--if-table-exists", default="replace", choices=["replace", "append", "fail"], help="SQL table handling mode.")
    parser.add_argument("--model-version", default="v2", choices=["v2"], help="Procurement model version for role validation and prompt generation. Procurement v2 is the only active Procurement model.")
    args = parser.parse_args()

    report = ProcurementPipelineRunner().run_pipeline(
        metadata_path=args.metadata,
        erd_path=args.erd,
        scenario_path=args.scenario,
        plan_path=args.plan,
        output_folder=args.output,
        seed=args.seed,
        load_sql=args.load_sql == "true",
        allow_unvalidated_sql_load=args.allow_unvalidated_sql_load,
        build_prompt=args.build_prompt == "true",
        generate_plan=args.generate_plan == "true",
        use_existing_plan=args.use_existing_plan,
        if_table_exists=args.if_table_exists,
        model_version=args.model_version,
    )
    if args.raw_llm_output:
        _copy_if_exists(Path(report.output_folder) / "prompt" / "azure_openai_raw_response.txt", Path(args.raw_llm_output))
    if args.generated_plan_output:
        _copy_if_exists(Path(report.output_folder) / "prompt" / "generated_llm_plan.json", Path(args.generated_plan_output))
    audit_stage = next((stage for stage in report.stages if stage.stage_name == "audit_report"), None)
    audit_path = ""
    if audit_stage and audit_stage.output_paths:
        audit_path = audit_stage.output_paths[-1]
    sql_stage = next((stage for stage in report.stages if stage.stage_name == "sql_load"), None)
    data_quality_stage = next((stage for stage in report.stages if stage.stage_name == "data_quality_validation"), None)

    print("Pipeline completed.")
    print(f"Run ID: {report.run_id}")
    print(f"Status: {report.status}")
    print(f"Output folder: {report.output_folder}")
    print(f"Tables generated: {report.tables_generated}")
    print(f"Total rows generated: {report.total_rows_generated}")
    print(f"Data quality status: {data_quality_stage.status if data_quality_stage else 'not_run'}")
    print(f"SQL load: {sql_stage.status if sql_stage else 'not_run'}")
    print(f"Audit report: {audit_path or 'not_generated'}")
    return 0 if report.status in {"passed", "passed_with_warnings"} else 1


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
