# Procurrent Synthetic Data Generator

Synthetic MES data generator for internal Procurement and Production demos,
validation, and SQL-load preparation.

Current modules:

- Procurement v2: 25-table supplier-to-inventory flow.
- Production v1: 21-table production execution flow using Procurement upstream inventory and receipt lineage.

The LLM is used for structured planning only. Python owns deterministic row
generation, primary/foreign keys, formulas, reconciliation, validation, and
output artifacts.

## Quick Start

Run the browser UI:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, choose Procurement or Procurement + Production,
and run the generic pipeline. Production depends on Procurement output; a
Production-only run requires an upstream `final_data` folder or explicit demo
fallback.

Run Procurement only:

```powershell
python scripts/run_pipeline.py --modules procurement --output-dir output/demo_procurement --seed 42
```

Run Procurement followed by Production:

```powershell
python scripts/run_pipeline.py --modules procurement,production --output-dir output/demo_mes --seed 42
```

Run Production only with explicit demo fallback upstream data:

```powershell
python scripts/run_pipeline.py --modules production --allow-demo-fallback --output-dir output/demo_production --seed 42
```

By default, Production-only generic runs fail unless Procurement upstream data is
provided with `--upstream-data` or `--allow-demo-fallback` is set.

Standalone compatibility scripts remain supported:

```powershell
python scripts/run_production_pipeline.py --metadata input/production_v1_metadata.xlsx --erd input/production_v1_erd.mmd --scenario input/production_v1_business_scenario.txt --plan input/sample_generation_plan_production_v1_valid.json --upstream-data output/<procurement_run>/final_data --output output/production_v1_runs --seed 42
```

## Architecture

- `core/pipeline/generic_runner.py`: generic registered-module orchestration.
- `core/modules/registry.py`: built-in module registry.
- `modules/procurement/plugin.py`: Procurement module adapter.
- `modules/production/plugin.py`: Production module adapter.
- `core/llm/prompt_builder.py`: generic MES planning prompt shell.
- `modules/*/prompt_sections.py`: module-owned prompt details.
- `core/validation/generic_validator.py`: schema/PK/FK/metadata checks.
- `modules/*/validation_rules.py`: module-specific validation ownership.
- `modules/shared/industry_profiles`: profile-driven industry vocabulary and policy values.

Current operating scope remains intentionally simple: one plant, one warehouse,
Shift A, calendar year 2025.

## Testing

Normal local baseline:

```powershell
pytest -m "not sql and not llm" -q
pytest -q -x
```

Focused marker runs:

```powershell
pytest -m unit -q
pytest -m integration -q
pytest -m pipeline -q
pytest -m sql -q
pytest -m llm -q
```

SQL tests require database connectivity. LLM tests require configured live Azure
OpenAI/LLM access. Normal tests do not require either service or pre-generated
files under `output/`.

## Adding Modules

Use `docs/module_template/` as the starting point. A future module should define
a role catalog, prompt sections, validation rules, generators, plugin adapter,
upstream requirements, and tests before being added to the built-in registry.

Sales is a future module concept only. It is not registered and has no backend
generation logic in the current platform.

Frontend acceptance checks:

- Procurement only: select Procurement and run; the result should include 25 Procurement tables.
- Procurement to Production: select Procurement and Production; the result should include 25 Procurement tables and 21 Production tables.
- Production only without fallback: expect a clear dependency error.
- Production only with demo fallback: enable demo fallback and expect a fallback warning.
- Food manufacturing: provide packaged food/snack scenario inputs through the scenario/plan flow; the UI does not force EV manufacturing.
