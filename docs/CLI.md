# CLI

Generic CLI:

```powershell
python scripts/run_pipeline.py --modules procurement
python scripts/run_pipeline.py --modules procurement,production --output-dir output/demo --seed 42
python scripts/run_pipeline.py --modules procurement,production,sales --output-dir output/demo_full_mes --seed 42 --profile-id food_manufacturing
python scripts/run_pipeline.py --modules production --upstream-data output/demo/procurement/<run>/final_data
python scripts/run_pipeline.py --modules production --allow-demo-fallback
```

Useful options:

- `--modules`: comma-separated module IDs.
- `--output-dir` / `--output`: output root.
- `--seed`: deterministic seed.
- `--profile-id`: industry profile, such as `food_manufacturing`.
- `--allow-demo-fallback`: explicitly allow Production fallback upstream data.
- `--upstream-data`: existing Procurement `final_data` folder for Production.

Production-only runs do not silently create upstream Procurement data unless
`--allow-demo-fallback` is set.

The browser UI defaults to the full `procurement,production,sales` team flow at
`http://127.0.0.1:8000` after starting:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run without SQL first, then test SQL load separately. Final SQL validation for
Sales remains a later phase.
