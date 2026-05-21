"""Robust LLM service for small industry scenario planning."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import ValidationError

from procurement_data_generator.core.llm.industry_scenario_contract import (
    IndustryScenarioPlan,
    fallback_industry_scenario_plan,
)
from procurement_data_generator.core.llm.llm_client_base import LLMClientBase, LLMResponse


LLMClientFactory = Callable[[], LLMClientBase]


@dataclass(frozen=True)
class IndustryScenarioAttempt:
    """One LLM attempt while planning a small industry scenario."""

    attempt_number: int
    prompt: str
    raw_text: str
    status: str
    error_message: str | None = None
    parsed_json: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "status": self.status,
            "error_message": self.error_message,
            "raw_text": self.raw_text,
            "parsed_json": self.parsed_json,
        }


@dataclass(frozen=True)
class IndustryScenarioPlanningResult:
    """Validated scenario plan plus diagnostic report data."""

    plan: IndustryScenarioPlan
    attempts: list[IndustryScenarioAttempt] = field(default_factory=list)
    azure_openai_used: bool = True
    validation_passed: bool = False
    repair_needed: bool = False
    fallback_used: bool = False
    retry_attempts: int = 0
    validation_errors: list[str] = field(default_factory=list)

    def report(self) -> dict[str, Any]:
        return {
            "azure_openai_used": self.azure_openai_used,
            "validation_passed": self.validation_passed,
            "repair_needed": self.repair_needed,
            "fallback_used": self.fallback_used,
            "retry_attempts": self.retry_attempts,
            "validation_errors": self.validation_errors,
            "final_industry_id": self.plan.industry_id,
            "final_industry_name": self.plan.industry_name,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


class IndustryScenarioPlanningService:
    """Call an LLM for scenario hints, repair once or twice, then fallback."""

    def __init__(self, llm_client_factory: LLMClientFactory, max_repair_attempts: int = 2) -> None:
        self.llm_client_factory = llm_client_factory
        self.max_repair_attempts = max(0, max_repair_attempts)

    def generate(self, prompt: str) -> IndustryScenarioPlanningResult:
        attempts: list[IndustryScenarioAttempt] = []
        validation_errors: list[str] = []
        try:
            llm_client = self.llm_client_factory()
        except Exception as exc:
            error_message = f"LLM client initialization failed: {exc}"
            return IndustryScenarioPlanningResult(
                plan=fallback_industry_scenario_plan(error_message),
                attempts=attempts,
                validation_passed=False,
                repair_needed=False,
                fallback_used=True,
                retry_attempts=0,
                validation_errors=[error_message],
            )
        active_prompt = prompt

        for attempt_number in range(1, self.max_repair_attempts + 2):
            try:
                response = llm_client.generate_plan(active_prompt)
            except Exception as exc:
                error_message = f"LLM planning call failed: {exc}"
                attempts.append(
                    IndustryScenarioAttempt(
                        attempt_number=attempt_number,
                        prompt=active_prompt,
                        raw_text="",
                        status="failed",
                        error_message=error_message,
                        parsed_json=None,
                    )
                )
                validation_errors.append(error_message)
                if attempt_number <= self.max_repair_attempts:
                    active_prompt = self._repair_prompt(prompt, "", error_message)
                    continue
                break
            plan, error_message, parsed_json = self._parse_and_validate(response)
            attempts.append(
                IndustryScenarioAttempt(
                    attempt_number=attempt_number,
                    prompt=active_prompt,
                    raw_text=response.raw_text or "",
                    status="passed" if plan else "failed",
                    error_message=error_message,
                    parsed_json=parsed_json,
                )
            )
            if plan is not None:
                return IndustryScenarioPlanningResult(
                    plan=plan,
                    attempts=attempts,
                    validation_passed=True,
                    repair_needed=attempt_number > 1,
                    fallback_used=False,
                    retry_attempts=attempt_number - 1,
                    validation_errors=validation_errors,
                )
            if error_message:
                validation_errors.append(error_message)
            if attempt_number <= self.max_repair_attempts:
                active_prompt = self._repair_prompt(prompt, response.raw_text or "", error_message or "Unknown validation error.")

        fallback_reason = validation_errors[-1] if validation_errors else "LLM did not return a valid IndustryScenarioPlan."
        return IndustryScenarioPlanningResult(
            plan=fallback_industry_scenario_plan(fallback_reason),
            attempts=attempts,
            validation_passed=False,
            repair_needed=bool(attempts),
            fallback_used=True,
            retry_attempts=max(0, len(attempts) - 1),
            validation_errors=validation_errors,
        )

    def _parse_and_validate(self, response: LLMResponse) -> tuple[IndustryScenarioPlan | None, str | None, dict[str, Any] | None]:
        if response.status != "passed":
            return None, response.error_message or "LLM response status was not passed.", response.parsed_json
        try:
            payload = response.parsed_json
            if payload is None:
                payload = json.loads(response.extracted_json_text or response.raw_text or "")
            if not isinstance(payload, dict):
                return None, "IndustryScenarioPlan response must be a JSON object.", None
            return IndustryScenarioPlan.model_validate(payload), None, payload
        except json.JSONDecodeError as exc:
            return None, f"Invalid JSON: {exc.msg}.", None
        except ValidationError as exc:
            return None, self._validation_error_summary(exc), payload if isinstance(payload, dict) else None

    def _repair_prompt(self, original_prompt: str, raw_text: str, error_message: str) -> str:
        return "\n".join(
            [
                "Repair the previous response so it validates as IndustryScenarioPlan JSON.",
                "Return JSON only. Do not include markdown or explanation.",
                "Do not generate rows, formulas, SQL, validation rules, table names, or column names.",
                "",
                "Validation error summary:",
                error_message[:2000],
                "",
                "Original invalid response:",
                raw_text[:4000],
                "",
                "Original instructions:",
                original_prompt[:6000],
            ]
        )

    def _validation_error_summary(self, exc: ValidationError) -> str:
        messages = []
        for error in exc.errors()[:10]:
            location = ".".join(str(part) for part in error.get("loc", ()))
            message = error.get("msg", "Invalid value.")
            messages.append(f"{location}: {message}" if location else str(message))
        return "; ".join(messages) or "IndustryScenarioPlan validation failed."
