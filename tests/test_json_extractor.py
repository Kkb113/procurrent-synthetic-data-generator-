from __future__ import annotations

from procurement_data_generator.core.llm.json_extractor import extract_json_object


def test_extracts_pure_json() -> None:
    result = extract_json_object('{"module": "procurement"}')

    assert result.success
    assert result.parsed_json == {"module": "procurement"}


def test_extracts_json_from_json_fence() -> None:
    result = extract_json_object('```json\n{"module": "procurement"}\n```')

    assert result.success
    assert result.parsed_json == {"module": "procurement"}


def test_extracts_json_from_generic_fence() -> None:
    result = extract_json_object('```\n{"module": "procurement"}\n```')

    assert result.success
    assert result.parsed_json == {"module": "procurement"}


def test_extracts_json_with_surrounding_whitespace() -> None:
    result = extract_json_object('\n\n  {"module": "procurement"}  \n')

    assert result.success
    assert result.parsed_json == {"module": "procurement"}


def test_fails_on_malformed_json() -> None:
    result = extract_json_object('{"module": "procurement",}')

    assert not result.success
    assert "Invalid JSON" in (result.error_message or "")


def test_fails_when_no_json_object_exists() -> None:
    result = extract_json_object("There is no JSON here.")

    assert not result.success
    assert "No JSON object" in (result.error_message or "")


def test_extracts_first_top_level_object_with_surrounding_text() -> None:
    result = extract_json_object('Here is the plan: {"module": "procurement", "nested": {"ok": true}} Thanks.')

    assert result.success
    assert result.parsed_json == {"module": "procurement", "nested": {"ok": True}}
