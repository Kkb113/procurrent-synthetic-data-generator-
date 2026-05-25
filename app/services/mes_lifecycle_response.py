"""Response shaping helpers for the productized MES lifecycle endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def enrich_mes_lifecycle_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Add user-facing lifecycle fields without changing generic-run details."""

    enriched = dict(summary)
    enriched["message"] = mes_user_message(enriched)
    enriched["lifecycle"] = ["procurement", "production", "sales"]
    enriched["validation_status"] = combined_status(
        list(enriched.get("validation_summary", {}).values()),
        empty="not_run",
    )
    enriched["sql_status"] = normalize_sql_status(enriched.get("sql_load_status", "not_run"))
    enriched["warning_count"] = len(enriched.get("warnings", []))
    enriched["error_count"] = len(enriched.get("errors", []))
    enriched["artifact_paths"] = artifact_paths(enriched.get("output_folder"))
    enriched["downloads"] = mes_downloads(enriched["run_id"], enriched["artifact_paths"])
    enriched["total_rows"] = enriched.get("total_rows_generated", 0)
    enriched["per_module_row_counts"] = {
        module_id: module_result.get("total_rows_generated", 0)
        for module_id, module_result in enriched.get("module_results", {}).items()
    }
    return enriched


def mes_user_message(summary: dict[str, Any]) -> str:
    if summary.get("status") in {"passed", "passed_with_warnings"}:
        return "MES lifecycle generation completed."
    return "MES lifecycle generation failed. Review the validation summary and reports."


def normalize_sql_status(status: str | None) -> str:
    return "not_run" if status in {None, "", "skipped"} else str(status)


def artifact_paths(output_folder: str | None) -> dict[str, str]:
    if not output_folder:
        return {}
    root = Path(output_folder)
    direct_candidates = {
        "final_data": root / "final_data",
        "row_budget_report": root / "reports" / "row_budget_report.json",
        "row_count_audit": root / "reports" / "row_count_audit.json",
    }
    artifacts = {
        name: str(path)
        for name, path in direct_candidates.items()
        if path.exists()
    }
    recursive_names = {
        "llm_planning_report": "llm_planning_report.json",
        "generated_industry_profile": "generated_industry_profile.json",
        "performance_profile_phase4": "performance_profile_phase4.json",
    }
    for artifact_name, filename in recursive_names.items():
        match = first_existing(root, filename)
        if match is not None:
            artifacts[artifact_name] = str(match)
    return artifacts


def first_existing(root: Path, filename: str) -> Path | None:
    direct = root / filename
    if direct.exists():
        return direct
    matches = sorted(root.glob(f"**/{filename}"))
    return matches[0] if matches else None


def mes_downloads(run_id: str, artifacts: dict[str, str]) -> dict[str, str]:
    downloads: dict[str, str] = {}
    if "final_data" in artifacts:
        downloads["final_data_zip"] = f"/api/artifacts/{run_id}/final-data-zip"
    if "row_budget_report" in artifacts:
        downloads["row_budget_report"] = f"/api/artifacts/{run_id}/row-budget-report"
    if "row_count_audit" in artifacts:
        downloads["row_count_audit"] = f"/api/artifacts/{run_id}/row-count-audit"
    if "llm_planning_report" in artifacts:
        downloads["llm_planning_report"] = f"/api/artifacts/{run_id}/llm-planning-report"
    if "generated_industry_profile" in artifacts:
        downloads["generated_industry_profile"] = f"/api/artifacts/{run_id}/generated-industry-profile"
    if "performance_profile_phase4" in artifacts:
        downloads["performance_profile_phase4"] = f"/api/artifacts/{run_id}/performance-profile-phase4"
    return downloads


def combined_status(statuses: list[str], empty: str = "-") -> str:
    if not statuses:
        return empty
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "passed_with_warnings" for status in statuses):
        return "passed_with_warnings"
    if all(status == "skipped" for status in statuses):
        return "skipped"
    if any(status == "passed" for status in statuses):
        return "passed"
    return statuses[0]
