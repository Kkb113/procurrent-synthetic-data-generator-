"""Small LLM contract for industry scenario planning."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SupportedDomain = Literal["procurement", "production", "sales"]
RowVolumeIntent = Literal["small", "standard", "analytics"]


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(item).strip() for item in value]
    else:
        raw_values = [str(value).strip()]
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        text = " ".join(raw_value.split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


class ScenarioModel(BaseModel):
    """Base model for forgiving scenario-plan parsing."""

    model_config = ConfigDict(extra="ignore")


class ProcurementScenarioHints(ScenarioModel):
    supplier_types: list[str] = Field(default_factory=list)
    component_categories: list[str] = Field(default_factory=list)
    raw_material_terms: list[str] = Field(default_factory=list)
    purchasing_patterns: list[str] = Field(default_factory=list)
    supplier_risk_factors: list[str] = Field(default_factory=list)
    inspection_or_quality_hints: list[str] = Field(default_factory=list)

    _clean_lists = field_validator("*", mode="before")(_normalize_string_list)


class ProductionScenarioHints(ScenarioModel):
    product_families: list[str] = Field(default_factory=list)
    production_process_terms: list[str] = Field(default_factory=list)
    work_center_terms: list[str] = Field(default_factory=list)
    routing_patterns: list[str] = Field(default_factory=list)
    scrap_or_yield_hints: list[str] = Field(default_factory=list)
    finished_good_terms: list[str] = Field(default_factory=list)

    _clean_lists = field_validator("*", mode="before")(_normalize_string_list)


class SalesScenarioHints(ScenarioModel):
    customer_types: list[str] = Field(default_factory=list)
    customer_industries: list[str] = Field(default_factory=list)
    sales_channels: list[str] = Field(default_factory=list)
    demand_patterns: list[str] = Field(default_factory=list)
    payment_terms: list[str] = Field(default_factory=list)
    return_reasons: list[str] = Field(default_factory=list)
    region_terms: list[str] = Field(default_factory=list)

    _clean_lists = field_validator("*", mode="before")(_normalize_string_list)


class SharedScenarioHints(ScenarioModel):
    geography_terms: list[str] = Field(default_factory=list)
    currency: str = "USD"
    seasonality: list[str] = Field(default_factory=list)
    naming_style: str = "realistic business names"
    regulatory_or_quality_terms: list[str] = Field(default_factory=list)

    _clean_lists = field_validator("geography_terms", "seasonality", "regulatory_or_quality_terms", mode="before")(_normalize_string_list)

    @field_validator("currency", "naming_style", mode="before")
    @classmethod
    def clean_optional_strings(cls, value: object) -> str:
        text = str(value or "").strip()
        return text or "USD"


class IndustryScenarioPlan(ScenarioModel):
    """LLM-owned industry/business scenario hints only.

    This contract intentionally excludes table names, column names, formulas,
    SQL, validation rules, row-level data, and full executable row-count plans.
    """

    industry_id: str
    industry_name: str
    business_summary: str
    supported_domains: list[SupportedDomain] = Field(default_factory=lambda: ["procurement", "production", "sales"])
    row_volume_intent: RowVolumeIntent = "standard"
    procurement: ProcurementScenarioHints = Field(default_factory=ProcurementScenarioHints)
    production: ProductionScenarioHints = Field(default_factory=ProductionScenarioHints)
    sales: SalesScenarioHints = Field(default_factory=SalesScenarioHints)
    shared: SharedScenarioHints = Field(default_factory=SharedScenarioHints)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("industry_id", mode="before")
    @classmethod
    def normalize_industry_id(cls, value: object) -> str:
        text = _normalize_text(value)
        return "_".join(text.lower().replace("-", " ").split()) or "general_manufacturing"

    @field_validator("industry_name", "business_summary", mode="before")
    @classmethod
    def clean_required_text(cls, value: object) -> str:
        text = _normalize_text(value)
        if not text:
            raise ValueError("field must not be blank.")
        return text

    @field_validator("supported_domains", mode="before")
    @classmethod
    def normalize_domains(cls, value: object) -> list[str]:
        domains = _normalize_string_list(value)
        return [domain.lower() for domain in domains] or ["procurement", "production", "sales"]

    @field_validator("assumptions", "warnings", mode="before")
    @classmethod
    def clean_text_lists(cls, value: object) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def require_lifecycle_domains(self) -> "IndustryScenarioPlan":
        missing = {"procurement", "production", "sales"} - set(self.supported_domains)
        if missing:
            raise ValueError(f"supported_domains must include procurement, production, and sales. Missing: {', '.join(sorted(missing))}.")
        return self


def fallback_industry_scenario_plan(reason: str | None = None) -> IndustryScenarioPlan:
    """Return deterministic fallback scenario hints for failed LLM planning."""

    warnings = ["Fallback industry scenario plan was used because LLM planning failed."]
    if reason:
        warnings.append(str(reason)[:500])
    return IndustryScenarioPlan(
        industry_id="general_manufacturing",
        industry_name="General Manufacturing",
        business_summary="General discrete manufacturing lifecycle covering supplier purchasing, production execution, finished goods, and customer sales.",
        supported_domains=["procurement", "production", "sales"],
        row_volume_intent="standard",
        procurement=ProcurementScenarioHints(
            supplier_types=["Component Supplier", "Raw Material Supplier", "Packaging Supplier"],
            component_categories=["Mechanical Components", "Electrical Components", "Packaging Materials"],
            raw_material_terms=["component", "assembly", "packaging material"],
            purchasing_patterns=["planned replenishment", "quality-inspected receipts"],
            supplier_risk_factors=["late delivery", "quality hold"],
            inspection_or_quality_hints=["incoming inspection", "accepted quantity", "rejected quantity"],
        ),
        production=ProductionScenarioHints(
            product_families=["Finished Goods", "Assembled Products"],
            production_process_terms=["assembly", "inspection", "packaging"],
            work_center_terms=["Assembly Cell", "Quality Station", "Packing Line"],
            routing_patterns=["standard routing", "quality gate"],
            scrap_or_yield_hints=["normal yield loss", "rework hold"],
            finished_good_terms=["finished product", "saleable item"],
        ),
        sales=SalesScenarioHints(
            customer_types=["Distributor", "Retail Customer", "Industrial Customer"],
            customer_industries=["Manufacturing", "Distribution", "Retail"],
            sales_channels=["DIRECT", "DISTRIBUTOR", "ONLINE"],
            demand_patterns=["steady demand", "monthly replenishment"],
            payment_terms=["Net30", "Net45"],
            return_reasons=["quality return", "shipping damage"],
            region_terms=["North", "South", "East", "West"],
        ),
        shared=SharedScenarioHints(
            geography_terms=["USA"],
            currency="USD",
            seasonality=["standard business calendar"],
            naming_style="realistic manufacturing business names",
            regulatory_or_quality_terms=["traceability", "quality inspection"],
        ),
        assumptions=["Python will synthesize executable table, column, formula, lifecycle, and validation rules from metadata."],
        warnings=warnings,
    )
