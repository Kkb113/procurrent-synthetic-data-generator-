"""Demo script for Phase 7 procurement name generation."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from procurement_data_generator.core.llm.plan_loader import format_llm_plan_validation_result, load_llm_plan_json
from procurement_data_generator.modules.procurement.name_generators import ProcurementNameGenerator


ARTIFICIAL_SUFFIX_PATTERN = re.compile(r"\s(?:[1-9]|[1-9][0-9])$")


def main() -> int:
    """Load a sample plan and generate representative procurement names."""

    parser = argparse.ArgumentParser(description="Run Phase 7 domain-aware name generation demo.")
    parser.add_argument("--plan", required=True, help="Path to a valid LLM generation plan JSON file.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic generation seed.")
    args = parser.parse_args()

    plan_result = load_llm_plan_json(args.plan)
    if not plan_result.report.is_valid or plan_result.plan is None:
        print(format_llm_plan_validation_result(plan_result))
        return 1

    profile = plan_result.plan.domain_profile
    generator = ProcurementNameGenerator()
    vendors = generator.generate_vendor_names(50, profile, seed=args.seed)
    materials = generator.generate_material_names(200, profile, seed=args.seed)
    plants = generator.generate_plant_names(2, profile, seed=args.seed)
    warehouses = generator.generate_warehouse_names(6, profile, plant_names=plants, seed=args.seed)
    people = generator.generate_faker_person_names(10, seed=args.seed)
    companies = generator.generate_faker_company_names(10, seed=args.seed)

    all_names = vendors + materials + plants + warehouses + people + companies
    duplicate_count = len(all_names) - len(set(all_names))
    suffix_count = sum(1 for name in all_names if ARTIFICIAL_SUFFIX_PATTERN.search(name))

    print("Domain-aware name generation completed.")
    print(f"Industry: {profile.industry}")
    print(f"Vendor names generated: {len(vendors)}")
    print(f"Material names generated: {len(materials)}")
    print(f"Plant names generated: {len(plants)}")
    print(f"Warehouse names generated: {len(warehouses)}")
    print(f"Faker person names generated: {len(people)}")
    print(f"Faker company names generated: {len(companies)}")
    print(f"Duplicates found: {duplicate_count}")
    print(f"Artificial numeric suffixes found: {suffix_count}")
    print(f"Validation status: {'passed' if duplicate_count == 0 and suffix_count == 0 else 'failed'}")
    print("")
    _print_sample("Sample vendors", vendors)
    _print_sample("Sample materials", materials)
    _print_sample("Sample plants", plants)
    _print_sample("Sample warehouses", warehouses)
    return 0 if duplicate_count == 0 and suffix_count == 0 else 1


def _print_sample(title: str, names: list[str]) -> None:
    print(f"{title}:")
    for name in names[:3]:
        print(f"- {name}")


if __name__ == "__main__":
    raise SystemExit(main())
