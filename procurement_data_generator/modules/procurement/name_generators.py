"""Universal domain-aware name generators for procurement data."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Iterable

from faker import Faker

from procurement_data_generator.core.contracts.llm_plan_contract import DomainProfile, MaterialCategory
from procurement_data_generator.modules.shared.industry_profiles.profile_contract import IndustryProfile
from procurement_data_generator.modules.shared.industry_profiles.profile_loader import get_default_industry_profile


ARTIFICIAL_NUMERIC_SUFFIX_PATTERN = re.compile(r"\s(?:[1-9]|[1-9][0-9])$")


class NameGenerationError(ValueError):
    """Raised when unique realistic names cannot be generated safely."""


@dataclass(frozen=True)
class FallbackMaterialCatalog:
    """Fallback material catalog for a procurement industry family."""

    keywords: tuple[str, ...]
    categories: tuple[MaterialCategory, ...]


def _profile_material_categories(profile: IndustryProfile) -> tuple[MaterialCategory, ...]:
    procurement = profile.procurement
    categories: list[MaterialCategory] = []
    for category_name, examples in procurement.component_material_examples.items():
        specs = procurement.component_specification_patterns.get(category_name, ())
        categories.append(
            MaterialCategory(
                category_name=category_name,
                material_examples=list(examples),
                specification_patterns=list(specs),
            )
        )
    if categories:
        return tuple(categories)
    return tuple(
        MaterialCategory(
            category_name=category_name,
            material_examples=list(procurement.component_name_patterns),
            specification_patterns=["Industrial Grade", "Standard Pack", "Grade A"],
        )
        for category_name in procurement.component_categories
    )


_DEFAULT_INDUSTRY_PROFILE = get_default_industry_profile()


INDUSTRY_MATERIAL_FALLBACKS: dict[str, FallbackMaterialCatalog] = {
    "ev": FallbackMaterialCatalog(
        keywords=("ev", "electric vehicle", "battery", "mobility"),
        categories=_profile_material_categories(_DEFAULT_INDUSTRY_PROFILE),
    ),
    "pharma": FallbackMaterialCatalog(
        keywords=("pharma", "pharmaceutical", "healthcare", "medicine"),
        categories=(
            MaterialCategory(
                category_name="Pharmaceutical Materials",
                material_examples=["Active Pharmaceutical Ingredient", "Excipient Powder", "Sterile Vial", "Blister Packaging Foil"],
                specification_patterns=["Grade A", "USP Grade", "10ml", "Analytical Grade", "Sterile"],
            ),
            MaterialCategory(
                category_name="Laboratory Supplies",
                material_examples=["Laboratory Reagent", "Culture Media", "Filter Membrane", "Glass Ampoule"],
                specification_patterns=["HPLC Grade", "0.22 Micron", "500ml", "Class A"],
            ),
        ),
    ),
    "semiconductor": FallbackMaterialCatalog(
        keywords=("semiconductor", "chip", "wafer", "microelectronics"),
        categories=(
            MaterialCategory(
                category_name="Semiconductor Materials",
                material_examples=["Silicon Wafer", "Photoresist Chemical", "Etching Gas Cylinder", "CMP Slurry"],
                specification_patterns=["300mm", "Grade A", "Ultra High Purity", "193nm", "Cleanroom Grade"],
            ),
            MaterialCategory(
                category_name="Cleanroom Supplies",
                material_examples=["Cleanroom Gloves", "Wafer Carrier", "Lint-Free Wiper", "Static Shielding Bag"],
                specification_patterns=["Nitrile", "Class 100", "8 inch", "ESD Safe"],
            ),
        ),
    ),
    "food": FallbackMaterialCatalog(
        keywords=("food", "beverage", "fmcg", "ingredient"),
        categories=(
            MaterialCategory(
                category_name="Food Ingredients",
                material_examples=["Refined Sugar", "Wheat Flour", "Food Grade Preservative", "Vegetable Oil"],
                specification_patterns=["50kg", "Grade A", "Food Grade", "25kg", "Low Moisture"],
            ),
            MaterialCategory(
                category_name="Food Packaging",
                material_examples=["Packaging Film Roll", "Corrugated Carton", "PET Bottle Preform", "Aluminium Foil Lid"],
                specification_patterns=["Micron 60", "Food Safe", "1 Liter", "Printed"],
            ),
        ),
    ),
    "furniture": FallbackMaterialCatalog(
        keywords=("furniture", "wood", "upholstery", "interior"),
        categories=(
            MaterialCategory(
                category_name="Furniture Materials",
                material_examples=["Teak Wood Panel", "Upholstery Fabric Roll", "Steel Hinge Set", "Wood Adhesive"],
                specification_patterns=["Industrial Grade", "18mm", "Premium Finish", "Heavy Duty", "Waterproof"],
            ),
            MaterialCategory(
                category_name="Furniture Hardware",
                material_examples=["Drawer Slide", "Furniture Foam Sheet", "Laminate Board", "Edge Banding Tape"],
                specification_patterns=["Soft Close", "High Density", "Matte Finish", "22mm"],
            ),
        ),
    ),
    "textile": FallbackMaterialCatalog(
        keywords=("textile", "garment", "fabric", "apparel"),
        categories=(
            MaterialCategory(
                category_name="Textile Materials",
                material_examples=["Cotton Yarn", "Polyester Fabric Roll", "Dye Chemical", "Elastic Tape"],
                specification_patterns=["40s Count", "GSM 180", "Reactive Grade", "25mm", "Colorfast"],
            ),
            MaterialCategory(
                category_name="Garment Trims",
                material_examples=["Zipper Coil", "Button Set", "Sewing Thread", "Care Label Roll"],
                specification_patterns=["Nylon", "Matte Finish", "Tex 40", "Printed"],
            ),
        ),
    ),
    "automotive": FallbackMaterialCatalog(
        keywords=("automotive", "auto", "vehicle", "component"),
        categories=(
            MaterialCategory(
                category_name="Automotive Components",
                material_examples=["Brake Pad Set", "Stamped Bracket", "Engine Gasket", "Rubber Bushing"],
                specification_patterns=["Automotive Grade", "Heat Resistant", "Zinc Plated", "Heavy Duty"],
            ),
            MaterialCategory(
                category_name="Automotive Materials",
                material_examples=["Sheet Metal Coil", "Coolant Additive", "Fastener Kit", "Wiring Connector"],
                specification_patterns=["CRCA", "Long Life", "M8", "IP67"],
            ),
        ),
    ),
    "electronics": FallbackMaterialCatalog(
        keywords=("electronics", "electronic", "pcb", "device"),
        categories=(
            MaterialCategory(
                category_name="Electronics Components",
                material_examples=["Printed Circuit Board", "Ceramic Capacitor", "Microcontroller IC", "Solder Paste"],
                specification_patterns=["FR4", "10uF", "32-bit", "Lead Free", "RoHS"],
            ),
            MaterialCategory(
                category_name="Electronic Assemblies",
                material_examples=["Display Module", "Power Adapter", "Sensor Cable", "Connector Header"],
                specification_patterns=["OLED", "24V", "Shielded", "2.54mm"],
            ),
        ),
    ),
    "construction": FallbackMaterialCatalog(
        keywords=("construction", "building", "civil", "infrastructure"),
        categories=(
            MaterialCategory(
                category_name="Construction Materials",
                material_examples=["Reinforced Steel Bar", "Portland Cement", "PVC Pipe", "Safety Helmet"],
                specification_patterns=["12mm", "50kg", "2 inch", "Industrial Grade", "ISI Marked"],
            ),
            MaterialCategory(
                category_name="Site Supplies",
                material_examples=["Concrete Admixture", "Plywood Sheet", "Electrical Conduit", "Anchor Bolt"],
                specification_patterns=["M25 Grade", "18mm", "Heavy Duty", "Galvanized"],
            ),
        ),
    ),
    "it_office": FallbackMaterialCatalog(
        keywords=("it", "office", "software", "cloud", "workstation"),
        categories=(
            MaterialCategory(
                category_name="IT and Office Supplies",
                material_examples=["Laptop Workstation", "Cloud Software License", "Network Switch", "Office Chair"],
                specification_patterns=["i7", "Annual Subscription", "24 Port", "Ergonomic", "Enterprise"],
            ),
            MaterialCategory(
                category_name="Office Infrastructure",
                material_examples=["Docking Station", "Wireless Access Point", "Monitor Display", "Printer Toner"],
                specification_patterns=["USB-C", "WiFi 6", "27 inch", "High Yield"],
            ),
        ),
    ),
    "general": FallbackMaterialCatalog(
        keywords=("general", "manufacturing", "industrial", "procurement"),
        categories=(
            MaterialCategory(
                category_name="Raw Materials",
                material_examples=["Industrial Sheet Metal", "Engineering Polymer", "Rubber Seal", "Fastener Kit"],
                specification_patterns=["Grade A", "Heavy Duty", "Standard Pack", "Industrial Grade"],
            ),
            MaterialCategory(
                category_name="Maintenance Spares",
                material_examples=["Bearing Assembly", "Pneumatic Valve", "Safety Gloves", "Cutting Tool"],
                specification_patterns=["High Load", "1/2 inch", "Nitrile", "Carbide"],
            ),
            MaterialCategory(
                category_name="Office and IT Supplies",
                material_examples=["Printer Toner", "Network Cable", "Office Chair", "Laptop Adapter"],
                specification_patterns=["High Yield", "CAT6", "Ergonomic", "65W"],
            ),
        ),
    ),
}

GENERIC_MATERIAL_CATEGORIES = (
    MaterialCategory(
        category_name="Raw Materials",
        material_examples=["Industrial Sheet Metal", "Engineering Polymer", "Rubber Seal", "Standard Fastener"],
        specification_patterns=["Grade A", "Heavy Duty", "Standard Pack", "Industrial Grade"],
    ),
    MaterialCategory(
        category_name="Electrical Components",
        material_examples=["Control Cable", "Circuit Breaker", "Terminal Block", "Power Connector"],
        specification_patterns=["24V", "DIN Rail", "10A", "IP67"],
    ),
    MaterialCategory(
        category_name="Mechanical Components",
        material_examples=["Bearing Assembly", "Gear Coupling", "Pneumatic Valve", "Drive Belt"],
        specification_patterns=["High Load", "Precision", "1/2 inch", "Reinforced"],
    ),
    MaterialCategory(
        category_name="Packaging Materials",
        material_examples=["Corrugated Carton", "Packaging Film Roll", "Pallet Wrap", "Label Roll"],
        specification_patterns=["Heavy Duty", "Printed", "Food Safe", "Standard Size"],
    ),
    MaterialCategory(
        category_name="Safety Supplies",
        material_examples=["Safety Gloves", "Protective Helmet", "Face Shield", "Safety Harness"],
        specification_patterns=["Nitrile", "Industrial Grade", "Clear", "Heavy Duty"],
    ),
)


class ProcurementNameGenerator:
    """Generate unique procurement names from domain profile context."""

    brand_prefixes = (
        "Apex",
        "Nova",
        "Vertex",
        "Orion",
        "Zenith",
        "Summit",
        "Trident",
        "BluePeak",
        "Quantum",
        "Prime",
        "Sterling",
        "Nexa",
        "Vantage",
        "Optima",
        "Pioneer",
        "Radiant",
        "Atlas",
        "Terra",
        "Coreline",
        "Hexa",
    )
    universal_vendor_terms = (
        "Industrial",
        "Precision",
        "Component",
        "Packaging",
        "Materials",
        "Supply",
        "Engineering",
        "Automation",
        "Electrical",
        "Mechanical",
        "Safety",
        "Laboratory",
        "Food",
        "Chemical",
        "Textile",
        "Construction",
        "Office",
        "Technology",
        "Alloy",
        "Logistics",
    )
    business_types = (
        "Components",
        "Systems",
        "Supplies",
        "Manufacturing",
        "Industries",
        "Technologies",
        "Materials",
        "Solutions",
        "Fabrication",
        "Works",
        "Corporation",
        "Enterprises",
        "Traders",
        "Distributors",
    )
    plant_types = (
        "Manufacturing Plant",
        "Assembly Plant",
        "Component Facility",
        "Production Site",
        "Fabrication Unit",
        "Processing Plant",
        "Operations Facility",
    )
    fallback_locations = (
        "Bengaluru",
        "Pune",
        "Chennai",
        "Hosur",
        "Hyderabad",
        "Ahmedabad",
        "Mysuru",
        "Coimbatore",
        "Gurugram",
        "Noida",
        "Surat",
        "Vadodara",
        "Nashik",
        "Indore",
        "Jaipur",
    )
    fallback_warehouse_types = (
        *_DEFAULT_INDUSTRY_PROFILE.procurement.warehouse_type_names,
    )
    material_modifiers = (
        "",
        "Premium",
        "Industrial",
        "Standard",
        "Certified",
        "High Purity",
        "Heavy Duty",
        "Precision",
        "Process Grade",
        "Commercial",
    )
    material_packaging = (
        "",
        "Bulk Pack",
        "Standard Pack",
        "Production Pack",
        "Supplier Pack",
        "Sealed Pack",
    )

    def generate_vendor_names(
        self,
        count: int,
        domain_profile: DomainProfile,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        rng = random.Random(seed)
        terms = self._vendor_terms(domain_profile)
        candidates = [
            f"{prefix} {term} {business_type}"
            for prefix in self.brand_prefixes
            for term in terms
            for business_type in self.business_types
        ]
        return self._select_unique(candidates, count, "vendor names", rng, existing_names)

    def generate_material_names(
        self,
        count: int,
        domain_profile: DomainProfile,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        rng = random.Random(seed)
        categories = self._material_categories(domain_profile, minimum_count=count)
        candidates: list[str] = []
        for category in categories:
            examples = [value.strip() for value in category.material_examples if value.strip()]
            specs = [value.strip() for value in category.specification_patterns if value.strip()]
            if not specs:
                specs = ["Industrial Grade", "Standard Pack", "Grade A"]
            for example in examples:
                candidates.append(example)
                for spec in specs:
                    candidates.append(f"{example} {spec}")
                    for modifier in self.material_modifiers:
                        if modifier:
                            candidates.append(f"{modifier} {example} {spec}")
                    for packaging in self.material_packaging:
                        if packaging:
                            candidates.append(f"{example} {spec} {packaging}")
                candidates.append(f"{category.category_name} {example}")

        return self._select_unique(candidates, count, "material names", rng, existing_names)

    def generate_plant_names(
        self,
        count: int,
        domain_profile: DomainProfile,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        rng = random.Random(seed)
        locations = self._values_or_fallback(domain_profile.plant_locations, self.fallback_locations)
        candidates = [f"{location} {plant_type}" for location in locations for plant_type in self.plant_types]
        return self._select_unique(candidates, count, "plant names", rng, existing_names)

    def generate_warehouse_names(
        self,
        count: int,
        domain_profile: DomainProfile,
        plant_names: list[str] | None = None,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        rng = random.Random(seed)
        bases = self._warehouse_bases(domain_profile, plant_names)
        warehouse_types = self._warehouse_types(domain_profile)
        candidates = [f"{base} {warehouse_type}" for base in bases for warehouse_type in warehouse_types]
        return self._select_unique(candidates, count, "warehouse names", rng, existing_names)

    def generate_faker_person_names(
        self,
        count: int,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        faker = Faker()
        if seed is not None:
            faker.seed_instance(seed)
        candidates = self._faker_candidates(lambda: faker.name(), count, "faker person names", existing_names)
        return self.ensure_unique_names(candidates, count, "faker person names", existing_names)

    def generate_faker_company_names(
        self,
        count: int,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        faker = Faker()
        if seed is not None:
            faker.seed_instance(seed)
        candidates = self._faker_candidates(lambda: faker.company(), count, "faker company names", existing_names)
        return self.ensure_unique_names(candidates, count, "faker company names", existing_names)

    def generate_carrier_names(
        self,
        count: int,
        domain_profile: DomainProfile,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        rng = random.Random(seed)
        patterns = self._values_or_fallback(
            domain_profile.carrier_name_patterns,
            ("Regional Freight", "Express Logistics", "Industrial Transport", "Certified Cargo"),
        )
        candidates = [
            f"{prefix} {self._title_term(pattern)}"
            for prefix in self.brand_prefixes
            for pattern in patterns
        ]
        return self._select_unique(candidates, count, "carrier names", rng, existing_names)

    def generate_inspection_test_names(
        self,
        count: int,
        domain_profile: DomainProfile,
        seed: int | None = None,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        rng = random.Random(seed)
        categories = self._values_or_fallback(
            domain_profile.inspection_test_categories,
            ("Dimensional Inspection", "Visual Inspection", "Material Verification", "Functional Test"),
        )
        qualifiers = ("Standard", "Incoming", "Batch", "Supplier", "Final")
        candidates = [f"{qualifier} {category}" for qualifier in qualifiers for category in categories]
        return self._select_unique(candidates, count, "inspection test names", rng, existing_names)

    def ensure_unique_names(
        self,
        names: list[str],
        expected_count: int,
        entity_type: str,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        existing = existing_names or set()
        selected: list[str] = []
        seen = set(existing)
        for name in names:
            clean_name = _clean_name(name)
            if not clean_name or clean_name in seen or self._has_artificial_numeric_suffix(clean_name):
                continue
            selected.append(clean_name)
            seen.add(clean_name)
            if len(selected) == expected_count:
                return selected

        raise NameGenerationError(
            f"Unable to generate {expected_count} unique {entity_type} without artificial suffixes. "
            "Increase domain profile variety or lower target count."
        )

    def _select_unique(
        self,
        candidates: Iterable[str],
        count: int,
        entity_type: str,
        rng: random.Random,
        existing_names: set[str] | None = None,
    ) -> list[str]:
        if count < 0:
            raise NameGenerationError(f"Requested count for {entity_type} must not be negative.")
        if count == 0:
            return []
        candidate_list = list(dict.fromkeys(_clean_name(name) for name in candidates if _clean_name(name)))
        rng.shuffle(candidate_list)
        return self.ensure_unique_names(candidate_list, count, entity_type, existing_names)

    def _faker_candidates(
        self,
        generator,
        count: int,
        entity_type: str,
        existing_names: set[str] | None,
    ) -> list[str]:
        max_attempts = max(count * 20, 100)
        existing = existing_names or set()
        candidates: list[str] = []
        seen = set(existing)
        for _ in range(max_attempts):
            name = _clean_name(generator())
            if name and name not in seen and not self._has_artificial_numeric_suffix(name):
                candidates.append(name)
                seen.add(name)
                if len(candidates) == count:
                    return candidates
        raise NameGenerationError(
            f"Unable to generate {count} unique {entity_type} without artificial suffixes. "
            "Increase max attempts, lower target count, or provide more variety."
        )

    def _vendor_terms(self, domain_profile: DomainProfile) -> list[str]:
        profile_terms: list[str] = []
        profile_terms.extend(self._term_tokens(domain_profile.vendor_categories))
        profile_terms.extend(self._term_tokens([domain_profile.industry]))
        profile_terms.extend(self._term_tokens(category.category_name for category in domain_profile.material_categories))
        terms = _dedupe_preserve_order([self._title_term(term) for term in profile_terms if term])
        if len(terms) < 5:
            terms = _dedupe_preserve_order([*terms, *self.universal_vendor_terms])
        return terms

    def _material_categories(self, domain_profile: DomainProfile, minimum_count: int) -> list[MaterialCategory]:
        rich_categories = [
            category
            for category in domain_profile.material_categories
            if category.material_examples and category.specification_patterns
        ]
        categories = list(rich_categories)
        if len(self._material_candidate_preview(categories)) < minimum_count:
            categories.extend(self._fallback_categories_for_industry(domain_profile.industry))
        if not categories:
            categories = list(GENERIC_MATERIAL_CATEGORIES)
        return categories

    def _fallback_categories_for_industry(self, industry: str) -> list[MaterialCategory]:
        normalized = industry.lower()
        for key, catalog in INDUSTRY_MATERIAL_FALLBACKS.items():
            if key == "general":
                continue
            if any(keyword in normalized for keyword in catalog.keywords):
                return list(catalog.categories)
        return list(INDUSTRY_MATERIAL_FALLBACKS["general"].categories)

    def _material_candidate_preview(self, categories: list[MaterialCategory]) -> list[str]:
        candidates = []
        for category in categories:
            for example in category.material_examples:
                candidates.append(example)
                for spec in category.specification_patterns:
                    candidates.append(f"{example} {spec}")
                    for modifier in self.material_modifiers:
                        if modifier:
                            candidates.append(f"{modifier} {example} {spec}")
                    for packaging in self.material_packaging:
                        if packaging:
                            candidates.append(f"{example} {spec} {packaging}")
                candidates.append(f"{category.category_name} {example}")
        return candidates

    def _warehouse_bases(self, domain_profile: DomainProfile, plant_names: list[str] | None) -> list[str]:
        if plant_names:
            return _dedupe_preserve_order([_plant_base_name(name) for name in plant_names if _plant_base_name(name)])
        return self._values_or_fallback(domain_profile.plant_locations, self.fallback_locations)

    def _warehouse_types(self, domain_profile: DomainProfile) -> list[str]:
        values = self._values_or_fallback(domain_profile.warehouse_types, self.fallback_warehouse_types)
        normalized = []
        for value in values:
            title = self._title_term(value)
            if "warehouse" not in title.lower():
                title = f"{title} Warehouse"
            normalized.append(title)
        return _dedupe_preserve_order(normalized)

    def _values_or_fallback(self, values: Iterable[str], fallback: Iterable[str]) -> list[str]:
        cleaned = [_clean_name(value) for value in values if _clean_name(value)]
        return _dedupe_preserve_order(cleaned or list(fallback))

    def _term_tokens(self, values: Iterable[str]) -> list[str]:
        tokens: list[str] = []
        stopwords = {"and", "for", "the", "of", "procurement", "manufacturing", "supplier", "suppliers"}
        for value in values:
            for token in re.split(r"[/,&\- ]+", value):
                token = token.strip()
                if len(token) > 2 and token.lower() not in stopwords:
                    tokens.append(token)
        return tokens

    def _title_term(self, value: str) -> str:
        return " ".join(part.capitalize() if part.islower() else part for part in value.split())

    def _has_artificial_numeric_suffix(self, name: str) -> bool:
        return bool(ARTIFICIAL_NUMERIC_SUFFIX_PATTERN.search(name))


def _plant_base_name(plant_name: str) -> str:
    suffixes = (
        " Manufacturing Plant",
        " Assembly Plant",
        " Component Facility",
        " Production Site",
        " Fabrication Unit",
        " Processing Plant",
        " Operations Facility",
    )
    for suffix in suffixes:
        if plant_name.endswith(suffix):
            return plant_name[: -len(suffix)]
    return plant_name.split()[0] if plant_name.split() else ""


def _clean_name(name: str) -> str:
    return " ".join(str(name).split())


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
