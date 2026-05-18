# Future MES Module Template

Copy these files when adding a new MES module. Do not register the new module
until its plugin, role catalog, prompt sections, validation rules, generator
factories, and tests are implemented.

Required implementation steps:

1. Create `procurement_data_generator/modules/<module_id>/`.
2. Define a role catalog in `role_catalog.py`.
3. Define module prompt sections in `prompt_sections.py`.
4. Define generic-runner validation boundaries in `validation_rules.py`.
5. Implement or adapt master/transaction generators.
6. Implement `<ModuleName>ModulePlugin` in `plugin.py`.
7. Register the plugin in `register_builtin_modules()` only when ready.
8. Add tests for plugin identity, roles, prompt sections, validation rules, and pipeline execution.

The template is intentionally inert. It is not imported by runtime code and is
not part of the built-in module registry.
