"""Occurrence-preserving coverage comparison for official and MTool extraction."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import ExtractionSnapshot, OccurrenceRecord, TranslationStatement

_LABEL_RE = re.compile(r"^\s*label\s+(?P<label>[A-Za-z_][\w.]*)\s*:")
_SPEAKER_RE = re.compile(r"^\s*(?P<speaker>[A-Za-z_][\w.]*)\s+(?:@\s+)?(?:[\"']{1,3})")
_COMMAND_PREFIXES = ("old ", "new ", "voice ", "play ", "queue ", "show ", "scene ", "window ", "extend ", "nvl clear")


def normalize_source_text(text: str) -> str:
    """Normalize only for comparison; never rewrite stored source text."""
    return " ".join(unicodedata.normalize("NFKC", text).replace("\r\n", "\n").split())


def _source_path(game_root: Path, source: str) -> Path:
    relative = source.replace("/", "\\")
    if relative.lower().startswith("game\\"):
        relative = relative[5:]
    return game_root / relative


def _label_and_lines(path: Path) -> dict[int, str]:
    labels: dict[int, str] = {}
    current: str | None = None
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return labels
    for number, line in enumerate(lines, 1):
        match = _LABEL_RE.match(line)
        if match:
            current = match.group("label")
        if current is not None:
            labels[number] = current
    return labels


def _speaker(raw: str | None) -> str | None:
    if not raw or raw.startswith(_COMMAND_PREFIXES):
        return None
    if raw.startswith(('"', "'", '"""', "'''") ):
        return None
    match = _SPEAKER_RE.match(raw)
    return match.group("speaker") if match else None


def enrich_snapshot(snapshot: ExtractionSnapshot, game_root: Path) -> ExtractionSnapshot:
    """Attach label and speaker context from the copied Scarlet Hollow scripts."""
    label_cache: dict[str, dict[int, str]] = {}
    for block in snapshot.blocks:
        source = block.location.source
        labels = label_cache.setdefault(source, _label_and_lines(_source_path(game_root, source)))
        label = labels.get(block.location.line)
        block.story = label
        block.metadata["label"] = label
        speakers: list[str] = []
        enriched: list[TranslationStatement] = []
        statement_labels: list[str | None] = []
        for statement in block.statements:
            speaker = statement.speaker or _speaker(statement.source_code or statement.raw)
            statement_labels.append(labels.get(statement.location.line))
            if speaker and speaker not in speakers:
                speakers.append(speaker)
            enriched.append(replace(statement, speaker=speaker))
        block.statements = enriched
        block.characters = speakers
        block.metadata["statement_labels"] = statement_labels
        if label is None:
            snapshot.diagnostics.append(
                f"label_unresolved:{source}:{block.location.line}"
            )
    return snapshot


def _iter_source_occurrences(snapshot: ExtractionSnapshot | None):
    if snapshot is None:
        return
    for block in snapshot.blocks:
        for index, statement in enumerate(block.statements):
            if statement.text is None or statement.text == "" or statement.kind == "string_new":
                continue
            yield block, statement, index


def build_occurrence_records(
    snapshot: ExtractionSnapshot,
    mtool: dict[str, str],
) -> list[dict[str, Any]]:
    """Create one record per official occurrence; duplicate source text stays duplicated."""
    normalized_keys: dict[str, list[str]] = defaultdict(list)
    for key in mtool:
        normalized_keys[normalize_source_text(key)].append(key)
    occurrences = list(_iter_source_occurrences(snapshot))
    source_counts = Counter(statement.text or "" for _, statement, _ in occurrences)
    records: list[dict[str, Any]] = []
    for block, statement, index in occurrences:
        source_text = statement.text or ""
        normalized = normalize_source_text(source_text)
        exact = source_text in mtool
        candidates = normalized_keys.get(normalized, [])
        mtool_key = source_text if exact else candidates[0] if len(candidates) == 1 else None
        diagnostics: list[str] = []
        labels = block.metadata.get("statement_labels")
        label = (
            labels[index]
            if isinstance(labels, list) and index < len(labels)
            else block.metadata.get("label", block.story)
        )
        if not isinstance(label, str):
            label = None
        speaker = statement.speaker
        if label is None:
            diagnostics.append("label_unresolved")
        raw_code = statement.source_code or statement.raw
        if speaker is None and raw_code is None:
            diagnostics.append("speaker_unresolved")
        elif speaker is None and raw_code:
            stripped = raw_code.lstrip()
            known_narration = stripped.startswith(('"', "'", '"""', "'''"))
            known_command = stripped.startswith(_COMMAND_PREFIXES)
            if not known_narration and not known_command and statement.kind not in {
                "string_old",
                "string_new",
            }:
                diagnostics.append("speaker_unresolved")
        if source_counts[source_text] > 1 and (exact or candidates):
            diagnostics.append("mtool_text_candidate_ambiguous")

        translated_text: str | None = None
        raw_source_code = statement.source_code or statement.raw
        raw_translated_code: str | None = None
        if statement.kind == "string_old":
            # Official strings blocks alternate old/new statements. The old
            # entry is the source occurrence and its adjacent new entry is the
            # official target, even when both values are equal in the template.
            following = block.statements[index + 1] if index + 1 < len(block.statements) else None
            if following is not None and following.kind == "string_new":
                candidate = following.text or ""
                if candidate != source_text:
                    translated_text = candidate
                    raw_translated_code = following.raw
        elif statement.source_code and statement.raw and statement.raw != statement.source_code:
            # A future official adapter may carry an actual translated code
            # line. The generated source==target template is intentionally
            # treated as untranslated and remains null.
            translated_text = statement.text
            raw_translated_code = statement.raw

        occurrence = OccurrenceRecord(
            occurrence_id=f"{block.identifier or block.id}@{statement.location.source}:{statement.location.line}:{index}",
            block_id=block.id,
            official_identifier=block.identifier,
            statement_index=index,
            source_file=statement.location.source,
            source_line=statement.location.line,
            label=label,
            speaker=speaker,
            source_text=source_text,
            translated_text=translated_text,
            raw_source_code=raw_source_code,
            raw_translated_code=raw_translated_code,
            extraction_backend=snapshot.backend,
            diagnostics=diagnostics,
        )
        row = occurrence.to_dict()
        ambiguous = source_counts[source_text] > 1
        row.update(
            {
                "mtool_translation": mtool.get(mtool_key) if mtool_key else None,
                "mtool_match": (
                    "text_candidate_ambiguous"
                    if ambiguous and mtool_key
                    else "exact_text_candidate"
                    if exact
                    else "normalized_text_candidate"
                    if mtool_key
                    else "none"
                ),
                "mtool_key": None if ambiguous else mtool_key,
                "mtool_candidates": candidates if candidates else ([source_text] if exact else []),
            }
        )
        records.append(row)
    return records


def compare_coverage(snapshot: ExtractionSnapshot, mtool: dict[str, str]) -> dict[str, Any]:
    """Compare sets and normalization variants without collapsing occurrences."""
    records = build_occurrence_records(snapshot, mtool)
    official_texts = [record["source_text"] for record in records]
    official_set = set(official_texts)
    mtool_set = set(mtool)
    normalized_official: dict[str, set[str]] = defaultdict(set)
    normalized_mtool: dict[str, set[str]] = defaultdict(set)
    for text in official_set:
        normalized_official[normalize_source_text(text)].add(text)
    for text in mtool_set:
        normalized_mtool[normalize_source_text(text)].add(text)
    normalized_differences = [
        {"normalized": key, "official_texts": sorted(normalized_official[key]), "mtool_keys": sorted(normalized_mtool[key])}
        for key in sorted(set(normalized_official) & set(normalized_mtool))
        if not (normalized_official[key] & normalized_mtool[key])
    ]
    duplicate_counts = Counter(official_texts)
    duplicate_source_texts = [
        {"source_text": text, "occurrences": count}
        for text, count in duplicate_counts.most_common()
        if count > 1
    ]
    return {
        "schema_version": 1,
        "baseline_kind": "MTool extraction baseline",
        "records": records,
        "coverage": {
            "mtool_keys": len(mtool_set),
            "official_unique_texts": len(official_set),
            "official_occurrences": len(official_texts),
            "intersection": len(official_set & mtool_set),
            "mtool_keys_only": len(mtool_set - official_set),
            "official_texts_only": len(official_set - mtool_set),
            "duplicate_source_texts": len(duplicate_source_texts),
            "duplicate_occurrences_beyond_first": sum(item["occurrences"] - 1 for item in duplicate_source_texts),
            "normalization_differences": len(normalized_differences),
        },
        "mtool_keys_only": sorted(mtool_set - official_set),
        "official_texts_only": sorted(official_set - mtool_set),
        "duplicate_source_texts": duplicate_source_texts,
        "normalization_differences": normalized_differences,
    }


def collapse_occurrences_to_mtool(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse only at the MTool export boundary and report collisions."""
    output: dict[str, str] = {}
    collisions: dict[str, list[str]] = defaultdict(list)
    for record in records:
        key = str(record["source_text"])
        value = record.get("our_translation")
        if value is None:
            value = record.get("mtool_translation") or key
        if key in output and output[key] != value:
            collisions[key].append(str(value))
        output.setdefault(key, str(value))
    return {
        "data": output,
        "collision_count": len(collisions),
        "collisions": {key: values for key, values in collisions.items()},
    }
