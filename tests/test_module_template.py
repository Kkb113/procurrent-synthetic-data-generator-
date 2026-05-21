from __future__ import annotations

from pathlib import Path

from procurement_data_generator.core.modules.registry import create_default_module_registry


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "module_template"


def test_future_module_template_exists_and_documents_required_files() -> None:
    assert (TEMPLATE / "README.md").exists()
    for filename in [
        "plugin.py.template",
        "role_catalog.py.template",
        "prompt_sections.py.template",
        "validation_rules.py.template",
        "master_generator.py.template",
        "transaction_generator.py.template",
    ]:
        assert (TEMPLATE / filename).exists()
    text = (TEMPLATE / "README.md").read_text(encoding="utf-8")
    assert "role catalog" in text
    assert "plugin" in text
    assert "not part of the built-in module registry" in text


def test_future_module_template_is_not_registered() -> None:
    registry = create_default_module_registry()

    assert registry.list_modules() == ("procurement", "production", "sales")
    assert "example" not in registry.list_modules()
