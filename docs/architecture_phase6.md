# Phase 6 Architecture Notes

This project now follows a stabilized Procurement -> Production -> Sales lifecycle.
The Phase 6 cleanup keeps public entry points stable while moving isolated helper
logic into smaller modules.

## Main Entry Points

- UI/API: `app/templates/index.html`, `app/static/js/app.js`, and `POST /api/pipeline/run-mes`.
- Product workflow service: `app/services/pipeline_service.py`.
- Product response shaping: `app/services/mes_lifecycle_response.py`.
- Generic lifecycle runner: `procurement_data_generator/core/pipeline/generic_runner.py`.
- Procurement runner and live LLM planning path: `procurement_data_generator/core/pipeline/pipeline_runner.py`.

## LLM Planning

- The LLM produces only `IndustryScenarioPlan`.
- `procurement_data_generator/core/llm/industry_scenario_service.py` handles parsing, repair, and fallback.
- `procurement_data_generator/core/llm/plan_synthesizer.py` creates the executable plan.
- `procurement_data_generator/core/llm/plan_validator.py` remains the public strict validation API.

## Industry Profiles

- Generated profiles are adapted in `procurement_data_generator/modules/shared/industry_profiles/generated_profile_adapter.py`.
- Static and generated profile loading is centralized in `profile_loader.py`.
- Generators consume profile vocabulary generically through `IndustryProfileValueProvider`.

## Row Budgeting

- `procurement_data_generator/core/row_budget.py` owns table classification, scaling, planned targets, and row-budget reports.
- Existing row-count audit remains in `procurement_data_generator/core/audit/row_count_audit.py`.

## Lifecycle Generators

- Procurement transaction generation remains in `modules/procurement/transaction_generator.py`.
- Production transaction generation remains publicly exposed through `modules/production/transaction_generator.py`.
- Production raw-material allocation helpers now live in `modules/production/allocation.py`.
- Production timing helpers now live in `modules/production/performance_profile.py`.
- Sales transaction generation remains publicly exposed through `modules/sales/transaction_generator.py`.
- Sales pure status and tolerance rules now live in `modules/sales/status_rules.py`.

## Compatibility

These public imports are intentionally preserved:

- `ProductionTransactionGenerator`
- `SalesTransactionGenerator`
- `ProcurementTransactionGenerator`
- module plugin classes
- `SyntheticDataPipelineRunner`
- `ProcurementPipelineRunner`
- `validate_generation_plan`

Developer routes such as `/api/pipeline/run` and `/api/pipeline/run-generic`
remain available for backward compatibility. The main UI hides those internals
and uses `/api/pipeline/run-mes`.
