"""Generate and validate an industry profile JSON artifact with Azure OpenAI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.llm.azure_openai_client import AzureOpenAIClient, AzureOpenAIConfig, AzureOpenAIConfigError
from procurement_data_generator.modules.shared.industry_profiles import (
    industry_profile_to_dict,
    load_industry_profile_from_dict,
    validate_industry_profile,
)
from procurement_data_generator.modules.shared.industry_profiles.profile_prompt_builder import build_industry_profile_prompt


SYSTEM_MESSAGE = (
    "You generate industry profile JSON only. Do not include markdown or explanations. "
    "Do not generate table rows, CSV rows, transactional data, or synthetic records."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an industry profile JSON using Azure OpenAI.")
    parser.add_argument("--industry", required=True, help="Industry name, for example Food Manufacturing.")
    parser.add_argument("--description", help="Optional additional business context.")
    parser.add_argument("--profile-id", help="Optional snake_case industry_id to request from Azure OpenAI.")
    parser.add_argument("--output", required=True, help="Output path for validated profile JSON.")
    parser.add_argument("--save-raw-response", action="store_true", help="Save raw Azure OpenAI response beside the output JSON.")
    parser.add_argument("--prompt-output", help="Optional path to save the prompt.")
    parser.add_argument("--env", help="Optional .env file path.")
    args = parser.parse_args()

    prompt = build_industry_profile_prompt(args.industry, description=args.description, profile_id=args.profile_id)
    if args.prompt_output:
        _write_text(args.prompt_output, prompt)

    try:
        config = AzureOpenAIConfig.from_env(args.env)
    except AzureOpenAIConfigError as exc:
        print("Azure OpenAI configuration missing.")
        print(f"Missing: {', '.join(exc.missing)}")
        print("Status: failed")
        return 1

    response = AzureOpenAIClient(config).generate_json(prompt, system_message=SYSTEM_MESSAGE)
    output_path = Path(args.output)
    if args.save_raw_response:
        _write_text(output_path.with_suffix(".raw_response.txt"), response.raw_text)

    if response.status != "passed" or response.parsed_json is None:
        _write_json(output_path.with_suffix(".llm_response_report.json"), response.to_dict())
        print("Azure OpenAI industry profile generation failed.")
        print(f"Provider: {response.provider}")
        print(f"Deployment: {response.deployment}")
        print(f"Error: {response.error_message}")
        print("Status: failed")
        return 1

    try:
        profile = load_industry_profile_from_dict(response.parsed_json)
    except ValueError as exc:
        _write_json(output_path.with_suffix(".llm_response_report.json"), response.to_dict())
        print("Generated industry profile failed validation.")
        print(str(exc))
        print("Status: failed")
        return 1

    validation = validate_industry_profile(profile)
    _write_json(output_path, industry_profile_to_dict(profile))
    _write_json(output_path.with_suffix(".llm_response_report.json"), response.to_dict())

    print("Azure OpenAI industry profile generation completed.")
    print(f"Provider: {response.provider}")
    print(f"Deployment: {response.deployment}")
    print(f"Profile JSON: {output_path}")
    print(f"Validation status: {'passed' if validation.valid else 'failed'}")
    print(f"Validation errors: {len(validation.errors)}")
    print(f"Validation warnings: {len(validation.warnings)}")
    print("Rows generated: 0")
    print(f"Status: {'passed' if validation.valid else 'failed'}")
    return 0 if validation.valid else 1


def _write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
