from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from procurement_data_generator.core.llm.azure_openai_client import (
    AzureOpenAIClient,
    AzureOpenAIConfig,
    AzureOpenAIConfigError,
)


def _config(api_key: str = "secret-key") -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        endpoint="https://example.openai.azure.com",
        api_key=api_key,
        deployment="plan-deployment",
        api_version="2024-02-15-preview",
        max_retries=0,
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeRetryableError(Exception):
    status_code = 429


class FakeAuthError(Exception):
    status_code = 401


def _completion(text: str, prompt_tokens: int = 10, completion_tokens: int = 20):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def test_missing_config_fails_clearly() -> None:
    with pytest.raises(AzureOpenAIConfigError) as exc:
        AzureOpenAIConfig.from_mapping({})

    assert "AZURE_OPENAI_ENDPOINT" in exc.value.missing
    assert "AZURE_OPENAI_API_KEY" in exc.value.missing
    assert "AZURE_OPENAI_DEPLOYMENT" in exc.value.missing


def test_client_sends_prompt_to_mocked_azure_openai() -> None:
    fake = FakeClient([_completion('{"module": "procurement"}')])
    response = AzureOpenAIClient(_config(), openai_client=fake).generate_plan("Build a plan.")

    assert response.status == "passed"
    assert fake.completions.calls[0]["model"] == "plan-deployment"
    assert fake.completions.calls[0]["messages"][1]["content"] == "Build a plan."


def test_generate_plan_uses_generic_mes_system_message() -> None:
    fake = FakeClient([_completion('{"module": "procurement"}')])

    AzureOpenAIClient(_config(), openai_client=fake).generate_plan("Build a plan.")

    system_message = fake.completions.calls[0]["messages"][0]["content"]
    assert "MES synthetic data planning assistant" in system_message
    assert "procurement data planning assistant" not in system_message
    assert "Do not generate raw rows, CSV data, SQL inserts, Python code, or markdown." in system_message


def test_core_llm_layer_does_not_use_procurement_specific_system_prompt() -> None:
    llm_folder = Path(__file__).resolve().parents[1] / "procurement_data_generator" / "core" / "llm"
    core_llm_text = "\n".join(path.read_text(encoding="utf-8") for path in llm_folder.glob("*.py"))

    assert "procurement data planning assistant" not in core_llm_text


def test_raw_response_and_extracted_json_are_captured() -> None:
    fake = FakeClient([_completion('```json\n{"module": "procurement"}\n```')])
    response = AzureOpenAIClient(_config(), openai_client=fake).generate_plan("Build a plan.")

    assert response.raw_text.startswith("```json")
    assert response.extracted_json_text == '{"module": "procurement"}'
    assert response.parsed_json == {"module": "procurement"}
    assert response.total_tokens == 30


def test_retry_behavior_for_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr("procurement_data_generator.core.llm.azure_openai_client.time.sleep", lambda *_args: None)
    config = AzureOpenAIConfig(
        endpoint="https://example.openai.azure.com",
        api_key="secret-key",
        deployment="plan-deployment",
        max_retries=1,
    )
    fake = FakeClient([FakeRetryableError("rate limit"), _completion('{"module": "procurement"}')])

    response = AzureOpenAIClient(config, openai_client=fake).generate_plan("Build a plan.")

    assert response.status == "passed"
    assert response.retry_count == 1
    assert len(fake.completions.calls) == 2


def test_api_key_is_not_printed_in_error_output() -> None:
    fake = FakeClient([FakeAuthError("bad key secret-key")])
    response = AzureOpenAIClient(_config(api_key="secret-key"), openai_client=fake).generate_plan("Build a plan.")

    assert response.status == "failed"
    assert "secret-key" not in (response.error_message or "")
    assert "[REDACTED]" in (response.error_message or "")


def test_invalid_json_response_returns_failed_status() -> None:
    fake = FakeClient([_completion("not json")])
    response = AzureOpenAIClient(_config(), openai_client=fake).generate_plan("Build a plan.")

    assert response.status == "failed"
    assert "JSON" in (response.error_message or "")


def test_auth_error_is_not_retried() -> None:
    config = AzureOpenAIConfig(
        endpoint="https://example.openai.azure.com",
        api_key="secret-key",
        deployment="plan-deployment",
        max_retries=2,
    )
    fake = FakeClient([FakeAuthError("unauthorized")])

    response = AzureOpenAIClient(config, openai_client=fake).generate_plan("Build a plan.")

    assert response.status == "failed"
    assert len(fake.completions.calls) == 1
