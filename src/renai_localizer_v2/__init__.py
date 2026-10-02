"""RenAI Localizer v2: official extraction first."""

from .models import ExtractionSnapshot, OccurrenceRecord, TranslationBlock, TranslationStatement
from .official_adapter import parse_translation_directory
from .coverage import build_occurrence_records, collapse_occurrences_to_mtool, compare_coverage, enrich_snapshot
from .context import build_context_index
from .prompts import build_context_aware_prompt, build_prompt_fixtures, build_single_unit_prompt
from .validation import validate_constraints, validate_translation_constraints, validate_translation_response
from .reader_context import (
    CharacterCard,
    GlossaryEntry,
    ReaderContext,
    SceneSummary,
    SourceRef,
    StoryBible,
    TimelineEvent,
    build_reader_context_artifacts,
)

__all__ = [
    "ExtractionSnapshot",
    "TranslationBlock",
    "TranslationStatement",
    "OccurrenceRecord",
    "parse_translation_directory",
    "build_occurrence_records",
    "collapse_occurrences_to_mtool",
    "compare_coverage",
    "enrich_snapshot",
    "build_context_index",
    "build_single_unit_prompt",
    "build_context_aware_prompt",
    "build_prompt_fixtures",
    "validate_constraints",
    "validate_translation_constraints",
    "validate_translation_response",
    "SourceRef",
    "StoryBible",
    "CharacterCard",
    "SceneSummary",
    "TimelineEvent",
    "GlossaryEntry",
    "ReaderContext",
    "build_reader_context_artifacts",
]
