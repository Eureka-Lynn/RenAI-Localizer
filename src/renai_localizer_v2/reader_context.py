"""Reader Context Layer data contracts and bounded fixture generation.

The builder deliberately creates an evidence graph, not a story summary. It
derives only source-backed indexes from selected official occurrences; all
interpretive fields remain unknown until a reviewed human or LLM pass fills
them.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from .context import build_context_index
from .coverage import build_occurrence_records, enrich_snapshot
from .models import ExtractionSnapshot, TranslationBlock


@dataclass(frozen=True)
class SourceRef:
    source_file: str
    source_line: int
    block_id: str | None = None
    occurrence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoryBible:
    project: str
    version: str | None
    story_overview: str | None
    confirmed_world_facts: list[str] = field(default_factory=list)
    confirmed_themes: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)
    confidence: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CharacterCard:
    character_id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    known_role: str | None = None
    personality: str | None = None
    speech_style: str | None = None
    relationships: list[str] = field(default_factory=list)
    known_facts: list[str] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)
    confidence: float | None = None
    unresolved_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SceneSummary:
    scene_id: str
    source_file: str
    label: str | None
    scene_goal: str | None = None
    participants: list[str] = field(default_factory=list)
    important_events: list[str] = field(default_factory=list)
    emotional_state: str | None = None
    foreshadowing: list[str] = field(default_factory=list)
    terminology: list[str] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)
    confidence: float | None = None
    unresolved_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    description: str
    participants: list[str] = field(default_factory=list)
    temporal_relation: str | None = None
    source_refs: list[SourceRef] = field(default_factory=list)
    confidence: float | None = None
    unresolved_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GlossaryEntry:
    source_term: str
    candidate_translation: str | None
    category: str
    related_characters: list[str] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)
    confidence: float | None = None
    alternatives: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReaderContext:
    occurrence_id: str
    story_bible_refs: list[str] = field(default_factory=list)
    character_card_refs: list[str] = field(default_factory=list)
    scene_summary_ref: str | None = None
    relevant_timeline_events: list[str] = field(default_factory=list)
    relevant_glossary_entries: list[str] = field(default_factory=list)
    local_context: dict[str, Any] = field(default_factory=dict)
    unresolved_questions: list[str] = field(default_factory=list)
    confidence: float | None = None
    source_refs: list[SourceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _scene_id(source_file: str) -> str:
    return f"scene-{hashlib.sha256(source_file.encode('utf-8')).hexdigest()[:12]}"


def _ref(record: dict[str, Any]) -> SourceRef:
    return SourceRef(
        source_file=str(record["source_file"]),
        source_line=int(record["source_line"]),
        block_id=str(record["block_id"]),
        occurrence_id=str(record["occurrence_id"]),
    )


def _unique_refs(records: Iterable[dict[str, Any]], limit: int | None = None) -> list[SourceRef]:
    seen: set[str] = set()
    result: list[SourceRef] = []
    for record in records:
        occurrence_id = str(record["occurrence_id"])
        if occurrence_id in seen:
            continue
        seen.add(occurrence_id)
        result.append(_ref(record))
        if limit is not None and len(result) >= limit:
            break
    return result


def _selected_snapshot(
    snapshot: ExtractionSnapshot,
    source_files: set[str],
) -> ExtractionSnapshot:
    blocks: list[TranslationBlock] = []
    for block in snapshot.blocks:
        statements = [
            statement
            for statement in block.statements
            if statement.location.source in source_files
        ]
        if statements:
            blocks.append(replace(block, statements=statements))
    return ExtractionSnapshot(
        backend=snapshot.backend,
        source=snapshot.source,
        blocks=blocks,
        diagnostics=list(snapshot.diagnostics),
    )


def build_reader_context_artifacts(
    snapshot: ExtractionSnapshot,
    mtool: dict[str, str],
    scene_manifest: list[dict[str, Any]],
    *,
    game_root: Path | None = None,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build bounded Stage 3 fixtures for the explicitly selected scenes."""
    source_files = {str(scene["source_file"]) for scene in scene_manifest}
    selected = _selected_snapshot(snapshot, source_files)
    if game_root is not None:
        enrich_snapshot(selected, game_root)
    records = build_occurrence_records(selected, mtool)
    context_index = build_context_index(selected, mtool)
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_scene[record["source_file"]].append(record)

    scene_ids = {source: _scene_id(source) for source in source_files}
    story_refs = [
        _ref(by_scene[source_file][0])
        for source_file in (str(scene["source_file"]) for scene in scene_manifest)
        if by_scene.get(source_file)
    ]
    metadata = run_metadata or {}
    story_bible = StoryBible(
        project=str(metadata.get("target", "Scarlet Hollow")),
        version=metadata.get("project_version"),
        story_overview=None,
        unresolved_questions=[
            "Story overview requires a reviewed reading pass.",
            "World facts and themes have not been asserted in Stage 3.",
        ],
        source_refs=story_refs,
        provenance={
            "kind": "official_snapshot_only",
            "extraction_backend": selected.backend,
            "source_snapshot": metadata.get("official_snapshot", "official_snapshot.json"),
            "renpy_version": metadata.get("renpy_version"),
            "llm_used": False,
        },
    )

    character_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["speaker"]:
            character_records[str(record["speaker"])].append(record)
    character_cards = [
        CharacterCard(
            character_id=character_id,
            name=character_id,
            source_refs=_unique_refs(character_records[character_id], limit=20),
            unresolved_items=[
                "Role, personality, speech style, relationships, and facts require reviewed evidence."
            ],
        )
        for character_id in sorted(character_records)
    ]

    scene_summaries: list[SceneSummary] = []
    for scene in scene_manifest:
        source_file = str(scene["source_file"])
        scene_records = by_scene.get(source_file, [])
        participants = sorted({str(r["speaker"]) for r in scene_records if r["speaker"]})
        refs_by_participant = [
            record
            for participant in participants
            for record in scene_records
            if record["speaker"] == participant
        ]
        refs = _unique_refs([*refs_by_participant, *scene_records], limit=40)
        labels = [r["label"] for r in scene_records if r["label"]]
        terminology = sorted(
            {
                term
                for record in scene_records
                for term in context_index[record["occurrence_id"]]["term_candidates"]
            }
        )
        scene_summaries.append(
            SceneSummary(
                scene_id=scene_ids[source_file],
                source_file=source_file,
                label=labels[0] if labels else None,
                participants=participants,
                terminology=terminology,
                source_refs=refs,
                unresolved_items=[
                    "Scene goal, events, emotional state, and foreshadowing require reviewed evidence."
                ],
            )
        )

    term_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    term_characters: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for term in context_index[record["occurrence_id"]]["term_candidates"]:
            term_records[term].append(record)
            if record["speaker"]:
                term_characters[term].add(str(record["speaker"]))
    glossary = [
        GlossaryEntry(
            source_term=term,
            candidate_translation=None,
            category="deterministic_source_candidate",
            related_characters=sorted(term_characters[term]),
            source_refs=_unique_refs(term_records[term], limit=10),
            notes=["Candidate extracted from source text; no translation asserted."],
        )
        for term in sorted(term_records)
    ]
    glossary_ids = {entry.source_term: f"glossary:{entry.source_term}" for entry in glossary}
    scene_summary_ids = {summary.source_file: summary.scene_id for summary in scene_summaries}
    character_ids = {card.character_id for card in character_cards}
    reader_contexts: list[ReaderContext] = []
    for record in records:
        occurrence_id = str(record["occurrence_id"])
        local = context_index[occurrence_id]
        terms = [
            glossary_ids[term]
            for term in local["term_candidates"]
            if term in glossary_ids
        ]
        speaker = str(record["speaker"]) if record["speaker"] else None
        reader_contexts.append(
            ReaderContext(
                occurrence_id=occurrence_id,
                story_bible_refs=["story_bible:scarlet_hollow"],
                character_card_refs=[f"character:{speaker}"] if speaker in character_ids else [],
                scene_summary_ref=scene_summary_ids.get(str(record["source_file"])),
                relevant_glossary_entries=terms,
                local_context=local,
                unresolved_questions=list(story_bible.unresolved_questions),
                source_refs=[_ref(record)],
            )
        )

    return {
        "story_bible": story_bible.to_dict(),
        "character_cards": [card.to_dict() for card in character_cards],
        "scene_summaries": [summary.to_dict() for summary in scene_summaries],
        "timeline": [],
        "glossary": [entry.to_dict() for entry in glossary],
        "reader_contexts": [context.to_dict() for context in reader_contexts],
        "metadata": {
            "selected_scenes": [str(scene["source_file"]) for scene in scene_manifest],
            "occurrences": len(records),
            "source_files": sorted(source_files),
            "llm_used": False,
            "vector_database_used": False,
            "translated": False,
            "duplicate_occurrence_ids": len(records) - len({r["occurrence_id"] for r in records}),
        },
    }
