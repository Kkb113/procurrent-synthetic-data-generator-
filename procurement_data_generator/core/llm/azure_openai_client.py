"""Azure OpenAI client for LLM generation plan creation."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from dotenv import load_dotenv

from procurement_data_generator.core.llm.json_extractor import extract_json_object
from procurement_data_generator.core.llm.llm_client_base import LLMClientBase, LLMResponse


class AzureOpenAIConfigError(ValueError):
    """Raised when required Azure OpenAI configuration is missing."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"Azure OpenAI configuration missing. Missing: {', '.join(missing)}")


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Configuration for Azure OpenAI plan generation."""

    endpoint: str
    api_key: str
    deployment: str
    api_version: str = ""
    model: str | None = None
    timeout_seconds: int = 120
    max_retries: int = 3
    use_v1_api: bool = False

    @classmethod
    def from_env(cls, env_path: str | None = None) -> "AzureOpenAIConfig":
        if env_path:
            load_dotenv(env_path, override=True)
        else:
            load_dotenv()
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> "AzureOpenAIConfig":
        missing = [
            name
            for name in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"]
            if not (values.get(name) or "").strip()
        ]
        if missing:
            raise AzureOpenAIConfigError(missing)

        return cls(
            endpoint=(values.get("AZURE_OPENAI_ENDPOINT") or "").strip(),
            api_key=(values.get("AZURE_OPENAI_API_KEY") or "").strip(),
            deployment=(values.get("AZURE_OPENAI_DEPLOYMENT") or "").strip(),
            api_version=(values.get("AZURE_OPENAI_API_VERSION") or "").strip() or "2024-02-15-preview",
            model=(values.get("AZURE_OPENAI_MODEL") or "").strip() or None,
            timeout_seconds=_parse_positive_int(values.get("AZURE_OPENAI_TIMEOUT_SECONDS"), 120),
            max_retries=_parse_non_negative_int(values.get("AZURE_OPENAI_MAX_RETRIES"), 3),
            use_v1_api=_parse_bool(values.get("AZURE_OPENAI_USE_V1_API")),
        )


class AzureOpenAIClient(LLMClientBase):
    """Generate LLMGenerationPlan JSON using Azure OpenAI."""

    provider = "Azure OpenAI"

    def __init__(self, config: AzureOpenAIConfig, openai_client: Any | None = None) -> None:
        self.config = config
        self._client = openai_client

    def generate_plan(self, prompt: str) -> LLMResponse:
        return self.generate_json(
            prompt,
            system_message=(
                "You are an MES synthetic data planning assistant. Return only valid JSON. "
                "Do not generate raw rows, CSV data, SQL inserts, Python code, or markdown. "
                "The LLM creates a structured business generation plan. Python validates the plan, "
                "generates deterministic data, calculates formulas, reconciles data, and validates business rules."
            ),
        )

    def generate_json(self, prompt: str, system_message: str) -> LLMResponse:
        """Generate a JSON object response using Azure OpenAI."""

        response = LLMResponse(provider=self.provider, deployment=self.config.deployment, status="failed")
        if not prompt.strip():
            response.error_message = "Prompt is empty."
            response.complete()
            return response

        try:
            client = self._get_client()
        except Exception as exc:
            response.error_message = _sanitize_error(exc, self.config.api_key)
            response.complete()
            return response

        attempts = self.config.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                completion = client.chat.completions.create(
                    model=self.config.deployment,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                    timeout=self.config.timeout_seconds,
                )
                self._populate_from_completion(response, completion)
                extraction = extract_json_object(response.raw_text)
                if not extraction.success:
                    response.error_message = extraction.error_message
                    response.status = "failed"
                    response.complete()
                    return response
                response.extracted_json_text = extraction.json_text
                response.parsed_json = extraction.parsed_json
                response.status = "passed"
                response.complete()
                return response
            except Exception as exc:  # pragma: no cover - specific provider exceptions vary by package version.
                last_error = exc
                if attempt < attempts - 1 and _is_retryable_error(exc):
                    response.retry_count += 1
                    time.sleep(min(2**attempt, 5))
                    continue
                break

        response.error_message = _sanitize_error(last_error, self.config.api_key) if last_error else "Azure OpenAI request failed."
        response.status = "failed"
        response.complete()
        return response

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import AzureOpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is required for Azure OpenAI integration.") from exc

        self._client = AzureOpenAI(
            azure_endpoint=self.config.endpoint,
            api_key=self.config.api_key,
            api_version=self.config.api_version,
            timeout=self.config.timeout_seconds,
            max_retries=0,
        )
        return self._client

    def _populate_from_completion(self, response: LLMResponse, completion: Any) -> None:
        response.raw_text = _extract_message_content(completion)
        usage = getattr(completion, "usage", None)
        if usage is not None:
            response.prompt_tokens = getattr(usage, "prompt_tokens", None)
            response.completion_tokens = getattr(usage, "completion_tokens", None)
            response.total_tokens = getattr(usage, "total_tokens", None)


def _extract_message_content(completion: Any) -> str:
    choices = getattr(completion, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    return content or ""


def _is_retryable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    if status_code in {400, 401, 403, 404}:
        return False
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    retry_terms = ("timeout", "rate", "temporar", "server", "unavailable", "connection")
    auth_terms = ("auth", "permission", "unauthorized", "forbidden", "invalid api key")
    if any(term in name or term in text for term in auth_terms):
        return False
    return any(term in name or term in text for term in retry_terms)


def _sanitize_error(exc: Exception | None, api_key: str) -> str:
    message = str(exc) if exc is not None else "Unknown Azure OpenAI error."
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message


def _parse_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value not in (None, "") else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _parse_non_negative_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value not in (None, "") else default
    except ValueError:
        return default
    return parsed if parsed >= 0 else default


def _parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y"}
