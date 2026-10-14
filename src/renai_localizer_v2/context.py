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
_URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>{}\[\]]+")
_TERM_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:['-][A-Za-z0-9]+)*\b")

# This is deliberately a small linguistic guard, not an entity recognizer.
# Shape, repetition, speaker metadata, and explicit block terms provide the
# positive evidence; this set only removes words that are almost never useful
# glossary entries on their own.
_COMMON_WORDS = frozenset(
    {
        "a",
        "all",
        "am",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "because",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "no",
        "nor",
        "not",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "she",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)

# These words can be title-cased or all-caps in ordinary prose/UI copy. They
# are kept separate from the function-word guard so the positive rules remain
# structural rather than becoming one large stopword list.
_ORDINARY_SURFACE_WORDS = frozenset(
    {
        "according",
        "afraid",
        "after",
        "almost",
        "always",
        "another",
        "any",
        "anything",
        "anyway",
        "back",
        "before",
        "between",
        "both",
        "come",
        "everyone",
        "listen",
        "maybe",
        "nothing",
        "please",
        "something",
        "there",
        "warning",
        "welcome",
    }
)

_COMMON_EXCLAMATIONS = frozenset(
    {
        "ah",
        "aw",
        "aww",
        "eh",
        "ew",
        "gee",
        "gosh",
        "ha",
        "haha",
        "heh",
        "heya",
        "hi",
        "hmm",
        "mhm",
        "nah",
        "ohhh",
        "okee",
        "phew",
        "yay",
        "yep",
        "whoa",
        "whoops",
    }
)


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
        "source_refs": [
            {
                "source_file": record["source_file"],
                "source_line": record["source_line"],
                "block_id": record["block_id"],
                "occurrence_id": record["occurrence_id"],
            }
            for record in records
        ],
    }


def _term_candidates(
    text: str,
    explicit_terms: list[str],
    *,
    speaker: str | None = None,
    token_frequency: dict[str, int] | None = None,
    non_initial_frequency: dict[str, int] | None = None,
    lowercase_frequency: dict[str, int] | None = None,
    suppress: bool = False,
) -> tuple[list[str], list[dict[str, str]]]:
    """Return conservative, source-backed term candidates.

    The function intentionally uses observable source shapes rather than
    pretending to identify entities. A title-case token is accepted when it
    is not sentence-initial, forms a multi-word title, or is stable all-caps
    text; speaker metadata remains context metadata rather than a term.
    """
    clean_text = _URL_RE.sub(" ", _VARIABLE_RE.sub(" ", _TAG_RE.sub(" ", text)))
    if suppress:
        return [], []
    matches = list(_TERM_RE.finditer(clean_text))
    words = [match.group(0) for match in matches]
    lowercase = lowercase_frequency or {}
    found: list[str] = []
    sources: list[dict[str, str]] = []

    def add(term: str, source: str) -> None:
        normalized = term.strip()
        if (
            not normalized
            or len(normalized) < 2
            or normalized.casefold() in _COMMON_WORDS
            or normalized in found
        ):
            return
        found.append(normalized)
        sources.append({"term": normalized, "source": source})

    for term in explicit_terms:
        add(term, "explicit_block_term")
    accepted: list[tuple[int, str, int, int]] = []
    for index, match in enumerate(matches):
        token = match.group(0)
        folded = token.casefold()
        if folded in _COMMON_WORDS or len(token) < 2:
            continue
        previous = clean_text[: match.start()].rstrip()
        sentence_initial = not previous or previous[-1] in ".!?\n"
        title_case = token[0].isupper() and token[1:].islower()
        case_stable = lowercase.get(folded, 0) == 0
        all_caps = (
            token.isupper()
            and any(character.isalpha() for character in token)
            and case_stable
        )
        ordinary = folded in _ORDINARY_SURFACE_WORDS or folded in _COMMON_EXCLAMATIONS
        adjacent_title = any(
            words[neighbor][0].isupper() and words[neighbor][1:].islower()
            for neighbor in (index - 1, index + 1)
            if 0 <= neighbor < len(words)
        )
        if all_caps and not ordinary:
            accepted.append((index, token, match.start(), match.end()))
            add(token, "source_text")
        elif (
            title_case
            and case_stable
            and not ordinary
            and (not sentence_initial or adjacent_title)
        ):
            accepted.append((index, token, match.start(), match.end()))
            add(token, "source_text")

    # Preserve a multi-word proper phrase as one candidate in addition to its
    # individual components, since titles and locations often translate as a
    # unit (for example, ``Scarlet Hollow``).
    run: list[str] = []
    previous_index: int | None = None
    previous_end: int | None = None
    for index, token, start, end in accepted:
        contiguous_text = (
            previous_end is not None and clean_text[previous_end:start].strip() == ""
        )
        title_case = token[0].isupper() and token[1:].islower()
        if run and (
            previous_index is None
            or index != previous_index + 1
            or not contiguous_text
            or not title_case
        ):
            if len(run) > 1:
                add(" ".join(run), "source_text_phrase")
            run = []
        if title_case:
            run.append(token)
        else:
            run = []
        previous_index = index
        previous_end = end
    if len(run) > 1:
        add(" ".join(run), "source_text_phrase")
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
    token_frequency: dict[str, int] = defaultdict(int)
    non_initial_frequency: dict[str, int] = defaultdict(int)
    lowercase_frequency: dict[str, int] = defaultdict(int)
    for record in records:
        clean_text = _URL_RE.sub(
            " ", _VARIABLE_RE.sub(" ", _TAG_RE.sub(" ", record["source_text"]))
        )
        matches = list(_TERM_RE.finditer(clean_text))
        for match in matches:
            token = match.group(0)
            if token.casefold() not in _COMMON_WORDS:
                token_frequency[token.casefold()] += 1
                if token.islower():
                    lowercase_frequency[token.casefold()] += 1
                prefix = clean_text[: match.start()].rstrip()
                if prefix and prefix[-1] not in ".!?\n":
                    non_initial_frequency[token.casefold()] += 1
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
            record["source_text"],
            explicit_terms.get(record["block_id"], []),
            speaker=record["speaker"],
            token_frequency=token_frequency,
            non_initial_frequency=non_initial_frequency,
            lowercase_frequency=lowercase_frequency,
            suppress=record["block_id"].startswith("strings:"),
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
                    "source_refs": [
                        {
                            "source_file": record["source_file"],
                            "source_line": record["source_line"],
                            "block_id": record["block_id"],
                            "occurrence_id": record["occurrence_id"],
                        }
                    ],
                }
            )
    return result
