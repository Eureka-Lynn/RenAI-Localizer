"""Stable interchange models for extraction, review, and tl generation.

The unit of translation is a block, while statements preserve the source AST
shape. A block may therefore contain a say statement followed by attributes,
conditions, or other Ren'Py statements without flattening the story context.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceLocation:
    source: str
    line: int
    end_line: int | None = None


@dataclass(frozen=True)
class TranslationStatement:
    kind: str
    text: str | None
    location: SourceLocation
    speaker: str | None = None
    raw: str | None = None
    source_code: str | None = None


@dataclass(frozen=True)
class OccurrenceRecord:
    """One translatable source occurrence.

    Occurrences are deliberately not keyed by ``source_text``. Equal text in
    two locations is still two independently addressable translation units.
    """

    occurrence_id: str
    block_id: str
    official_identifier: str | None
    statement_index: int
    source_file: str
    source_line: int
    label: str | None
    speaker: str | None
    source_text: str
    translated_text: str | None
    raw_source_code: str | None
    raw_translated_code: str | None
    extraction_backend: str
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranslationBlock:
    """A source-local translation unit that can contain multiple statements."""

    id: str
    statements: list[TranslationStatement]
    location: SourceLocation
    identifier: str | None = None
    story: str | None = None
    scene: str | None = None
    characters: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def texts(self) -> list[str]:
        return [s.text for s in self.statements if s.text is not None]

    @property
    def text(self) -> str:
        """Convenience view; does not imply that occurrences are merged."""
        return "\n".join(self.texts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionSnapshot:
    backend: str
    source: str
    blocks: list[TranslationBlock] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "backend": self.backend,
            "source": self.source,
            "blocks": [b.to_dict() for b in self.blocks],
            "diagnostics": self.diagnostics,
        }
