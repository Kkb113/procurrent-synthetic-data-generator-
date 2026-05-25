# Testing

The normal local test baseline is designed to run from a fresh clone without SQL Server,
live Azure OpenAI calls, internet access, or pre-existing files under `output/`.

Recommended local commands:

```powershell
pytest -m "not slow and not sql and not llm" -q
pytest -m "pipeline and slow and not sql and not llm" -q
pytest -q -x
```

Optional focused commands:

```powershell
pytest -m unit -q
pytest -m integration -q
pytest -m pipeline -q
pytest -m sql -q
pytest -m llm -q
```

Marker meanings:

- `unit`: fast tests with no external services
- `integration`: tests multiple internal components without SQL or live LLM
- `pipeline`: full or near-full generation pipeline tests
- `slow`: lifecycle or volume tests excluded from the fast local baseline
- `sql`: tests requiring SQL Server or database connectivity
- `llm`: tests requiring live LLM or Azure OpenAI calls

Slow lifecycle tests, SQL tests, and live LLM tests are excluded from the fast
local baseline unless explicitly requested.
Tests that need generated CSVs should create them under pytest temporary directories or
use committed test fixtures, not repo-level `output/` folders.

CI should run the same non-external baseline:

```powershell
pytest -m "not slow and not sql and not llm" -q
```

Phase 5 UI/API checks:

```powershell
pytest tests/test_phase5_mes_lifecycle_api.py tests/test_frontend_generic_ui.py tests/test_frontend_sales_ui.py tests/test_artifact_api.py -q
```

The main UI should render only the product workflow: Metadata XLSX, Mermaid ERD,
Business Scenario, Azure OpenAI, Build Prompt, Load SQL, and collapsed advanced
row/seed/SQL settings. It should not expose module selectors, v1/v2 labels,
manual executable plan JSON, demo fallback, or separate Production/Sales inputs.

The full suite can be run locally before commits:

```powershell
pytest -q -x
```
