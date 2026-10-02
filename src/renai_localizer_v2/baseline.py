"""MTool ``ManualTransFile.json`` extraction baseline importer.

The file is a source-text coverage and compatibility baseline. Its values may
be identical to the keys because the template has not been translated yet;
that is expected and is never treated as an error.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import ExtractionSnapshot


def load_mtool_baseline(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("MTool extraction baseline must contain a JSON object of string -> string entries")
    return data


def assess_alignment(snapshot: ExtractionSnapshot | None, baseline: dict[str, str]) -> dict[str, object]:
    """Explain what a text-only MTool map can and cannot align."""
    occurrences: list[str] = []
    if snapshot is not None:
        for block in snapshot.blocks:
            for statement in block.statements:
                if statement.text is not None and statement.text != "" and statement.kind != "string_new":
                    occurrences.append(statement.text)
    counts: dict[str, int] = {}
    for text in occurrences:
        counts[text] = counts.get(text, 0) + 1
    matched = sum(text in baseline for text in occurrences)
    return {
        "schema": "text->text",
        "occurrences": len(occurrences),
        "exact_text_matches": matched,
        "missing_text": len(occurrences) - matched,
        "source_index_available": False,
        "line_index_available": False,
        "occurrence_index_available": False,
        "ambiguous_texts": sorted(text for text, count in counts.items() if count > 1),
        "required_extra_index": ["source", "line", "occurrence"],
    }
