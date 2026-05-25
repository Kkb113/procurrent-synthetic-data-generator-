# Procurrent Synthetic Data Generator

Synthetic MES data generator for internal Procurement, Production, and Sales demos,
validation, and SQL-load preparation.

Current modules:

- Procurement v2: 25-table supplier-to-inventory flow.
- Production v1: 21-table production execution flow using Procurement upstream inventory and receipt lineage.
- Sales v1: 18-table Order-to-Cash flow using Production finished goods and Procurement/Production lineage.

The LLM is used for structured planning only. Python owns deterministic row
generation, primary/foreign keys, formulas, reconciliation, validation, and
output artifacts.

## Quick Start

Run the browser UI:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and run the default team flow:
Procurement -> Production -> Sales. The main UI asks for:

- Metadata XLSX
- Mermaid ERD
- Business Scenario

The product checkboxes are:

- Azure OpenAI: use the small IndustryScenarioPlan planning flow before deterministic Python generation.
- Build Prompt: save prompt/planning artifacts where supported.
- Load SQL: run the configured SQL load path; leave unchecked for local data generation.

Advanced settings include `target_total_rows`, `row_scale_factor`, `seed`, and
SQL `if_table_exists`. The main UI always runs the full MES lifecycle and hides
developer-only module/version/plan controls. Run without SQL first, then test SQL
load separately. After loading the full chain to SQL Server, run
`sql/mes_procurement_production_sales_validation.sql`; the final readiness status
should be `SALES_E2E_VALIDATED`.

Run Procurement only:

```powershell
python scripts/run_pipeline.py --modules procurement --output-dir output/demo_procurement --seed 42
```

Run Procurement followed by Production:

```powershell
python scripts/run_pipeline.py --modules procurement,production --output-dir output/demo_mes --seed 42
```

Run the full backend chain:

```powershell
python scripts/run_pipeline.py --modules procurement,production,sales --output-dir output/demo_full_mes --seed 42 --profile-id food_manufacturing
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
pytest -m "not slow and not sql and not llm" -q
pytest -m "pipeline and slow and not sql and not llm" -q
pytest -q -x
```

Focused marker runs:

```powershell
pytest -m unit -q
pytest -m integration -q
pytest -m pipeline -q
pytest -m slow -q
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

Frontend acceptance checks:

- Main UI: upload metadata, paste Mermaid ERD, enter a business scenario, and run the full Procurement -> Production -> Sales lifecycle.
- Result panel: verify status, total rows, per-module rows, validation status, SQL status, warnings/errors, and artifact paths.
- Artifacts: expect final data, `row_budget_report.json`, `row_count_audit.json`, generated industry profile when Azure planning/profile generation runs, LLM planning report when Azure OpenAI is used, and Phase 4 performance profile when generated.
- Developer routes: explicit plan JSON, module selectors, profile IDs, demo fallback, and model-version controls remain backend/developer concepts and are not part of the main UI.
- SQL validation for the full Sales chain: run `sql/mes_procurement_production_sales_validation.sql` after SQL load.
- Sales v1 excludes `SalesCreditMemo`.
