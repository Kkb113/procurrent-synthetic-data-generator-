from __future__ import annotations

from pathlib import Path


PIPELINE_TEST_FILES = {
    "test_data_validator_v2.py",
    "test_pipeline_runner.py",
    "test_pipeline_runner_v2.py",
    "test_production_pipeline_runner.py",
}

INTEGRATION_TEST_FILES = {
    "test_artifact_api.py",
    "test_audit_report.py",
    "test_fastapi_app.py",
    "test_pipeline_api.py",
    "test_pipeline_api_v2.py",
    "test_production_data_validator.py",
    "test_sql_loader.py",
}

CATEGORY_MARKERS = {"unit", "integration", "pipeline", "sql", "llm"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        filename = Path(str(item.fspath)).name
        marker_names = {marker.name for marker in item.iter_markers()}

        if filename in PIPELINE_TEST_FILES:
            if "pipeline" not in marker_names:
                item.add_marker("pipeline")
            if "integration" not in marker_names:
                item.add_marker("integration")
            continue

        if filename in INTEGRATION_TEST_FILES:
            if "integration" not in marker_names:
                item.add_marker("integration")
            continue

        if marker_names.isdisjoint(CATEGORY_MARKERS):
            item.add_marker("unit")
