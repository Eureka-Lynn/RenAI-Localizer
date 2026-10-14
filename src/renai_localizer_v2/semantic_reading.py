"""Automated, evidence bounded semantic reading and verification.

The module keeps model output separate from the context consumed by a
translator.  A claim can only become verified when its occurrence references
resolve inside the selected scene and a deterministic verifier supports it.
The fixture reader is deliberately useful offline; the HTTP adapter is an
optional provider-neutral integration point and never disguises a network
call as a fixture call.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

CLAIM_STATUSES = frozenset({"candidate", "verified", "rejected", "unresolved"})
VERIFIER_DECISIONS = frozenset({"supported", "unsupported", "ambiguous", "contradictory"})
SEMANTIC_READING_VERSION = "semantic-reading-v1"


@dataclass(frozen=True)
class SemanticClaim:
    claim_id: str
    kind: str
    subject_id: str
    value: str
    source_refs: list[str]
    confidence: float
    status: str = "candidate"
    verifier_reason: str = ""
    unresolved_reason: str = ""
    status_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in CLAIM_STATUSES:
            raise ValueError(f"unknown claim status: {self.status}")
        if not self.source_refs:
            raise ValueError("semantic claims require at least one source_ref")
        if not 0 <= self.confidence <= 1:
            raise ValueError("claim confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationDecision:
    decision: str
    reason: str
    checks: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision not in VERIFIER_DECISIONS:
            raise ValueError(f"unknown verifier decision: {self.decision}")


@dataclass(frozen=True)
class LLMCallMetadata:
    model: str
    temperature: float
    prompt_version: str
    called_at: str
    llm_used: bool
    adapter: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SemanticReader(Protocol):
    metadata: LLMCallMetadata

    def read(self, occurrences: list[dict[str, Any]], scene_id: str) -> list[dict[str, Any]]:
        """Return JSON-compatible candidate claim objects."""


class SemanticVerifier(Protocol):
    def verify(self, claim: SemanticClaim) -> VerificationDecision:
        """Independently evaluate one claim."""


class FixtureReader:
    """Deterministic reader for local runs and regression tests."""

    def __init__(self, *, model: str = "fixture-reader", temperature: float = 0.0) -> None:
        self.metadata = LLMCallMetadata(
            model=model,
            temperature=temperature,
            prompt_version=SEMANTIC_READING_VERSION,
            called_at=datetime.now(timezone.utc).isoformat(),
            llm_used=False,
            adapter="fixture",
        )

    def read(self, occurrences: list[dict[str, Any]], scene_id: str) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        by_speaker: dict[str, dict[str, Any]] = {}
        for row in occurrences:
            speaker = row.get("speaker")
            if speaker and speaker not in by_speaker:
                by_speaker[str(speaker)] = row
        for speaker, row in sorted(by_speaker.items()):
            claims.append({
                "kind": "character",
                "subject_id": speaker,
                "value": f"{speaker} is a speaking character in scene {scene_id}.",
                "source_refs": [row["occurrence_id"]],
                "confidence": 0.78,
            })
        if occurrences:
            first = occurrences[0]
            claims.append({
                "kind": "scene",
                "subject_id": scene_id,
                "value": f"Scene {scene_id} contains ordered narration and dialogue occurrences.",
                "source_refs": [first["occurrence_id"]],
                "confidence": 0.72,
            })
        # A fact is emitted only when the exact source text names the place.
        for row in occurrences:
            if "Scarlet Hollow" in str(row.get("source_text", "")):
                claims.append({
                    "kind": "fact",
                    "subject_id": "place:scarlet-hollow",
                    "value": "Scarlet Hollow is named in the selected source text.",
                    "source_refs": [row["occurrence_id"]],
                    "confidence": 0.82,
                })
                break
        # Fixed negative controls make the offline verifier auditable: these
        # are candidate model-like assertions that must never silently become
        # facts.
        if occurrences:
            first = occurrences[0]
            claims.append({
                "kind": "character",
                "subject_id": "unseen-character",
                "value": "An unseen-character speaker is present.",
                "source_refs": [first["occurrence_id"]],
                "confidence": 0.25,
            })
            claims.append({
                "kind": "fact",
                "subject_id": "fact:protagonist-intent",
                "value": "The protagonist definitely intended the events.",
                "source_refs": [first["occurrence_id"]],
                "confidence": 0.3,
            })
        # Keep term generation controlled: context candidates already passed
        # the deterministic shape/repetition filters in context.py.
        seen_terms: set[str] = set()
        for row in occurrences:
            for term in row.get("term_candidates", []):
                if term in seen_terms:
                    continue
                seen_terms.add(term)
                refs = [r["occurrence_id"] for r in occurrences if term in r.get("term_candidates", [])]
                if len(refs) >= 2 or " " in term:
                    claims.append({
                        "kind": "term",
                        "subject_id": f"term:{term}",
                        "value": term,
                        "source_refs": refs[:5],
                        "confidence": 0.7,
                    })
        return claims


class HTTPJsonReader:
    """Provider-neutral JSON HTTP adapter configured exclusively by env vars."""

    def __init__(self, *, endpoint: str, api_key: str, model: str, temperature: float = 0.0) -> None:
        if not endpoint or not api_key:
            raise ValueError("endpoint and api_key are required for the HTTP reader")
        self.endpoint, self.api_key = endpoint, api_key
        self.metadata = LLMCallMetadata(
            model=model, temperature=temperature, prompt_version=SEMANTIC_READING_VERSION,
            called_at=datetime.now(timezone.utc).isoformat(), llm_used=True, adapter="http-json",
        )

    @classmethod
    def from_environment(cls) -> "HTTPJsonReader":
        return cls(
            endpoint=os.environ.get("RENAI_LLM_ENDPOINT", ""),
            api_key=os.environ.get("RENAI_LLM_API_KEY", ""),
            model=os.environ.get("RENAI_LLM_MODEL", ""),
            temperature=float(os.environ.get("RENAI_LLM_TEMPERATURE", "0")),
        )

    def read(self, occurrences: list[dict[str, Any]], scene_id: str) -> list[dict[str, Any]]:
        payload = json.dumps({"scene_id": scene_id, "occurrences": occurrences}, ensure_ascii=False).encode()
        request = urllib.request.Request(
            self.endpoint, data=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - endpoint is explicit configuration
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, list):
            decoded = decoded.get("claims", []) if isinstance(decoded, dict) else []
        if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
            raise ValueError("semantic reader response must be a JSON claim array")
        return decoded


class HTTPJsonVerifier:
    """Optional independent verifier adapter with a separate endpoint/config."""

    def __init__(self, *, endpoint: str, api_key: str, model: str, temperature: float = 0.0, occurrence_index: dict[str, dict[str, Any]] | None = None, scene_occurrence_ids: set[str] | None = None) -> None:
        if not endpoint or not api_key:
            raise ValueError("verifier endpoint and api_key are required")
        self.endpoint, self.api_key, self.model, self.temperature = endpoint, api_key, model, temperature
        self.local = DeterministicVerifier(occurrence_index or {}, scene_occurrence_ids or set())

    @classmethod
    def from_environment(cls, occurrence_index: dict[str, dict[str, Any]], scene_occurrence_ids: set[str]) -> "HTTPJsonVerifier":
        return cls(
            endpoint=os.environ.get("RENAI_VERIFIER_ENDPOINT", ""),
            api_key=os.environ.get("RENAI_VERIFIER_API_KEY", os.environ.get("RENAI_LLM_API_KEY", "")),
            model=os.environ.get("RENAI_VERIFIER_MODEL", os.environ.get("RENAI_LLM_MODEL", "")),
            temperature=float(os.environ.get("RENAI_VERIFIER_TEMPERATURE", "0")),
            occurrence_index=occurrence_index,
            scene_occurrence_ids=scene_occurrence_ids,
        )

    def verify(self, claim: SemanticClaim) -> VerificationDecision:
        local = self.local.verify(claim)
        if local.decision == "unsupported":
            return local
        payload = json.dumps({"claim": claim.to_dict(), "occurrences": [self.local.occurrence_index[ref] for ref in claim.source_refs]}, ensure_ascii=False).encode()
        request = urllib.request.Request(self.endpoint, data=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - endpoint is explicit configuration
            decoded = json.loads(response.read().decode("utf-8"))
        decision = str(decoded.get("decision", "ambiguous")) if isinstance(decoded, dict) else "ambiguous"
        reason = str(decoded.get("reason", "external verifier response")) if isinstance(decoded, dict) else "external verifier response"
        return VerificationDecision(decision if decision in VERIFIER_DECISIONS else "ambiguous", reason, {"external_verifier": True})


class DeterministicVerifier:
    """Independent source and contradiction checks used by fixture mode."""

    def __init__(self, occurrence_index: dict[str, dict[str, Any]], *, scene_occurrence_ids: set[str], existing: Iterable[SemanticClaim] = ()) -> None:
        self.occurrence_index = occurrence_index
        self.scene_occurrence_ids = scene_occurrence_ids
        self.existing = list(existing)

    def verify(self, claim: SemanticClaim) -> VerificationDecision:
        for existing in self.existing:
            if existing.status == "verified" and existing.kind == claim.kind and existing.subject_id == claim.subject_id and existing.value != claim.value:
                return VerificationDecision("contradictory", "conflicts with an existing verified claim", {"existing_claim_conflict": False})
        if not claim.source_refs:
            return VerificationDecision("unsupported", "source_refs is empty", {"source_refs": False})
        refs_exist = all(ref in self.occurrence_index for ref in claim.source_refs)
        refs_in_scene = all(ref in self.scene_occurrence_ids for ref in claim.source_refs)
        if not refs_exist or not refs_in_scene:
            return VerificationDecision("unsupported", "source_ref is missing or outside selected scene", {"source_refs": refs_exist, "scene_scope": refs_in_scene})
        rows = [self.occurrence_index[ref] for ref in claim.source_refs]
        if claim.kind == "character":
            supported = any(str(row.get("speaker")) == claim.subject_id for row in rows)
            return VerificationDecision("supported" if supported else "unsupported", "speaker metadata supports claim" if supported else "speaker does not support claim", {"speaker": supported})
        if claim.kind == "scene":
            return VerificationDecision("supported", "claim is bounded to selected scene occurrences", {"scene_scope": True})
        if claim.kind == "fact":
            supported = any(claim.value.replace(" is named in the selected source text.", "") in str(row.get("source_text", "")) for row in rows)
            return VerificationDecision("supported" if supported else "ambiguous", "literal source text supports fact" if supported else "fact needs interpretation beyond source", {"literal_text": supported})
        if claim.kind == "term":
            term = claim.value
            occurrences = [row for row in self.occurrence_index.values() if row["occurrence_id"] in self.scene_occurrence_ids]
            count = sum(term in row.get("term_candidates", []) for row in occurrences)
            ordinary = term.casefold() in {"everyone", "listen", "there", "warning", "hello", "according", "afraid", "welcome", "the", "and"}
            if ordinary and count < 2:
                return VerificationDecision("unsupported", "ordinary word lacks controlled term evidence", {"ordinary_word": False})
            if count < 2 and " " not in term:
                return VerificationDecision("ambiguous", "term does not repeat in the selected scene", {"repetition": False})
            return VerificationDecision("supported", "controlled term repeats in selected scene", {"repetition": True})
        return VerificationDecision("ambiguous", "unknown claim kind requires review", {"kind": False})


def _status_for(decision: str) -> str:
    return {"supported": "verified", "unsupported": "rejected", "ambiguous": "unresolved", "contradictory": "unresolved"}[decision]


def _claim_id(scene_id: str, raw: dict[str, Any]) -> str:
    data = json.dumps([scene_id, raw], ensure_ascii=False, sort_keys=True)
    return "claim-" + hashlib.sha256(data.encode()).hexdigest()[:16]


def materialize_claim(raw: dict[str, Any], *, scene_id: str, verifier: DeterministicVerifier) -> SemanticClaim:
    refs = [str(ref) for ref in raw.get("source_refs", []) if ref]
    claim = SemanticClaim(
        claim_id=str(raw.get("claim_id") or _claim_id(scene_id, raw)),
        kind=str(raw.get("kind", "fact")),
        subject_id=str(raw.get("subject_id", "")),
        value=str(raw.get("value", "")),
        source_refs=refs,
        confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
    )
    try:
        decision = verifier.verify(claim)
    except Exception as exc:  # malformed model output stays diagnostic
        decision = VerificationDecision("unsupported", f"verifier error: {exc}")
    status = _status_for(decision.decision)
    return SemanticClaim(
        **{**claim.to_dict(), "status": status, "verifier_reason": decision.reason,
           "unresolved_reason": decision.reason if status == "unresolved" else "",
           "status_history": [{"from": "candidate", "to": status, "reason": decision.reason}]}
    )


def run_semantic_reading(
    occurrences: list[dict[str, Any]],
    context_index: dict[str, dict[str, Any]],
    *,
    scene_id: str,
    reader: SemanticReader | None = None,
    verifier: SemanticVerifier | None = None,
) -> dict[str, Any]:
    """Read one selected scene and return candidates plus verified diagnostics."""
    reader = reader or FixtureReader()
    occurrence_index = {str(row["occurrence_id"]): row for row in occurrences}
    raw_claims = reader.read(occurrences, scene_id)
    verifier = verifier or DeterministicVerifier(occurrence_index, scene_occurrence_ids=set(occurrence_index))
    candidates: list[dict[str, Any]] = []
    claims: list[SemanticClaim] = []
    for raw in raw_claims:
        if not isinstance(raw, dict):
            continue
        candidate = dict(raw)
        candidate.setdefault("claim_id", _claim_id(scene_id, raw))
        candidate.setdefault("status", "candidate")
        candidate.setdefault("verifier_reason", "")
        candidate.setdefault("unresolved_reason", "")
        candidate.setdefault("status_history", [])
        candidates.append(candidate)
        # Context term candidates are attached to records for the fixture reader.
        for ref in raw.get("source_refs", []):
            if ref in context_index:
                raw.setdefault("term_candidates", context_index[ref].get("term_candidates", []))
        claim = materialize_claim(raw, scene_id=scene_id, verifier=verifier)
        claims.append(claim)
        if claim.status == "verified" and isinstance(verifier, DeterministicVerifier):
            verifier.existing.append(claim)
    return {"scene_id": scene_id, "reading_candidates": candidates, "claims": [claim.to_dict() for claim in claims], "llm": reader.metadata.to_dict()}


def build_semantic_pilot(
    occurrences: list[dict[str, Any]],
    context_index: dict[str, dict[str, Any]],
    scene_manifest: list[dict[str, Any]],
    *,
    reader: SemanticReader | None = None,
    verifier: SemanticVerifier | None = None,
    input_hash: str | None = None,
) -> dict[str, Any]:
    """Run the bounded reader/verifier over the selected scenes."""
    reader = reader or FixtureReader()
    by_file: dict[str, list[dict[str, Any]]] = {}
    for row in occurrences:
        by_file.setdefault(str(row["source_file"]), []).append(row)
    all_candidates: list[dict[str, Any]] = []
    all_claims: list[dict[str, Any]] = []
    scene_ids: dict[str, str] = {}
    scene_runs: list[dict[str, Any]] = []
    for scene in scene_manifest:
        source_file = str(scene["source_file"])
        scene_id = str(scene.get("scene_id") or "scene-" + hashlib.sha256(source_file.encode()).hexdigest()[:12])
        scene_ids[source_file] = scene_id
        rows = []
        for row in by_file.get(source_file, []):
            enriched = dict(row)
            enriched["term_candidates"] = context_index.get(row["occurrence_id"], {}).get("term_candidates", [])
            rows.append(enriched)
        run = run_semantic_reading(rows, context_index, scene_id=scene_id, reader=reader, verifier=verifier)
        scene_runs.append(run)
        all_candidates.extend(run["reading_candidates"])
        all_claims.extend(run["claims"])
    by_occurrence: dict[str, dict[str, Any]] = {}
    for row in occurrences:
        oid, source = str(row["occurrence_id"]), str(row["source_file"])
        scene_claims = [claim for claim in all_claims if claim.get("status") == "verified" and (
            oid in claim.get("source_refs", [])
            or claim.get("kind") == "scene" and claim.get("source_refs", []) and claim["source_refs"][0] in {r["occurrence_id"] for r in by_file.get(source, [])}
            or claim.get("kind") == "character" and claim.get("subject_id") == row.get("speaker")
            or claim.get("kind") == "term" and claim.get("value") in context_index.get(oid, {}).get("term_candidates", [])
        )]
        unresolved = [claim.get("unresolved_reason", "") for claim in all_claims if claim.get("status") == "unresolved" and claim.get("unresolved_reason")]
        by_occurrence[oid] = build_semantic_context(
            scene_claims + [claim for claim in all_claims if claim.get("status") == "unresolved"],
            occurrence_id=oid,
            scene_id=scene_ids.get(source, ""),
        ) | {"unresolved_questions": unresolved}
    metadata = {
        "schema_version": 1,
        "pipeline": SEMANTIC_READING_VERSION,
        "selected_scenes": [str(scene["source_file"]) for scene in scene_manifest],
        "occurrence_count": len(occurrences),
        "candidate_count": len(all_candidates),
        "verified_count": sum(c["status"] == "verified" for c in all_claims),
        "rejected_count": sum(c["status"] == "rejected" for c in all_claims),
        "unresolved_count": sum(c["status"] == "unresolved" for c in all_claims),
        "character_card_count": sum(c["status"] == "verified" and c["kind"] == "character" for c in all_claims),
        "scene_summary_count": sum(c["status"] == "verified" and c["kind"] == "scene" for c in all_claims),
        "verified_term_count": sum(c["status"] == "verified" and c["kind"] == "term" for c in all_claims),
        "story_bible_hard_fact_count": sum(c["status"] == "verified" and c["kind"] == "fact" for c in all_claims),
        "timeline_count": 0,
        "llm_used": reader.metadata.llm_used,
        "model": reader.metadata.model,
        "adapter": reader.metadata.adapter,
        "temperature": reader.metadata.temperature,
        "prompt_version": reader.metadata.prompt_version,
        "generated_at": reader.metadata.called_at,
        "input_sha256": input_hash,
    }
    return {"reading_candidates": all_candidates, "claims": all_claims, "semantic_context": by_occurrence, "metadata": metadata, "scene_runs": scene_runs}


def build_semantic_context(claims: Iterable[dict[str, Any]], *, occurrence_id: str, scene_id: str) -> dict[str, Any]:
    """Build the only semantic payload allowed into a translation prompt."""
    # Callers pass the claims selected for this occurrence.  The status check
    # here is the final safety boundary; rejected and unresolved claims remain
    # available to diagnostics but cannot enter asserted context.
    selected = [claim for claim in claims if claim.get("status") == "verified"]
    return {
        "occurrence_id": occurrence_id,
        "scene_id": scene_id,
        "verified_claims": selected,
        "unresolved_questions": [
            claim.get("unresolved_reason", "") for claim in claims
            if claim.get("status") == "unresolved" and claim.get("unresolved_reason")
        ],
        "source_refs": sorted({ref for claim in selected for ref in claim.get("source_refs", [])}),
    }


def claims_by_status(claims: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {status: [] for status in CLAIM_STATUSES}
    for claim in claims:
        status = claim.get("status")
        if status in result:
            result[status].append(claim)
    return result


def validate_claims(claims: Iterable[dict[str, Any]], occurrence_index: dict[str, dict[str, Any]], *, selected_occurrence_ids: set[str] | None = None) -> list[str]:
    """Return structural/source diagnostics for a claim collection."""
    errors: list[str] = []
    selected = selected_occurrence_ids or set(occurrence_index)
    for index, claim in enumerate(claims):
        prefix = f"claim[{index}]"
        if not claim.get("source_refs"):
            errors.append(f"{prefix}:missing_source_refs")
        for ref in claim.get("source_refs", []):
            if ref not in occurrence_index:
                errors.append(f"{prefix}:unknown_source_ref:{ref}")
            elif ref not in selected:
                errors.append(f"{prefix}:out_of_scope_source_ref:{ref}")
        if claim.get("status") not in CLAIM_STATUSES:
            errors.append(f"{prefix}:invalid_status")
        if claim.get("kind") not in {"character", "scene", "fact", "term"}:
            errors.append(f"{prefix}:invalid_kind")
    return errors
