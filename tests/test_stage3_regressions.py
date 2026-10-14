import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from renai_localizer_v2.context import _term_candidates
from renai_localizer_v2.prompts import build_context_aware_prompt, build_single_unit_prompt


def test_common_function_words_are_not_glossary_candidates():
    terms, _ = _term_candidates(
        "You For But The And Pearlanne Scarlet Biltmore Dustin",
        [],
        token_frequency={"pearlanne": 2, "scarlet": 2, "biltmore": 2, "dustin": 2},
    )
    assert {"You", "For", "But", "The", "And"}.isdisjoint(terms)
    assert {"Pearlanne", "Scarlet", "Biltmore", "Dustin"}.issubset(terms)


def test_markup_and_variables_are_not_candidates():
    terms, _ = _term_candidates(
        "{color=#f00}[player_name] Meet Dustin and say HELLO!",
        [],
        token_frequency={"dustin": 2, "hello": 2},
    )
    assert "player_name" not in terms
    assert "color" not in terms
    assert "Dustin" in terms
    assert "HELLO" in terms


def test_speaker_metadata_and_ordinary_surface_words_are_not_candidates():
    terms, _ = _term_candidates(
        "Everyone Listen There According Afraid WARNING Ah Hi Hmm Pearlanne Scarlet Biltmore Dustin",
        [],
        speaker="bs",
        token_frequency={"pearlanne": 2, "scarlet": 2, "biltmore": 2, "dustin": 2},
        non_initial_frequency={"pearlanne": 1, "scarlet": 1, "biltmore": 1, "dustin": 1},
    )
    assert {
        "Everyone",
        "Listen",
        "There",
        "According",
        "Afraid",
        "WARNING",
        "Ah",
        "Hi",
        "Hmm",
        "bs",
    }.isdisjoint(terms)
    assert {"Pearlanne", "Scarlet", "Biltmore", "Dustin"}.issubset(terms)


def test_generic_ui_source_is_not_glossary_evidence():
    assert _term_candidates("Search Item WARNING", [], suppress=True) == ([], [])


def test_prompt_output_schema_is_identical_and_context_is_bounded():
    occurrence = {
        "occurrence_id": "sample@game/script.rpy:4:0",
        "source_text": "Hello [name] {i}world{/i}",
        "speaker": "Dustin",
        "label": "start",
        "source_file": "game/script.rpy",
        "source_line": 4,
    }
    context = {
        "current_label": "start",
        "current_speaker": "Dustin",
        "scene_file": "game/script.rpy",
        "previous_blocks": [],
        "next_blocks": [],
        "recent_same_speaker": [],
        "variables": ["[name]"],
        "renpy_tags": ["{i}", "{/i}"],
        "term_candidates": ["Dustin"],
        "source_refs": [{"source_file": "game/script.rpy", "source_line": 4}],
    }
    story = {
        "project": "Scarlet Hollow",
        "version": None,
        "story_overview": None,
        "confirmed_world_facts": [],
        "confirmed_themes": [],
        "unresolved_questions": ["Needs review"],
        "source_refs": context["source_refs"],
        "confidence": None,
        "provenance": {"llm_used": False},
    }
    card = {
        "character_id": "Dustin",
        "name": "Dustin",
        "speech_style": None,
        "source_refs": context["source_refs"],
    }
    summary = {"scene_id": "scene-1", "source_file": "game/script.rpy", "label": "start"}
    glossary = {"source_term": "Dustin", "source_refs": context["source_refs"]}
    reader_context = {
        "occurrence_id": occurrence["occurrence_id"],
        "story_bible_refs": ["story_bible:scarlet_hollow"],
        "character_card_refs": ["character:Dustin"],
        "scene_summary_ref": "scene-1",
        "relevant_glossary_entries": ["glossary:Dustin"],
        "relevant_timeline_events": [],
        "unresolved_questions": ["Needs review"],
        "source_refs": context["source_refs"],
    }
    single = build_single_unit_prompt(occurrence)
    aware = build_context_aware_prompt(
        occurrence,
        context,
        reader_context=reader_context,
        story_bible=story,
        character_cards=[card],
        scene_summaries=[summary],
        glossary=[glossary],
    )
    assert set(single["response_schema"]) == {"occurrence_id", "translation", "notes"}
    assert single["response_schema"] == aware["response_schema"]
    assert aware["context"]["glossary_entries"] == [glossary]
    assert aware["context"]["character_cards"][0]["speech_style"] is None
    assert aware["context"]["variables"] == ["[name]"]
    assert aware["context"]["renpy_tags"] == ["{i}", "{/i}"]
    assert aware["context"]["timeline_events"] == []
    assert aware["context"]["local_context"] == context
    assert {
        "reader_context",
        "story_bible",
        "character_cards",
        "scene_summary",
        "timeline_events",
        "glossary_entries",
        "unresolved_questions",
        "local_context",
        "source_refs",
    }.issubset(aware["context"])


def test_checked_glossary_fixture_entries_have_source_refs():
    fixture = json.loads((Path(__file__).parents[1] / "data/glossary_fixture.json").read_text(encoding="utf-8"))
    terms = {entry["source_term"] for entry in fixture}
    assert {"Everyone", "Listen", "There", "According", "Afraid", "WARNING", "bs"}.isdisjoint(terms)
    assert {"Pearlanne", "Scarlet", "Biltmore", "Dustin"}.issubset(terms)
    assert all(entry.get("source_refs") for entry in fixture)
