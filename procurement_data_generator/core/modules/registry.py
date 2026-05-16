"""Registry for MES module plugins."""

from __future__ import annotations

from procurement_data_generator.core.modules.contracts import MESModulePlugin


class ModuleRegistryError(Exception):
    """Base error raised by module registry operations."""


class DuplicateModuleError(ModuleRegistryError):
    """Raised when registering a duplicate module without overwrite."""


class UnknownModuleError(ModuleRegistryError, KeyError):
    """Raised when a module id is not registered."""


class ModuleRegistry:
    """Small in-memory registry of MES module plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, MESModulePlugin] = {}

    def register(self, plugin: MESModulePlugin, overwrite: bool = False) -> MESModulePlugin:
        module_id = _normalize_module_id(plugin.module_id)
        if module_id in self._plugins and not overwrite:
            raise DuplicateModuleError(f"Module plugin '{module_id}' is already registered.")
        self._plugins[module_id] = plugin
        return plugin

    def get(self, module_id: str) -> MESModulePlugin:
        normalized = _normalize_module_id(module_id)
        try:
            return self._plugins[normalized]
        except KeyError as exc:
            available = ", ".join(self.list_modules()) or "none"
            raise UnknownModuleError(f"Unknown module plugin '{normalized}'. Registered modules: {available}.") from exc

    def list_modules(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))

    def clear(self) -> None:
        self._plugins.clear()


def create_default_module_registry() -> ModuleRegistry:
    """Create a registry with the built-in Procurement and Production modules."""

    registry = ModuleRegistry()
    register_builtin_modules(registry)
    return registry


def register_builtin_modules(registry: ModuleRegistry) -> ModuleRegistry:
    """Register built-in module plugins.

    Imports stay inside this function so the generic registry can be imported
    without pulling concrete modules into core contracts.
    """

    from procurement_data_generator.modules.procurement.plugin import ProcurementModulePlugin
    from procurement_data_generator.modules.production.plugin import ProductionModulePlugin

    registry.register(ProcurementModulePlugin())
    registry.register(ProductionModulePlugin())
    return registry


def _normalize_module_id(module_id: str) -> str:
    normalized = module_id.strip().lower()
    if not normalized:
        raise ModuleRegistryError("Module plugin id must not be empty.")
    return normalized

