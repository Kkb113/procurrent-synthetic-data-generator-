"""Parser for Mermaid ERD relationship lines."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from procurement_data_generator.core.contracts.erd_contract import RelationshipContract


RELATIONSHIP_PATTERN = re.compile(
    r"^\s*(?P<left>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<symbol>[|}{o0O]+--[|}{o0O]+)\s+"
    r"(?P<right>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*:\s*(?P<label>.*?))?\s*$"
)

LEFT_PARENT_SYMBOLS = {
    "||--o{": "one_to_many",
    "||--|{": "one_to_many",
    "||--||": "one_to_one",
}

RIGHT_PARENT_SYMBOLS = {
    "}o--||": "many_to_one",
    "}|--||": "many_to_one",
    "o{--||": "many_to_one",
    "|{--||": "many_to_one",
}

MANY_TO_MANY_SYMBOLS = {
    "}o--o{",
    "o{--}o",
    "}|--|{",
    "|{--}|",
}


def parse_mermaid_erd_text(erd_text: str) -> list[RelationshipContract]:
    """Parse Mermaid ERD text into normalized relationship contracts."""

    relationships: list[RelationshipContract] = []
    for raw_line in erd_text.splitlines():
        line = _strip_inline_comment(raw_line).strip()
        if not line or line == "erDiagram":
            continue

        match = RELATIONSHIP_PATTERN.match(line)
        if not match:
            continue

        left_table = match.group("left")
        right_table = match.group("right")
        symbol = _normalize_symbol(match.group("symbol"))
        label = match.group("label")
        if label is not None:
            label = label.strip() or None

        parent_table, child_table, relationship_type = _normalize_relationship_direction(
            left_table=left_table,
            right_table=right_table,
            symbol=symbol,
        )
        relationships.append(
            RelationshipContract(
                parent_table=parent_table,
                child_table=child_table,
                relationship_type=relationship_type,
                mermaid_symbol=symbol,
                label=label,
                raw_line=line,
            )
        )

    return relationships


def parse_mermaid_erd_file(file_path: str | Path) -> list[RelationshipContract]:
    """Read a Mermaid ERD file and parse relationship contracts."""

    return parse_mermaid_erd_text(Path(file_path).read_text(encoding="utf-8"))


def _normalize_relationship_direction(
    left_table: str,
    right_table: str,
    symbol: str,
) -> tuple[str, str, str]:
    if symbol in LEFT_PARENT_SYMBOLS:
        return left_table, right_table, LEFT_PARENT_SYMBOLS[symbol]
    if symbol in RIGHT_PARENT_SYMBOLS:
        return right_table, left_table, RIGHT_PARENT_SYMBOLS[symbol]
    if symbol in MANY_TO_MANY_SYMBOLS:
        return left_table, right_table, "many_to_many"
    return left_table, right_table, "unknown"


def _normalize_symbol(symbol: str) -> str:
    return symbol.replace("0", "o").replace("O", "o")


def _strip_inline_comment(line: str) -> str:
    if line.strip().startswith("%%") or line.strip().startswith("#"):
        return ""
    if "%%" in line:
        return line.split("%%", maxsplit=1)[0]
    return line


def main() -> int:
    """Small parser demo for Mermaid ERD files."""

    parser = argparse.ArgumentParser(description="Parse Mermaid ERD relationships.")
    parser.add_argument("erd_path", help="Path to a Mermaid ERD text file.")
    args = parser.parse_args()

    relationships = parse_mermaid_erd_file(args.erd_path)
    for relationship in relationships:
        label = f" : {relationship.label}" if relationship.label else ""
        print(
            f"{relationship.parent_table} -> {relationship.child_table} "
            f"({relationship.relationship_type}, {relationship.mermaid_symbol}){label}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
