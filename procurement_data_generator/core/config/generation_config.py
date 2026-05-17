"""Runtime generation configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GenerationConfig:
    """Small runtime configuration object for generation runs."""

    seed: int = 42
    output_dir: Path | None = None
    allow_demo_fallback: bool = False
    run_name: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer.")
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        if self.run_name is not None:
            run_name = str(self.run_name).strip()
            if not run_name:
                raise ValueError("run_name must not be blank when provided.")
            object.__setattr__(self, "run_name", run_name)
