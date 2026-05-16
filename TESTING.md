# Testing

The normal local test baseline is designed to run from a fresh clone without SQL Server,
live Azure OpenAI calls, internet access, or pre-existing files under `output/`.

Recommended local commands:

```powershell
pytest -m "not sql and not llm" -q
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
- `sql`: tests requiring SQL Server or database connectivity
- `llm`: tests requiring live LLM or Azure OpenAI calls

SQL and live LLM tests are excluded from normal local runs unless explicitly requested.
Tests that need generated CSVs should create them under pytest temporary directories or
use committed test fixtures, not repo-level `output/` folders.
