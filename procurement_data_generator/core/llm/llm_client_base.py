"""Base contracts for LLM planning clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from procurement_data_generator.core.contracts.pipeline_report import utc_now_iso


@dataclass
class LLMResponse:
    """Provider-neutral response from an LLM planning call."""

    provider: str
    deployment: str
    status: str
    raw_text: str = ""
    extracted_json_text: str | None = None
    parsed_json: dict[str, Any] | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    retry_count: int = 0

    def complete(self) -> None:
        self.completed_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "deployment": self.deployment,
            "status": self.status,
            "raw_text": self.raw_text,
            "extracted_json_text": self.extracted_json_text,
            "parsed_json": self.parsed_json,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "error_message": self.error_message,
            "warnings": self.warnings,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
        }


class LLMClientBase(ABC):
    """Base interface for LLM plan generation providers."""

    @abstractmethod
    def generate_plan(self, prompt: str) -> LLMResponse:
        """Generate an LLM generation plan response for a planning prompt."""
