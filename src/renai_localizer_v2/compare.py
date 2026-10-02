"""Official snapshot and MTool baseline comparison.

The comparison is text based at the external MTool boundary. Internally,
every official occurrence remains a separate row.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import ExtractionSnapshot


@dataclass(frozen=True)
class ComparisonRow:
    occurrence: str
    source: str
    line: int
    official: str
    mtool: str | None
    status: str


def _occurrences(snapshot: ExtractionSnapshot | None) -> list[tuple[str, str, int, str]]:
    if snapshot is None:
        return []
    rows: list[tuple[str, str, int, str]] = []
    for block in snapshot.blocks:
        for index, statement in enumerate(block.statements):
            if statement.text is None or statement.text == "" or statement.kind == "string_new":
                continue
            occurrence = (
                f"{block.identifier or block.id}@"
                f"{statement.location.source}:{statement.location.line}:{index}"
            )
            rows.append((occurrence, statement.location.source, statement.location.line, statement.text))
    return rows


def build_report(
    official: ExtractionSnapshot | None,
    mtool: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an official-vs-baseline report without a legacy production path."""
    rows = [
        ComparisonRow(
            occurrence=occurrence,
            source=source,
            line=line,
            official=text,
            mtool=(mtool or {}).get(text),
            status="exact" if text in (mtool or {}) else "mtool-missing",
        )
        for occurrence, source, line, text in _occurrences(official)
    ]
    texts = {row.official for row in rows}
    baseline = set(mtool or {})
    return {
        "schema_version": 2,
        "rows": [asdict(row) for row in rows],
        "summary": {
            "occurrences": len(rows),
            "official_unique_texts": len(texts),
            "mtool_entries": len(baseline),
            "exact_text_matches": sum(row.status == "exact" for row in rows),
            "mtool_missing_occurrences": sum(row.status == "mtool-missing" for row in rows),
            "mtool_only": len(baseline - texts),
        },
    }
