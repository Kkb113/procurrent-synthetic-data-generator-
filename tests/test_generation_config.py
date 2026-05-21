from __future__ import annotations

from pathlib import Path

import pytest

from procurement_data_generator.core.config import DEFAULT_OPERATING_SCOPE, GenerationConfig, OperatingScope
from procurement_data_generator.core.pipeline.generic_runner import PipelineRunSpec, SyntheticDataPipelineRunner
from procurement_data_generator.core.pipeline.pipeline_runner import ProcurementPipelineRunner
from procurement_data_generator.modules.procurement.master_generator import ProcurementMasterDataGenerator
from procurement_data_generator.modules.procurement.plugin import ProcurementModulePlugin
from procurement_data_generator.modules.procurement.transaction_generator import ProcurementTransactionGenerator
from procurement_data_generator.modules.production.master_generator import ProductionMasterDataGenerator
from procurement_data_generator.modules.production.plugin import ProductionModulePlugin
from procurement_data_generator.modules.production.transaction_generator import ProductionTransactionGenerator


pytestmark = pytest.mark.unit


def test_generation_config_defaults_are_deterministic_and_conservative() -> None:
    config = GenerationConfig()

    assert config.seed == 42
    assert config.output_dir is None
    assert config.allow_demo_fallback is False
    assert config.run_name is None
    assert config.profile_id is None
    assert config.row_scale_factor == 1.0
    assert config.target_total_rows is None
    assert config.max_rows_per_table is None
    assert config.max_production_orders is None
    assert config.max_production_requirements is None
    assert config.limit_sales_orders_by_customer is False
    assert config.sales_orders_per_customer_cap == 50
    assert config.profile_file is None
    assert config.planned_row_targets is None


def test_generation_config_normalizes_output_dir_to_path(tmp_path: Path) -> None:
    profile_file = tmp_path / "profile.json"
    config = GenerationConfig(output_dir=str(tmp_path), run_name=" phase-5 ", profile_id=" food_manufacturing ", profile_file=str(profile_file))

    assert config.output_dir == tmp_path
    assert config.run_name == "phase-5"
    assert config.profile_id == "food_manufacturing"
    assert config.profile_file == profile_file


@pytest.mark.parametrize("seed", [None, True, "42"])
def test_generation_config_rejects_invalid_seed(seed: object) -> None:
    with pytest.raises(ValueError, match="seed"):
        GenerationConfig(seed=seed)  # type: ignore[arg-type]


def test_generation_config_rejects_blank_run_name() -> None:
    with pytest.raises(ValueError, match="run_name"):
        GenerationConfig(run_name=" ")


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("row_scale_factor", 0),
        ("row_scale_factor", True),
        ("target_total_rows", 0),
        ("max_rows_per_table", -1),
        ("max_production_orders", "20"),
        ("max_production_requirements", False),
        ("limit_sales_orders_by_customer", "false"),
        ("sales_orders_per_customer_cap", 0),
        ("planned_row_targets", {"SalesOrderHdr": 0}),
        ("planned_row_targets", {" ": 10}),
    ],
)
def test_generation_config_rejects_invalid_phase1_row_controls(field_name: str, value: object) -> None:
    with pytest.raises(ValueError, match=field_name):
        GenerationConfig(**{field_name: value})  # type: ignore[arg-type]


def test_generation_config_normalizes_planned_row_targets() -> None:
    config = GenerationConfig(planned_row_targets={"SalesOrderHdr": 25})

    assert config.planned_row_targets == {"SalesOrderHdr": 25}


def test_procurement_generators_accept_optional_phase5_config_objects(tmp_path: Path) -> None:
    scope = OperatingScope()
    config = GenerationConfig(output_dir=tmp_path)

    master_generator = ProcurementMasterDataGenerator(operating_scope=scope, generation_config=config)
    transaction_generator = ProcurementTransactionGenerator(operating_scope=scope, generation_config=config)

    assert master_generator.operating_scope is scope
    assert master_generator.generation_config is config
    assert transaction_generator.operating_scope is scope
    assert transaction_generator.generation_config is config


def test_production_generators_accept_optional_phase5_config_objects(tmp_path: Path) -> None:
    scope = OperatingScope()
    config = GenerationConfig(output_dir=tmp_path)

    master_generator = ProductionMasterDataGenerator(operating_scope=scope, generation_config=config)
    transaction_generator = ProductionTransactionGenerator(operating_scope=scope, generation_config=config)

    assert master_generator.operating_scope is scope
    assert master_generator.generation_config is config
    assert transaction_generator.operating_scope is scope
    assert transaction_generator.generation_config is config


def test_module_plugins_forward_phase5_config_objects_to_generators(tmp_path: Path) -> None:
    scope = OperatingScope()
    config = GenerationConfig(output_dir=tmp_path)

    procurement_master = ProcurementModulePlugin().create_master_generator(
        operating_scope=scope,
        generation_config=config,
    )
    production_transaction = ProductionModulePlugin().create_transaction_generator(
        operating_scope=scope,
        generation_config=config,
    )

    assert procurement_master.operating_scope is scope
    assert procurement_master.generation_config is config
    assert production_transaction.operating_scope is scope
    assert production_transaction.generation_config is config


def test_procurement_pipeline_runner_accepts_optional_phase5_config_objects(tmp_path: Path) -> None:
    scope = OperatingScope()
    config = GenerationConfig(output_dir=tmp_path)

    runner = ProcurementPipelineRunner(operating_scope=scope, generation_config=config)

    assert runner.operating_scope is scope
    assert runner.generation_config is config


def test_procurement_pipeline_runner_preserves_default_config_when_omitted() -> None:
    runner = ProcurementPipelineRunner()

    assert runner.operating_scope is DEFAULT_OPERATING_SCOPE
    assert isinstance(runner.generation_config, GenerationConfig)


def test_generic_pipeline_runner_accepts_optional_phase5_config_objects(tmp_path: Path) -> None:
    scope = OperatingScope()
    config = GenerationConfig(output_dir=tmp_path)

    runner = SyntheticDataPipelineRunner(operating_scope=scope, generation_config=config)

    assert runner.operating_scope is scope
    assert runner.generation_config is config


def test_pipeline_run_spec_can_carry_phase5_config_objects(tmp_path: Path) -> None:
    scope = OperatingScope()
    config = GenerationConfig(output_dir=tmp_path)

    spec = PipelineRunSpec(
        module_ids=("procurement",),
        metadata_path="metadata.xlsx",
        erd_path="erd.mmd",
        scenario_path=None,
        plan_path="plan.json",
        output_folder=str(tmp_path),
        operating_scope=scope,
        generation_config=config,
    )

    assert spec.operating_scope is scope
    assert spec.generation_config is config
