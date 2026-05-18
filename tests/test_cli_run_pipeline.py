from __future__ import annotations

from pathlib import Path

import pytest

import scripts.run_pipeline as run_pipeline_cli
from procurement_data_generator.core.contracts.pipeline_report import PipelineRunReport, utc_now_iso
from procurement_data_generator.core.pipeline.generic_runner import GenericPipelineRunResult, ModulePipelineRunResult, PipelineConfigurationError


class FakeRunner:
    calls: list[tuple[str, dict]] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def resolve_modules(self, modules):
        normalized = tuple(module.strip().lower() for module in modules)
        if len(set(normalized)) != len(normalized):
            raise PipelineConfigurationError("Duplicate module_id values are not allowed: procurement.")
        unknown = [module for module in normalized if module not in {"procurement", "production"}]
        if unknown:
            raise KeyError(f"Unknown module plugin '{unknown[0]}'.")
        return None

    def run_pipeline(self, **kwargs):
        self.calls.append(("run_pipeline", kwargs))
        report = PipelineRunReport(
            run_id="run_fake",
            started_at=utc_now_iso(),
            input_files={},
            output_folder=str(kwargs["output_folder"]),
        )
        report.tables_generated = 25
        report.total_rows_generated = 100
        report.data_quality_status = "passed"
        report.complete("passed")
        return report

    def run(self, spec):
        self.calls.append(("run", {"spec": spec}))
        if spec.module_ids == ("production",) and not spec.generation_config.allow_demo_fallback:
            raise ValueError("Production requires Procurement upstream data.")
        return GenericPipelineRunResult(
            status="passed",
            module_ids=spec.module_ids,
            output_folder=spec.output_folder,
            module_results={
                module_id: ModulePipelineRunResult(
                    module_id=module_id,
                    status="passed",
                    output_folder=str(Path(spec.output_folder) / module_id),
                    tables_generated=25 if module_id == "procurement" else 21,
                    data_quality_status="passed",
                )
                for module_id in spec.module_ids
            },
        )


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch):
    FakeRunner.calls = []
    monkeypatch.setattr(run_pipeline_cli, "SyntheticDataPipelineRunner", FakeRunner)


def test_cli_runs_procurement_default_path(tmp_path: Path, capsys) -> None:
    exit_code = run_pipeline_cli.main(["--modules", "procurement", "--output-dir", str(tmp_path), "--seed", "42"])

    assert exit_code == 0
    assert FakeRunner.calls[0][0] == "run_pipeline"
    assert FakeRunner.calls[0][1]["model_version"] == "v2"
    assert "Modules: procurement" in capsys.readouterr().out


def test_cli_runs_procurement_then_production(tmp_path: Path, capsys) -> None:
    exit_code = run_pipeline_cli.main(["--modules", "procurement,production", "--output-dir", str(tmp_path), "--seed", "42"])

    assert exit_code == 0
    call = FakeRunner.calls[0]
    assert call[0] == "run"
    assert call[1]["spec"].module_ids == ("procurement", "production")
    assert "production: status=passed, tables=21" in capsys.readouterr().out


def test_cli_rejects_duplicate_modules(tmp_path: Path, capsys) -> None:
    exit_code = run_pipeline_cli.main(["--modules", "procurement,procurement", "--output-dir", str(tmp_path)])

    assert exit_code == 2
    assert "Duplicate module_id values" in capsys.readouterr().err


def test_cli_rejects_unknown_module(tmp_path: Path, capsys) -> None:
    exit_code = run_pipeline_cli.main(["--modules", "quality", "--output-dir", str(tmp_path)])

    assert exit_code == 2
    assert "Unknown module plugin" in capsys.readouterr().err


def test_cli_requires_explicit_demo_fallback_for_production_only(tmp_path: Path, capsys) -> None:
    exit_code = run_pipeline_cli.main(["--modules", "production", "--output-dir", str(tmp_path)])

    assert exit_code == 2
    assert "requires Procurement upstream data" in capsys.readouterr().err


def test_cli_allows_explicit_demo_fallback_for_production_only(tmp_path: Path) -> None:
    exit_code = run_pipeline_cli.main(["--modules", "production", "--allow-demo-fallback", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert FakeRunner.calls[0][1]["spec"].generation_config.allow_demo_fallback is True
