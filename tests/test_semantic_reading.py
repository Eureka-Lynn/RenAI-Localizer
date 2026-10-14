import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from renai_localizer_v2.prompts import build_context_aware_prompt, build_single_unit_prompt
from renai_localizer_v2.semantic_reading import (
    DeterministicVerifier,
    FixtureReader,
    SemanticClaim,
    materialize_claim,
    run_semantic_reading,
    validate_claims,
)


def rows():
    return [
        {"occurrence_id": "a@scene:1:0", "source_file": "scene.rpy", "source_line": 1, "speaker": "avery", "source_text": "Hello Scarlet Hollow", "term_candidates": ["Scarlet Hollow"]},
        {"occurrence_id": "b@scene:2:0", "source_file": "scene.rpy", "source_line": 2, "speaker": "avery", "source_text": "Hello Scarlet Hollow", "term_candidates": ["Scarlet Hollow"]},
    ]


def test_claim_requires_real_source_refs_and_verifier_rejects_missing_refs():
    index = {row["occurrence_id"]: row for row in rows()}
    verifier = DeterministicVerifier(index, scene_occurrence_ids=set(index))
    claim = SemanticClaim("x", "fact", "x", "x", ["missing"], 0.5)
    decision = verifier.verify(claim)
    assert decision.decision == "unsupported"
    assert validate_claims([claim.to_dict()], index)


def test_pipeline_has_all_auditable_statuses_without_network():
    result = run_semantic_reading(rows(), {row["occurrence_id"]: row for row in rows()}, scene_id="scene-1", reader=FixtureReader())
    statuses = {claim["status"] for claim in result["claims"]}
    assert statuses == {"verified", "rejected", "unresolved"}
    assert result["llm"]["llm_used"] is False
    assert all(claim["source_refs"] for claim in result["claims"])


def test_unverified_claims_are_not_prompt_context_and_verified_character_is():
    occurrence = {"occurrence_id": "b@scene:2:0", "source_text": "Hi [name] {i}world{/i}", "speaker": "avery", "label": "start", "source_file": "scene.rpy", "source_line": 2}
    context = {"current_label": "start", "current_speaker": "avery", "scene_file": "scene.rpy", "variables": ["[name]"], "renpy_tags": ["{i}", "{/i}"], "source_refs": [{"source_file": "scene.rpy", "source_line": 2}]}
    semantic = {"occurrence_id": occurrence["occurrence_id"], "verified_claims": [{"claim_id": "ok", "kind": "character", "subject_id": "avery", "value": "known", "source_refs": ["a@scene:1:0"], "status": "verified"}, {"claim_id": "bad", "kind": "fact", "subject_id": "x", "value": "guess", "source_refs": ["b@scene:2:0"], "status": "unresolved"}], "unresolved_questions": ["guess"]}
    prompt = build_context_aware_prompt(occurrence, context, semantic_context=semantic)
    claims = prompt["context"]["semantic_context"]["verified_claims"]
    assert [claim["claim_id"] for claim in claims] == ["ok"]
    assert prompt["context"]["unresolved_questions"] == ["guess"]
    assert set(prompt["user"]) == set(build_single_unit_prompt(occurrence)["user"])
    assert prompt["context"]["variables"] == ["[name]"]
    assert prompt["context"]["renpy_tags"] == ["{i}", "{/i}"]


def test_duplicate_text_is_kept_as_two_occurrences():
    result = run_semantic_reading(rows(), {row["occurrence_id"]: row for row in rows()}, scene_id="scene-1")
    refs = {ref for claim in result["claims"] for ref in claim["source_refs"]}
    assert {"a@scene:1:0", "b@scene:2:0"}.issubset(refs)


def test_materialized_claim_tracks_transition_and_source_scope():
    source = rows()[0]
    verifier = DeterministicVerifier({source["occurrence_id"]: source}, scene_occurrence_ids={source["occurrence_id"]})
    claim = materialize_claim({"kind": "character", "subject_id": "avery", "value": "speaker", "source_refs": [source["occurrence_id"]], "confidence": 0.9}, scene_id="scene-1", verifier=verifier)
    assert claim.status == "verified"
    assert claim.status_history[0]["from"] == "candidate"
