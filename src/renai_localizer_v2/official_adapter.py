"""Parser for Ren'Py's generated ``tl/<language>`` files.

This consumes the actual text emitted by Ren'Py 8.0.3's
``renpy.translation.generation.write_translates`` and ``write_strings``.
The adapter preserves official identifiers and does not derive IDs from
source location or ordinal.
"""

from __future__ import annotations

import re
import ast
from pathlib import Path

from .models import ExtractionSnapshot, SourceLocation, TranslationBlock, TranslationStatement

_TRANSLATE_RE = re.compile(r"^translate\s+(?P<language>\S+)\s+(?P<identifier>[^:]+):\s*$")
_SOURCE_RE = re.compile(r"^#\s+(?P<source>.+):(?P<line>\d+)\s*$")
_OLD_RE = re.compile(r'^\s*old\s+(?P<quote>\"|\')(?P<text>.*)(?P=quote)\s*$')
_NEW_RE = re.compile(r'^\s*new\s+(?P<quote>\"|\')(?P<text>.*)(?P=quote)\s*$')


def _source_location(value: str | None, fallback: SourceLocation) -> SourceLocation:
    if value is None:
        return fallback
    match = _SOURCE_RE.match(value.strip())
    if match is None:
        return fallback
    return SourceLocation(match.group("source"), int(match.group("line")))


def _unquote(value: str) -> str:
    # Generated tl strings use Ren'Py's quote_unicode escaping. Preserve text
    # faithfully enough for alignment while leaving unknown escapes intact.
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value[1:-1]
    return parsed if isinstance(parsed, str) else value[1:-1]


def _statement_text(code: str) -> str | None:
    if code.startswith("old "):
        match = _OLD_RE.match(code)
    elif code.startswith("new "):
        match = _NEW_RE.match(code)
    elif code.startswith(("voice ", "play ", "queue ", "show ", "scene ", "window ")):
        return None
    else:
        match = re.search(r'(?P<quote>\"|\')(?P<text>.*)(?P=quote)', code)
    if match is None:
        return None
    quote = match.group("quote")
    return _unquote(quote + match.group("text") + quote)


def _parse_file(path: Path, source_root: Path) -> list[TranslationBlock]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    blocks: list[TranslationBlock] = []
    index = 0
    while index < len(lines):
        header = _TRANSLATE_RE.match(lines[index])
        if header is None:
            index += 1
            continue
        identifier = header.group("identifier").strip()
        language = header.group("language")
        block_start = index
        index += 1
        entries: list[tuple[SourceLocation, str | None, str]] = []
        pending_source: str | None = None
        original_codes: list[str] = []
        translated_codes: list[str] = []
        translated_locations: list[SourceLocation] = []
        fallback_source = SourceLocation(str(path.relative_to(source_root)).replace("\\", "/"), 1)
        for previous in reversed(lines[:block_start]):
            if not previous.strip():
                continue
            if _SOURCE_RE.match(previous.strip()):
                pending_source = previous.strip()
            break
        header_location = _source_location(pending_source, fallback_source)
        while index < len(lines) and _TRANSLATE_RE.match(lines[index]) is None:
            line = lines[index]
            source_match = _SOURCE_RE.match(line.strip())
            if source_match and identifier == "strings":
                pending_source = line.strip()
            elif line.startswith("    # "):
                original_codes.append(line[6:])
            elif line.startswith("    ") and line.strip():
                translated_codes.append(line[4:])
                translated_locations.append(
                    _source_location(pending_source, fallback_source)
                    if identifier == "strings"
                    else header_location
                )
            index += 1

        if not translated_codes:
            continue
        block_location = translated_locations[0] if translated_locations else fallback_source
        for position, code in enumerate(translated_codes):
            source_code = original_codes[position] if position < len(original_codes) else None
            location = translated_locations[position] if position < len(translated_locations) else block_location
            entries.append((location, source_code, code))
        statements: list[TranslationStatement] = []
        for location, source_code, code in entries:
            kind = "string_old" if code.startswith("old ") else "string_new" if code.startswith("new ") else "renpy_statement"
            statements.append(
                TranslationStatement(
                    kind=kind,
                    text=_statement_text(code),
                    location=location,
                    raw=code,
                    source_code=source_code,
                )
            )
        first_location = statements[0].location
        block_id = identifier if identifier != "strings" else f"strings:{first_location.source}:{first_location.line}"
        blocks.append(
            TranslationBlock(
                id=block_id,
                identifier=identifier,
                statements=statements,
                location=first_location,
                metadata={
                    "language": language,
                    "official_file": str(path.relative_to(source_root)).replace("\\", "/"),
                    "source_code": [s.source_code for s in statements if s.source_code is not None],
                    "header_line": block_start + 1,
                },
            )
        )
    return blocks


def parse_translation_directory(tl_dir: Path, *, source: str | None = None) -> ExtractionSnapshot:
    """Parse all generated ``.rpy`` files below one official tl directory."""
    tl_dir = tl_dir.resolve()
    blocks: list[TranslationBlock] = []
    for path in sorted(tl_dir.rglob("*.rpy")):
        blocks.extend(_parse_file(path, tl_dir))
    return ExtractionSnapshot(
        backend="official",
        source=source or str(tl_dir.parent.parent),
        blocks=blocks,
        diagnostics=[f"parsed_official_tl_dir={tl_dir}"],
    )
