"""Lightweight performance profiling helpers for Production generation."""

from __future__ import annotations

import time
from typing import Any, Callable

import pandas as pd


def profile_stage(
    stages: list[dict[str, Any]],
    stage_name: str,
    action: Callable[[], Any],
    input_rows: dict[str, int] | None = None,
) -> Any:
    start = time.perf_counter()
    result = action()
    elapsed = round(time.perf_counter() - start, 6)
    stages.append(
        {
            "stage_name": stage_name,
            "row_count_input": input_rows or {},
            "row_count_output": profile_row_counts(result),
            "elapsed_seconds": elapsed,
        }
    )
    return result


def summarize_profile(stages: list[dict[str, Any]], total_elapsed_seconds: float) -> dict[str, Any]:
    slowest = max(stages, key=lambda item: item["elapsed_seconds"], default=None)
    return {
        "total_elapsed_seconds": round(total_elapsed_seconds, 6),
        "top_suspected_bottleneck": slowest["stage_name"] if slowest else None,
        "stages": stages,
    }


def profile_row_counts(value: Any) -> dict[str, int]:
    if isinstance(value, pd.DataFrame):
        return {"dataframe": len(value)}
    if isinstance(value, dict):
        return {
            str(key): len(item)
            for key, item in value.items()
            if isinstance(item, pd.DataFrame)
        }
    if isinstance(value, tuple):
        counts: dict[str, int] = {}
        for index, item in enumerate(value):
            if isinstance(item, pd.DataFrame):
                counts[f"dataframe_{index}"] = len(item)
            elif isinstance(item, dict):
                for key, nested in item.items():
                    if isinstance(nested, pd.DataFrame):
                        counts[str(key)] = len(nested)
        return counts
    return {}
