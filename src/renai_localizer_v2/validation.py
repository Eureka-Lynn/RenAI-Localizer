"""Deterministic translation response and Ren'Py constraint validation."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

_VARIABLE_RE = re.compile(r"\[[^\[\]\r\n]+\]")
_TAG_RE = re.compile(r"\{[^{}\r\n]*\}")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    checks: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "checks": self.checks}


def _same_counter(source: str, translated: str, pattern: re.Pattern[str]) -> bool:
    return Counter(pattern.findall(source)) == Counter(pattern.findall(translated))


def validate_translation_constraints(
    source_text: str,
    translated_text: str,
    *,
    source_statement_count: int = 1,
    translated_statement_count: int = 1,
) -> ValidationResult:
    """Check syntax-sensitive content without judging translation quality."""
    checks = {
        "placeholders": _same_counter(source_text, translated_text, _VARIABLE_RE),
        "text_tags": _same_counter(source_text, translated_text, _TAG_RE),
        "percent_signs": source_text.count("%") == translated_text.count("%"),
        "backslashes": source_text.count("\\") == translated_text.count("\\"),
        "newlines": source_text.count("\n") == translated_text.count("\n"),
        "statement_count": source_statement_count == translated_statement_count,
    }
    errors = [name for name, passed in checks.items() if not passed]
    return ValidationResult(not errors, errors, checks)


def validate_translation_response(
    response: str | dict[str, Any],
    *,
    occurrence_id: str,
    source_text: str,
    source_statement_count: int = 1,
    translated_statement_count: int = 1,
) -> ValidationResult:
    """Validate the exact JSON response contract plus source constraints."""
    errors: list[str] = []
    payload: dict[str, Any]
    if isinstance(response, str):
        try:
            decoded = json.loads(response)
        except json.JSONDecodeError:
            return ValidationResult(False, ["invalid_json"], {"json": False})
        if not isinstance(decoded, dict):
            return ValidationResult(False, ["response_not_object"], {"json": True, "object": False})
        payload = decoded
    else:
        if not isinstance(response, dict):
            return ValidationResult(False, ["response_not_object"], {"json": True, "object": False})
        payload = response
    required = {"occurrence_id", "translation", "notes"}
    if set(payload) != required:
        errors.append("response_keys")
    if payload.get("occurrence_id") != occurrence_id:
        errors.append("occurrence_id")
    if not isinstance(payload.get("translation"), str):
        errors.append("translation_type")
    if not isinstance(payload.get("notes"), list) or not all(
        isinstance(note, str) for note in payload.get("notes", [])
    ):
        errors.append("notes_type")
    if isinstance(payload.get("translation"), str):
        result = validate_translation_constraints(
            source_text,
            payload["translation"],
            source_statement_count=source_statement_count,
            translated_statement_count=translated_statement_count,
        )
        errors.extend(result.errors)
        checks = {"json": True, "object": True, **result.checks}
    else:
        checks = {"json": True, "object": True}
    return ValidationResult(not errors, errors, checks)


# Short alias for callers that treat this as a generic technical constraint check.
validate_constraints = validate_translation_constraints
