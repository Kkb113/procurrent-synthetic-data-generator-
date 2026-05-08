"""Contracts for parsed Mermaid ERD relationships."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


RelationshipType = Literal["one_to_many", "one_to_one", "many_to_one", "many_to_many", "unknown"]


class RelationshipContract(BaseModel):
    """A normalized relationship parsed from a Mermaid ERD line."""

    model_config = ConfigDict(extra="forbid")

    parent_table: str
    child_table: str
    relationship_type: RelationshipType
    mermaid_symbol: str
    label: str | None = None
    raw_line: str
