# Adding a Future MES Module

Future modules should be added through the plugin boundary, not by importing
module generators directly from core.

Checklist:

1. Copy `docs/module_template/` into a new module package.
2. Define `module_id`, `module_name`, and `module_version`.
3. Add a role catalog and role validation.
4. Add module prompt sections.
5. Add master and transaction generator factories.
6. Add module-specific validation rules and a data-quality adapter if needed.
7. Declare upstream requirements with `UpstreamRequirement`.
8. Add plugin tests, validation tests, and pipeline tests.
9. Register the plugin in `register_builtin_modules()` only after tests pass.

Do not add new module names directly to core pipeline logic. Core should resolve
registered plugins and use plugin capabilities.
