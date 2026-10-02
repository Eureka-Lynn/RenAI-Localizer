"""Deterministic, source-traceable story context indexing.

This module only reshapes extracted data. It does not infer plot facts and does
not call an LLM or build a vector index.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .coverage import build_occurrence_records, enrich_snapshot, normalize_source_text
from .models import ExtractionSnapshot

_VARIABLE_RE = re.compile(r"\[[^\[\]\r\n]+\]")
_TAG_RE = re.compile(r"\{[^{}\r\n]*\}")
_TERM_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b")


@dataclass(frozen=True)
class ContextIndexEntry:
    occurrence_id: str
    current_label: str | None
    previous_blocks: list[dict[str, Any]] = field(default_factory=list)
    next_blocks: list[dict[str, Any]] = field(default_factory=list)
    current_speaker: str | None = None
    scene_file: str = ""
    recent_same_speaker: list[dict[str, Any]] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    renpy_tags: list[str] = field(default_factory=list)
    related_mtool_source_text: list[str] = field(default_factory=list)
    term_candidates: list[str] = field(default_factory=list)
    term_sources: list[dict[str, str]] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence_id,
            "current_label": self.current_label,
            "previous_blocks": self.previous_blocks,
            "next_blocks": self.next_blocks,
            "current_speaker": self.current_speaker,
            "scene_file": self.scene_file,
            "recent_same_speaker": self.recent_same_speaker,
            "variables": self.variables,
            "renpy_tags": self.renpy_tags,
            "related_mtool_source_text": self.related_mtool_source_text,
            "term_candidates": self.term_candidates,
            "term_sources": self.term_sources,
            "source_refs": self.source_refs,
            "diagnostics": self.diagnostics,
        }


def _block_view(records: list[dict[str, Any]]) -> dict[str, Any]:
    first = records[0]
    return {
        "context_key": f"{first['block_id']}@{first['source_file']}",
        "block_id": first["block_id"],
        "official_identifier": first["official_identifier"],
        "source_file": first["source_file"],
        "source_line": first["source_line"],
        "label": first["label"],
        "speaker": first["speaker"],
        "occurrence_ids": [record["occurrence_id"] for record in records],
        "source_texts": [record["source_text"] for record in records],
    }


def _term_candidates(text: str, explicit_terms: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    found: list[str] = []
    sources: list[dict[str, str]] = []
    for term in [*explicit_terms, *_TERM_RE.findall(text)]:
        if term not in found:
            found.append(term)
            sources.append({"term": term, "source": "source_text"})
    return found, sources


def build_context_index(
    snapshot: ExtractionSnapshot,
    mtool: dict[str, str] | None = None,
    *,
    game_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Build one deterministic context entry per occurrence.

    ``game_root`` is optional because official snapshots already contain the
    source locations. When provided, labels and speaker values are enriched
    from the copied source files; unresolved values remain ``None`` and are
    represented in occurrence diagnostics.
    """
    if game_root is not None:
        enrich_snapshot(snapshot, game_root)
    baseline = mtool or {}
    normalized_baseline: dict[str, list[str]] = defaultdict(list)
    for key_text in baseline:
        normalized_baseline[normalize_source_text(key_text)].append(key_text)
    records = build_occurrence_records(snapshot, baseline)
    explicit_terms = {block.id: list(block.terms) for block in snapshot.blocks}
    by_block: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["block_id"], record["source_file"])
        by_block.setdefault(key, []).append(record)
    block_order = list(by_block)
    block_views = [_block_view(by_block[key]) for key in block_order]
    blocks_by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for view in block_views:
        blocks_by_scene[view["source_file"]].append(view)
    block_index = {
        (view["block_id"], view["source_file"]): index
        for scene_blocks in blocks_by_scene.values()
        for index, view in enumerate(scene_blocks)
    }

    result: dict[str, dict[str, Any]] = {}
    prior_speakers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        idx = block_index[(record["block_id"], record["source_file"])]
        scene_blocks = blocks_by_scene[record["source_file"]]
        previous = scene_blocks[max(0, idx - 3) : idx]
        following = scene_blocks[idx + 1 : idx + 4]
        speaker = record["speaker"]
        key = (record["source_file"], speaker) if speaker else None
        recent = list(prior_speakers.get(key, [])) if key else []
        related = [record["source_text"]] if record["source_text"] in baseline else []
        if not related:
            normalized = normalize_source_text(record["source_text"])
            related = normalized_baseline.get(normalized, [])
        terms, term_sources = _term_candidates(
            record["source_text"], explicit_terms.get(record["block_id"], [])
        )
        term_sources = [
            {
                **source,
                "occurrence_id": record["occurrence_id"],
                "source_file": record["source_file"],
                "source_line": str(record["source_line"]),
            }
            for source in term_sources
        ]
        variables = _VARIABLE_RE.findall(record["source_text"])
        tags = _TAG_RE.findall(record["source_text"])
        source_refs = [
            {
                "occurrence_id": record["occurrence_id"],
                "source_file": record["source_file"],
                "source_line": record["source_line"],
                "block_id": record["block_id"],
                "statement_index": record["statement_index"],
            }
        ]
        entry = ContextIndexEntry(
            occurrence_id=record["occurrence_id"],
            current_label=record["label"],
            previous_blocks=previous,
            next_blocks=following,
            current_speaker=speaker,
            scene_file=record["source_file"],
            recent_same_speaker=recent[-5:],
            variables=variables,
            renpy_tags=tags,
            related_mtool_source_text=related,
            term_candidates=terms,
            term_sources=term_sources,
            source_refs=source_refs,
            diagnostics=list(record.get("diagnostics", [])),
        )
        result[record["occurrence_id"]] = entry.to_dict()
        if key:
            prior_speakers.setdefault(key, []).append(
                {
                    "occurrence_id": record["occurrence_id"],
                    "source_text": record["source_text"],
                    "source_file": record["source_file"],
                    "source_line": record["source_line"],
                }
            )
    return result
