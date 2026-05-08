"""Safe JSON extraction helpers for LLM responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JSONExtractionResult:
    """Result of extracting a JSON object from model output."""

    success: bool
    json_text: str | None = None
    parsed_json: dict[str, Any] | None = None
    error_message: str | None = None


def extract_json_object(text: str | None) -> JSONExtractionResult:
    """Extract the first valid top-level JSON object from text.

    The extractor accepts strict JSON, fenced JSON, and responses with light
    surrounding text. It does not repair malformed JSON.
    """

    if text is None or not text.strip():
        return JSONExtractionResult(success=False, error_message="LLM response was empty.")
    if "{" not in text:
        return JSONExtractionResult(success=False, error_message="No JSON object found in LLM response.")

    candidates = _candidate_texts(text)
    seen: set[str] = set()
    last_error = ""

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = f"Invalid JSON: {exc.msg}."
            continue
        if not isinstance(parsed, dict):
            return JSONExtractionResult(success=False, error_message="Extracted JSON is not a top-level object.")
        return JSONExtractionResult(success=True, json_text=candidate, parsed_json=parsed)

    object_candidate = _find_first_json_object(text)
    if object_candidate:
        try:
            parsed = json.loads(object_candidate)
        except json.JSONDecodeError as exc:
            return JSONExtractionResult(success=False, error_message=f"Invalid JSON object: {exc.msg}.")
        if not isinstance(parsed, dict):
            return JSONExtractionResult(success=False, error_message="Extracted JSON is not a top-level object.")
        return JSONExtractionResult(success=True, json_text=object_candidate, parsed_json=parsed)

    return JSONExtractionResult(success=False, error_message=last_error or "No JSON object found in LLM response.")


def _candidate_texts(text: str) -> list[str]:
    candidates = [text.strip()]
    fence_pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
    candidates.extend(match.group(1).strip() for match in fence_pattern.finditer(text))
    return candidates


def _find_first_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        candidate = _scan_object_from(text, start)
        if candidate:
            return candidate
        start = text.find("{", start + 1)
    return None


def _scan_object_from(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1].strip()
            if depth < 0:
                return None

    return None
