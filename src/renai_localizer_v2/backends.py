"""Extraction backend contracts and deliberately separate implementations."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Protocol, Sequence

from .models import ExtractionSnapshot, SourceLocation, TranslationBlock, TranslationStatement


class BackendUnavailable(RuntimeError):
    """Raised when a backend cannot run in the current environment."""


class ExtractionBackend(Protocol):
    name: str

    def extract(self, source: Path) -> ExtractionSnapshot:
        """Extract source into ordered blocks without losing occurrences."""
        ...


def _block_id(source: str, line: int, ordinal: int) -> str:
    digest = hashlib.sha256(f"{source}:{line}:{ordinal}".encode()).hexdigest()[:12]
    return f"block-{digest}"


class OfficialStaticBackend:
    """Adapter for Ren'Py's own translation generation command.

    No CLI syntax is invented here. ``command`` must be supplied by the caller
    as the exact launcher command documented by the installed Ren'Py version.
    The command's stdout must be a v2 snapshot JSON document unless an adapter
    is provided. No Ren'Py arguments are invented by this class.
    """

    name = "official"

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        adapter: Callable[[Path], ExtractionSnapshot] | None = None,
        tl_dir: Path | None = None,
    ) -> None:
        self.command = list(command) if command else None
        self.adapter = adapter
        self.tl_dir = tl_dir

    @staticmethod
    def probe() -> dict[str, str | bool]:
        python_module = False
        try:
            importlib.import_module("renpy")
            python_module = True
        except Exception:
            pass
        launcher = shutil.which("renpy") or shutil.which("renpy.exe") or shutil.which("renpy.sh")
        return {
            "python_module": python_module,
            "launcher": launcher or "",
            "available": bool(python_module or launcher),
        }

    def extract(self, source: Path) -> ExtractionSnapshot:
        if self.adapter is not None:
            return self.adapter(source)
        if not self.command:
            probe = self.probe()
            raise BackendUnavailable(
                "Ren'Py official extraction is blocked: no adapter or explicitly "
                f"configured launcher command (probe={probe}). Configure the exact "
                "command for the installed Ren'Py version; v2 does not guess CLI flags."
            )
        argv = [arg.replace("{source}", os.fspath(source)) for arg in self.command]
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        if completed.returncode:
            raise BackendUnavailable(
                f"Official command failed with exit code {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        if self.tl_dir is not None:
            from .official_adapter import parse_translation_directory

            if not self.tl_dir.exists():
                raise BackendUnavailable(f"Official command did not create tl directory: {self.tl_dir}")
            return parse_translation_directory(self.tl_dir, source=os.fspath(source))
        try:
            return snapshot_from_mapping(json.loads(completed.stdout))
        except Exception as exc:
            raise BackendUnavailable(
                "Official command completed but stdout was not a v2 snapshot JSON and "
                "no tl_dir was configured for the generated Ren'Py output."
            ) from exc


class RuntimeBackend:
    """Runtime extraction seam for a running Ren'Py process or bridge."""

    name = "runtime"

    def __init__(self, extractor: Callable[[Path], ExtractionSnapshot] | None = None) -> None:
        self.extractor = extractor

    def extract(self, source: Path) -> ExtractionSnapshot:
        if self.extractor is None:
            raise BackendUnavailable(
                "Runtime extraction is not configured: provide a Ren'Py runtime bridge."
            )
        return self.extractor(source)


def run_backend(backend: ExtractionBackend, source: Path) -> ExtractionSnapshot:
    return backend.extract(source)


def snapshot_from_mapping(data: dict[str, object]) -> ExtractionSnapshot:
    """Decode the JSON contract used between official adapters and v2."""
    blocks: list[TranslationBlock] = []
    for raw_block in data.get("blocks", []):
        item = raw_block  # type: ignore[assignment]
        loc = SourceLocation(**item["location"])
        statements = [
            TranslationStatement(
                location=SourceLocation(**statement["location"]),
                **{key: value for key, value in statement.items() if key != "location"},
            )
            for statement in item["statements"]
        ]
        blocks.append(
            TranslationBlock(
                location=loc,
                statements=statements,
                **{key: value for key, value in item.items() if key not in {"location", "statements"}},
            )
        )
    return ExtractionSnapshot(
        backend=str(data["backend"]),
        source=str(data["source"]),
        blocks=blocks,
        diagnostics=list(data.get("diagnostics", [])),
    )
