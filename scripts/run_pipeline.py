"""CLI entry point for generic MES synthetic data pipeline runs."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.config import GenerationConfig
from procurement_data_generator.core.pipeline.generic_runner import (
    GenericPipelineRunResult,
    ModulePipelineInput,
    PipelineRunSpec,
    SyntheticDataPipelineRunner,
)
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport


DEFAULT_INPUTS = {
    "procurement": ModulePipelineInput(
        metadata_path=str(PROJECT_ROOT / "input" / "procurement_v2_metadata.xlsx"),
        erd_path=str(PROJECT_ROOT / "input" / "procurement_v2_erd.mmd"),
        scenario_path=str(PROJECT_ROOT / "input" / "procurement_v2_business_scenario.txt"),
        plan_path=str(PROJECT_ROOT / "input" / "sample_generation_plan_v2_valid.json"),
        model_version="v2",
    ),
    "production": ModulePipelineInput(
        metadata_path=str(PROJECT_ROOT / "input" / "production_v1_metadata.xlsx"),
        erd_path=str(PROJECT_ROOT / "input" / "production_v1_erd.mmd"),
        scenario_path=str(PROJECT_ROOT / "input" / "production_v1_business_scenario.txt"),
        plan_path=str(PROJECT_ROOT / "input" / "sample_generation_plan_production_v1_valid.json"),
        model_version="production_v1",
    ),
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        modules = _parse_modules(args.modules)
        result = _run(args, modules)
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 2

    _copy_optional_llm_artifacts(result, args)
    _print_summary(result, modules, args)
    return 0 if result.status in {"passed", "passed_with_warnings"} else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MES synthetic data generation pipeline.")
    parser.add_argument("--modules", default="procurement", help="Comma-separated modules, for example procurement or procurement,production.")
    parser.add_argument("--metadata", help="Path to Procurement metadata XLSX. Defaults to bundled Procurement v2 metadata.")
    parser.add_argument("--erd", help="Path to Procurement Mermaid ERD. Defaults to bundled Procurement v2 ERD.")
    parser.add_argument("--scenario", help="Path to Procurement business scenario text. Defaults to bundled Procurement scenario.")
    parser.add_argument("--plan", help="Path to Procurement plan JSON. Defaults to bundled Procurement sample plan.")
    parser.add_argument("--production-metadata", help="Path to Production metadata XLSX. Defaults to bundled Production v1 metadata.")
    parser.add_argument("--production-erd", help="Path to Production Mermaid ERD. Defaults to bundled Production v1 ERD.")
    parser.add_argument("--production-scenario", help="Path to Production business scenario text. Defaults to bundled Production scenario.")
    parser.add_argument("--production-plan", help="Path to Production plan JSON. Defaults to bundled Production sample plan.")
    parser.add_argument("--upstream-data", help="Existing Procurement final_data folder for Production-only or custom Production runs.")
    parser.add_argument("--output", "--output-dir", dest="output", default="output/runs", help="Base output folder.")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic seed.")
    parser.add_argument("--profile-id", "--industry-profile", dest="profile_id", default=None, help="Industry profile ID, for example ev_manufacturing, generic_mes, or food_manufacturing.")
    parser.add_argument("--allow-demo-fallback", action="store_true", help="Allow explicit Production demo fallback when upstream Procurement data is absent.")
    parser.add_argument("--load-sql", default="false", choices=["true", "false"], help="Whether to run SQL load for Procurement.")
    parser.add_argument("--allow-unvalidated-sql-load", action="store_true", help="Allow SQL load without a quality report.")
    parser.add_argument("--build-prompt", default="false", choices=["true", "false"], help="Build and save the LLM planning prompt without calling an LLM.")
    parser.add_argument("--generate-plan", default="false", choices=["true", "false"], help="Generate the Procurement LLM plan with Azure OpenAI.")
    parser.add_argument("--use-existing-plan", action="store_true", help="Use --plan even when --generate-plan true.")
    parser.add_argument("--raw-llm-output", help="Optional extra path to copy the raw Azure OpenAI response.")
    parser.add_argument("--generated-plan-output", help="Optional extra path to copy the generated plan JSON.")
    parser.add_argument("--if-table-exists", default="replace", choices=["replace", "append", "fail"], help="SQL table handling mode.")
    parser.add_argument("--model-version", default="v2", choices=["v2"], help="Procurement model version. Procurement v2 is the only active Procurement model.")
    return parser


def _run(args: argparse.Namespace, modules: tuple[str, ...]) -> PipelineRunReport | GenericPipelineRunResult:
    generation_config = GenerationConfig(
        seed=args.seed if args.seed is not None else 42,
        allow_demo_fallback=args.allow_demo_fallback,
        profile_id=args.profile_id,
    )
    runner = SyntheticDataPipelineRunner(generation_config=generation_config)
    runner.resolve_modules(modules)

    if modules == ("procurement",):
        procurement = _procurement_input(args)
        return runner.run_pipeline(
            module_id="procurement",
            metadata_path=procurement.metadata_path,
            erd_path=procurement.erd_path,
            scenario_path=procurement.scenario_path,
            plan_path=procurement.plan_path,
            output_folder=args.output,
            seed=args.seed,
            load_sql=args.load_sql == "true",
            allow_unvalidated_sql_load=args.allow_unvalidated_sql_load,
            build_prompt=args.build_prompt == "true",
            generate_plan=args.generate_plan == "true",
            use_existing_plan=args.use_existing_plan,
            if_table_exists=args.if_table_exists,
            model_version=args.model_version,
            generation_config=generation_config,
        )

    module_inputs = {
        "procurement": _procurement_input(args),
        "production": _production_input(args),
    }
    known_inputs = {module_id: module_inputs[module_id] for module_id in modules if module_id in module_inputs}
    spec = PipelineRunSpec(
        module_ids=modules,
        metadata_path=known_inputs[modules[0]].metadata_path,
        erd_path=known_inputs[modules[0]].erd_path,
        scenario_path=known_inputs[modules[0]].scenario_path,
        plan_path=known_inputs[modules[0]].plan_path,
        output_folder=args.output,
        seed=args.seed,
        load_sql=args.load_sql == "true",
        allow_unvalidated_sql_load=args.allow_unvalidated_sql_load,
        build_prompt=args.build_prompt == "true",
        generate_plan=args.generate_plan == "true",
        use_existing_plan=args.use_existing_plan,
        if_table_exists=args.if_table_exists,
        model_version=args.model_version,
        generation_config=generation_config,
        module_inputs=known_inputs,
    )
    return runner.run(spec)


def _procurement_input(args: argparse.Namespace) -> ModulePipelineInput:
    default = DEFAULT_INPUTS["procurement"]
    return ModulePipelineInput(
        metadata_path=args.metadata or default.metadata_path,
        erd_path=args.erd or default.erd_path,
        scenario_path=args.scenario or default.scenario_path,
        plan_path=args.plan or default.plan_path,
        model_version=args.model_version,
    )


def _production_input(args: argparse.Namespace) -> ModulePipelineInput:
    default = DEFAULT_INPUTS["production"]
    return ModulePipelineInput(
        metadata_path=args.production_metadata or default.metadata_path,
        erd_path=args.production_erd or default.erd_path,
        scenario_path=args.production_scenario or default.scenario_path,
        plan_path=args.production_plan or default.plan_path,
        model_version=default.model_version,
        upstream_data_path=args.upstream_data,
    )


def _parse_modules(raw: str) -> tuple[str, ...]:
    modules = tuple(module.strip().lower() for module in raw.split(",") if module.strip())
    if not modules:
        raise argparse.ArgumentTypeError("--modules must include at least one module.")
    return modules


def _copy_optional_llm_artifacts(result: PipelineRunReport | GenericPipelineRunResult, args: argparse.Namespace) -> None:
    if not isinstance(result, PipelineRunReport):
        return
    if args.raw_llm_output:
        _copy_if_exists(Path(result.output_folder) / "prompt" / "azure_openai_raw_response.txt", Path(args.raw_llm_output))
    if args.generated_plan_output:
        _copy_if_exists(Path(result.output_folder) / "prompt" / "generated_llm_plan.json", Path(args.generated_plan_output))


def _print_summary(result: PipelineRunReport | GenericPipelineRunResult, modules: tuple[str, ...], args: argparse.Namespace) -> None:
    print("Pipeline completed.")
    print(f"Modules: {', '.join(modules)}")
    print(f"Output root: {args.output}")
    print(f"Seed: {args.seed if args.seed is not None else 'default'}")
    print(f"Profile ID: {args.profile_id or 'default'}")
    print(f"Status: {result.status}")
    if isinstance(result, PipelineRunReport):
        _print_procurement_report(result)
        return
    for module_id, module_result in result.module_results.items():
        print(
            f"{module_id}: status={module_result.status}, "
            f"tables={module_result.tables_generated}, validation={module_result.data_quality_status}, "
            f"output={module_result.output_folder}"
        )
    if result.warnings:
        print(f"Warnings: {len(result.warnings)}")
    if result.errors:
        print(f"Errors: {len(result.errors)}")


def _print_procurement_report(report: PipelineRunReport) -> None:
    audit_stage = next((stage for stage in report.stages if stage.stage_name == "audit_report"), None)
    sql_stage = next((stage for stage in report.stages if stage.stage_name == "sql_load"), None)
    data_quality_stage = next((stage for stage in report.stages if stage.stage_name == "data_quality_validation"), None)
    audit_path = audit_stage.output_paths[-1] if audit_stage and audit_stage.output_paths else ""
    print(f"Run ID: {report.run_id}")
    print(f"Output folder: {report.output_folder}")
    print(f"Tables generated: {report.tables_generated}")
    print(f"Total rows generated: {report.total_rows_generated}")
    print(f"Data quality status: {data_quality_stage.status if data_quality_stage else 'not_run'}")
    print(f"SQL load: {sql_stage.status if sql_stage else 'not_run'}")
    print(f"Audit report: {audit_path or 'not_generated'}")


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
