"""Prompt fixtures for later translation integration.

The fixtures are plain data for review and tests. No provider SDK or network
call is involved in producing them.
"""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "translation-prompt-v2-semantic"

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
    reader_context: dict[str, Any] | None = None,
    story_bible: dict[str, Any] | None = None,
    character_cards: list[dict[str, Any]] | None = None,
    scene_summaries: list[dict[str, Any]] | None = None,
    timeline_events: list[dict[str, Any]] | None = None,
    glossary: list[dict[str, Any]] | None = None,
    semantic_context: dict[str, Any] | None = None,
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
        payload["context"] = _reader_context_payload(
            occurrence,
            context,
            reader_context=reader_context,
            story_bible=story_bible,
            character_cards=character_cards or [],
            scene_summaries=scene_summaries or [],
            timeline_events=timeline_events or [],
            glossary=glossary or [],
            semantic_context=semantic_context,
        )
    return payload


def _source_fields(occurrence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "occurrence_id": occurrence["occurrence_id"],
        "source_text": occurrence["source_text"],
        "label": occurrence.get("label", context.get("current_label")),
        "speaker": occurrence.get("speaker", context.get("current_speaker")),
        "source_file": occurrence.get("source_file", context.get("scene_file")),
        "source_line": occurrence.get("source_line"),
    }


def _reader_context_payload(
    occurrence: dict[str, Any],
    context: dict[str, Any],
    *,
    reader_context: dict[str, Any] | None,
    story_bible: dict[str, Any] | None,
    character_cards: list[dict[str, Any]],
    scene_summaries: list[dict[str, Any]],
    timeline_events: list[dict[str, Any]],
    glossary: list[dict[str, Any]],
    semantic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expand one occurrence index entry into a bounded Reader Context.

    Only glossary entries referenced by this occurrence are copied into the
    prompt. Every other object is either selected by a ReaderContext ref or
    represented by an explicit null/empty value.
    """
    reader_context = reader_context or {}
    story_ref_set = set(reader_context.get("story_bible_refs", []))
    character_ref_set = set(reader_context.get("character_card_refs", []))
    glossary_ref_set = set(reader_context.get("relevant_glossary_entries", []))
    scene_ref = reader_context.get("scene_summary_ref")

    story = story_bible if not story_ref_set or "story_bible:scarlet_hollow" in story_ref_set else None
    # Semantic claims are an explicit, status-filtered boundary. Legacy
    # fixtures without a status remain compatible; claims with a status must
    # be verified before they can appear as asserted context.
    semantic_context = semantic_context or {}
    def verified(item: dict[str, Any]) -> bool:
        return item.get("status", "verified") == "verified"
    verified_claims = [
        claim for claim in semantic_context.get("verified_claims", [])
        if claim.get("status", "verified") == "verified"
    ]
    selected_characters = [
        dict(card)
        for card in character_cards
        if f"character:{card.get('character_id')}" in character_ref_set and verified(card)
    ]
    selected_scene = next(
        (summary for summary in scene_summaries if summary.get("scene_id") == scene_ref and verified(summary)),
        None,
    )
    timeline_ref_set = set(reader_context.get("relevant_timeline_events", []))
    selected_timeline = [
        event
        for event in timeline_events
        if event.get("event_id") in timeline_ref_set
    ]
    selected_glossary = [
        entry
        for entry in glossary
        if f"glossary:{entry.get('source_term')}" in glossary_ref_set and verified(entry)
    ]
    if not reader_context:
        selected_glossary = [
            entry
            for entry in glossary
            if entry.get("source_term") in set(context.get("term_candidates", [])) and verified(entry)
        ]

    if selected_characters:
        for card in selected_characters:
            card.setdefault("speech_style_status", "unknown" if card.get("speech_style") is None else "known")

    return {
        "reader_context": reader_context,
        "local_context": dict(context),
        "current_occurrence": _source_fields(occurrence, context),
        "current_label": context.get("current_label", occurrence.get("label")),
        "current_speaker": context.get("current_speaker", occurrence.get("speaker")),
        "scene_file": context.get("scene_file", occurrence.get("source_file")),
        "previous_blocks": list(context.get("previous_blocks", []))[-3:],
        "next_blocks": list(context.get("next_blocks", []))[:3],
        "recent_same_speaker": list(context.get("recent_same_speaker", [])),
        "scene_summary": selected_scene,
        "timeline_events": selected_timeline,
        "character_cards": selected_characters,
        "story_bible": story,
        "glossary_entries": selected_glossary,
        "unresolved_questions": list(
            reader_context.get(
                "unresolved_questions",
                (story or {}).get("unresolved_questions", []),
            )
        ) + list(semantic_context.get("unresolved_questions", [])),
        "variables": list(context.get("variables", [])),
        "renpy_tags": list(context.get("renpy_tags", [])),
        "source_refs": list(reader_context.get("source_refs", context.get("source_refs", []))),
        "diagnostics": list(context.get("diagnostics", [])),
        "semantic_context": {
            "occurrence_id": occurrence["occurrence_id"],
            "verified_claims": verified_claims,
            "unresolved_questions": list(semantic_context.get("unresolved_questions", [])),
            "source_refs": list(semantic_context.get("source_refs", [])),
        },
    }


def build_single_unit_prompt(
    occurrence: dict[str, Any], *, target_language: str = "简体中文"
) -> dict[str, Any]:
    return _fixture("single_unit_prompt", occurrence, target_language=target_language)


def build_context_aware_prompt(
    occurrence: dict[str, Any],
    context: dict[str, Any],
    *,
    target_language: str = "简体中文",
    reader_context: dict[str, Any] | None = None,
    story_bible: dict[str, Any] | None = None,
    character_cards: list[dict[str, Any]] | None = None,
    scene_summaries: list[dict[str, Any]] | None = None,
    timeline_events: list[dict[str, Any]] | None = None,
    glossary: list[dict[str, Any]] | None = None,
    semantic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _fixture(
        "context_aware_prompt",
        occurrence,
        target_language=target_language,
        context=context,
        reader_context=reader_context,
        story_bible=story_bible,
        character_cards=character_cards,
        scene_summaries=scene_summaries,
        timeline_events=timeline_events,
        glossary=glossary,
        semantic_context=semantic_context,
    )


def build_prompt_fixtures(
    occurrences: list[dict[str, Any]],
    context_index: dict[str, dict[str, Any]],
    *,
    target_language: str = "简体中文",
    reader_contexts: dict[str, dict[str, Any]] | None = None,
    story_bible: dict[str, Any] | None = None,
    character_cards: list[dict[str, Any]] | None = None,
    scene_summaries: list[dict[str, Any]] | None = None,
    timeline_events: list[dict[str, Any]] | None = None,
    glossary: list[dict[str, Any]] | None = None,
    semantic_contexts: dict[str, dict[str, Any]] | None = None,
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
                reader_context=(reader_contexts or {}).get(row["occurrence_id"]),
                story_bible=story_bible,
                character_cards=character_cards,
                scene_summaries=scene_summaries,
                timeline_events=timeline_events,
                glossary=glossary,
                semantic_context=(semantic_contexts or {}).get(row["occurrence_id"]),
            )
            for row in occurrences
        ],
    }


def render_prompt(fixture: dict[str, Any]) -> str:
    """Render a fixture as deterministic JSON for a later provider adapter."""
    return json.dumps(fixture, ensure_ascii=False, indent=2)
