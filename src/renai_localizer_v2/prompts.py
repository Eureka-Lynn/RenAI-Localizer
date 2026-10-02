"""Prompt fixtures for later translation integration.

The fixtures are plain data for review and tests. No provider SDK or network
call is involved in producing them.
"""

from __future__ import annotations

import json
from typing import Any

OUTPUT_SHAPE = {
    "occurrence_id": "...",
    "translation": "...",
    "notes": [],
}

_OUTPUT_INSTRUCTION = (
    "Return exactly one JSON object with exactly these keys: "
    "occurrence_id (string), translation (string), notes (array of strings). "
    "Do not return markdown, commentary, or any other keys."
)


def _fixture(
    prompt_type: str,
    occurrence: dict[str, Any],
    *,
    target_language: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    occurrence_id = str(occurrence["occurrence_id"])
    payload: dict[str, Any] = {
        "prompt_type": prompt_type,
        "target_language": target_language,
        "system": (
            "You translate one Ren'Py text occurrence. Preserve variables, "
            "Ren'Py text tags, percent signs, backslashes, newlines, and the "
            "statement structure exactly. "
            + _OUTPUT_INSTRUCTION
        ),
        "user": {
            "occurrence_id": occurrence_id,
            "source_text": occurrence["source_text"],
            "speaker": occurrence.get("speaker"),
            "label": occurrence.get("label"),
            "source_file": occurrence["source_file"],
            "source_line": occurrence["source_line"],
        },
        "response_schema": OUTPUT_SHAPE,
    }
    if context is not None:
        payload["context"] = context
    return payload


def build_single_unit_prompt(
    occurrence: dict[str, Any], *, target_language: str = "简体中文"
) -> dict[str, Any]:
    return _fixture("single_unit_prompt", occurrence, target_language=target_language)


def build_context_aware_prompt(
    occurrence: dict[str, Any],
    context: dict[str, Any],
    *,
    target_language: str = "简体中文",
) -> dict[str, Any]:
    return _fixture(
        "context_aware_prompt",
        occurrence,
        target_language=target_language,
        context=context,
    )


def build_prompt_fixtures(
    occurrences: list[dict[str, Any]],
    context_index: dict[str, dict[str, Any]],
    *,
    target_language: str = "简体中文",
) -> dict[str, list[dict[str, Any]]]:
    """Build both fixture types for the selected occurrence rows."""
    return {
        "single_unit_prompt": [
            build_single_unit_prompt(row, target_language=target_language)
            for row in occurrences
        ],
        "context_aware_prompt": [
            build_context_aware_prompt(
                row,
                context_index.get(row["occurrence_id"], {}),
                target_language=target_language,
            )
            for row in occurrences
        ],
    }


def render_prompt(fixture: dict[str, Any]) -> str:
    """Render a fixture as deterministic JSON for a later provider adapter."""
    return json.dumps(fixture, ensure_ascii=False, indent=2)
