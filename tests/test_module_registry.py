from __future__ import annotations

import pytest

from procurement_data_generator.core.modules.registry import (
    DuplicateModuleError,
    ModuleRegistry,
    UnknownModuleError,
    create_default_module_registry,
)
from procurement_data_generator.modules.procurement.plugin import ProcurementModulePlugin
from procurement_data_generator.modules.production.plugin import ProductionModulePlugin
from procurement_data_generator.modules.sales.plugin import SalesModulePlugin


class DummyPlugin:
    module_id = "dummy"
    module_name = "Dummy"
    module_version = "v0"


def test_registry_registers_and_retrieves_procurement_plugin() -> None:
    registry = ModuleRegistry()
    plugin = ProcurementModulePlugin()

    registry.register(plugin)

    assert registry.get("procurement") is plugin
    assert registry.list_modules() == ("procurement",)


def test_registry_registers_and_retrieves_production_plugin() -> None:
    registry = ModuleRegistry()
    plugin = ProductionModulePlugin()

    registry.register(plugin)

    assert registry.get("production") is plugin


def test_registry_registers_and_retrieves_sales_plugin() -> None:
    registry = ModuleRegistry()
    plugin = SalesModulePlugin()

    registry.register(plugin)

    assert registry.get("sales") is plugin


def test_registry_rejects_duplicate_module_id() -> None:
    registry = ModuleRegistry()
    registry.register(DummyPlugin())

    with pytest.raises(DuplicateModuleError, match="already registered"):
        registry.register(DummyPlugin())


def test_registry_can_overwrite_duplicate_module_id() -> None:
    registry = ModuleRegistry()
    first = DummyPlugin()
    second = DummyPlugin()
    registry.register(first)

    registry.register(second, overwrite=True)

    assert registry.get("dummy") is second


def test_registry_unknown_module_raises_clear_error() -> None:
    registry = ModuleRegistry()

    with pytest.raises(UnknownModuleError, match="Unknown module plugin 'missing'"):
        registry.get("missing")


def test_default_registry_includes_builtin_modules() -> None:
    registry = create_default_module_registry()

    assert registry.list_modules() == ("procurement", "production", "sales")
    assert registry.get("procurement").module_version == "v2"
    assert registry.get("production").module_version == "v1"
    assert registry.get("sales").module_version == "v1"
