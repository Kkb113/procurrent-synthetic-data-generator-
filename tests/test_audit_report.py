from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from procurement_data_generator.core.audit.audit_report import AuditReportBuilder


def test_audit_report_builds_from_valid_data_quality_report(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}, "checks_run": 1, "checks_passed": 1, "checks_failed": 0})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.report["final_status"]["status"] == "passed"


def test_audit_report_marks_failed_when_data_quality_failed(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "failed", "issues": [], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.report["final_status"]["status"] == "failed"


def test_audit_report_marks_incomplete_when_data_quality_missing(tmp_path: Path) -> None:
    result = AuditReportBuilder().build_audit_report(output_folder=str(tmp_path))

    assert result.report["final_status"]["status"] == "incomplete"


def test_audit_report_includes_row_counts_from_csv_folders(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    pd.DataFrame({"A": [1, 2, 3]}).to_csv(folder / "Vendor.csv", index=False)
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), data_folders=[str(folder)], output_folder=str(tmp_path))

    assert result.report["generation_summary"]["row_counts_by_table"]["Vendor"] == 3
    assert result.report["generation_summary"]["total_rows_generated"] == 3


def test_later_data_folder_overrides_earlier_duplicate_table_csv(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    pd.DataFrame({"A": [1]}).to_csv(first / "PurchaseOrderLine.csv", index=False)
    pd.DataFrame({"A": [1, 2, 3, 4]}).to_csv(second / "PurchaseOrderLine.csv", index=False)
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), data_folders=[str(first), str(second)], output_folder=str(tmp_path))

    assert result.report["generation_summary"]["row_counts_by_table"]["PurchaseOrderLine"] == 4


def test_audit_report_includes_sql_load_summary_when_sql_report_exists(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})
    sql = _write_json(tmp_path / "sql.json", {"status": "passed", "tables_created": ["Vendor"], "tables_loaded": ["Vendor"], "total_rows_inserted": 1, "pk_constraints_created_count": 1, "fk_constraints_created_count": 0})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), sql_load_report_path=str(sql), output_folder=str(tmp_path))

    assert result.report["sql_load_summary"]["sql_load_attempted"] is True
    assert result.report["sql_load_summary"]["sql_load_status"] == "passed"


def test_audit_report_handles_missing_sql_load_report_as_not_attempted(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.report["sql_load_summary"]["sql_load_status"] == "not_attempted"


def test_markdown_report_is_created(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.markdown_path.exists()
    assert "Procurement Data Generation Audit Report" in result.markdown_path.read_text(encoding="utf-8")


def test_json_report_is_created(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.json_path.exists()
    assert json.loads(result.json_path.read_text(encoding="utf-8"))["final_status"]["status"] == "passed"


def test_report_includes_top_warnings(tmp_path: Path) -> None:
    issue = {"level": "warning", "check_type": "ROW_COUNT", "table_name": "InventoryBalance", "message": "Grouped rows differ."}
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed_with_warnings", "warning_count": 1, "error_count": 0, "issues": [issue], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.report["data_quality_summary"]["top_warnings"][0]["check_type"] == "ROW_COUNT"


def test_report_includes_top_errors(tmp_path: Path) -> None:
    issue = {"level": "error", "check_type": "FK_INTEGRITY", "table_name": "PurchaseOrderLine", "message": "Bad FK."}
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "failed", "warning_count": 0, "error_count": 1, "issues": [issue], "table_summaries": {}})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), output_folder=str(tmp_path))

    assert result.report["data_quality_summary"]["top_errors"][0]["check_type"] == "FK_INTEGRITY"


def test_scenario_preview_is_included_when_scenario_file_exists(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})
    scenario = tmp_path / "scenario.txt"
    scenario.write_text("Generate procurement data for a plant.", encoding="utf-8")

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), scenario_path=str(scenario), output_folder=str(tmp_path))

    assert "procurement data" in result.report["business_summary"]["scenario_text_preview"]


def test_domain_industry_is_included_when_plan_exists(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})
    plan = _write_json(tmp_path / "plan.json", {"domain_profile": {"industry": "Pharma manufacturing", "business_context": "Sterile supplies"}, "formula_rules": []})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), llm_plan_path=str(plan), output_folder=str(tmp_path))

    assert result.report["business_summary"]["industry"] == "Pharma manufacturing"


def test_sql_failure_with_passed_quality_sets_passed_with_warnings(tmp_path: Path) -> None:
    quality = _write_json(tmp_path / "quality.json", {"overall_status": "passed", "issues": [], "table_summaries": {}})
    sql = _write_json(tmp_path / "sql.json", {"status": "failed", "errors": ["connection failed"]})

    result = AuditReportBuilder().build_audit_report(data_quality_report_path=str(quality), sql_load_report_path=str(sql), output_folder=str(tmp_path))

    assert result.report["final_status"]["status"] == "passed_with_warnings"
    assert result.report["final_status"]["ready_for_sql_load"] is True


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
