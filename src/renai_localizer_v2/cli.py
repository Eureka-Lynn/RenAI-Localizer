"""Small, dependency-free v2 CLI for extraction probes and comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backends import (
    OfficialStaticBackend,
    snapshot_from_mapping,
)
from .baseline import assess_alignment, load_mtool_baseline
from .compare import build_report
from .context import build_context_index
from .coverage import (
    build_occurrence_records,
    collapse_occurrences_to_mtool,
    compare_coverage,
    enrich_snapshot,
)
from .official_adapter import parse_translation_directory
from .prompts import build_prompt_fixtures
from .reader_context import _selected_snapshot, build_reader_context_artifacts
from .semantic_reading import (
    HTTPJsonVerifier,
    HTTPJsonReader,
    FixtureReader,
    build_semantic_pilot,
    claims_by_status,
    validate_claims,
)
from .validation import validate_translation_response


def main() -> int:
    parser = argparse.ArgumentParser(prog="renai-localizer-v2")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe-official", help="probe for an installed Ren'Py runtime/launcher")
    probe.add_argument("--json", action="store_true")
    compare = sub.add_parser("compare", help="compare an official snapshot with an explicit MTool baseline")
    compare.add_argument("source", type=Path, nargs="?", help="official snapshot path (compatibility alias)")
    compare.add_argument("--mtool", type=Path)
    compare.add_argument("--official-json", type=Path)
    compare.add_argument("--official-file", default=None, help="limit official snapshot to one generated tl file")
    compare.add_argument("-o", "--output", type=Path)
    adapt = sub.add_parser("adapt-official", help="convert generated Ren'Py tl files to a v2 snapshot")
    adapt.add_argument("tl_dir", type=Path)
    adapt.add_argument("-o", "--output", type=Path, required=True)
    adapt.add_argument("--source", default=None)
    coverage = sub.add_parser("coverage", help="compare official Scarlet Hollow occurrences with an MTool extraction baseline")
    coverage.add_argument("official_json", type=Path)
    coverage.add_argument("--mtool", type=Path, required=True)
    coverage.add_argument("--game-root", type=Path, required=True)
    coverage.add_argument("-o", "--output", type=Path, required=True)
    coverage.add_argument("--occurrences-output", type=Path)
    coverage.add_argument("--mtool-output", type=Path)
    context = sub.add_parser("context-index", help="build a deterministic occurrence context index")
    context.add_argument("official_json", type=Path)
    context.add_argument("--mtool", type=Path, required=True)
    context.add_argument("--game-root", type=Path)
    context.add_argument("-o", "--output", type=Path, required=True)
    prompts = sub.add_parser("prompt-fixtures", help="write single and context-aware prompt fixtures")
    prompts.add_argument("official_json", type=Path)
    prompts.add_argument("--mtool", type=Path, required=True)
    prompts.add_argument("--game-root", type=Path)
    prompts.add_argument("--occurrence-id", action="append", dest="occurrence_ids")
    prompts.add_argument("--sample-count", type=int, default=1)
    prompts.add_argument("--language", default="简体中文")
    prompts.add_argument(
        "--reader-context-dir",
        type=Path,
        help="directory containing Reader Context fixture JSON files",
    )
    prompts.add_argument("-o", "--output", type=Path, required=True)
    validate = sub.add_parser("validate-response", help="validate one translation JSON response")
    validate.add_argument("response", type=Path, help="JSON file containing the provider response")
    validate.add_argument("--occurrence-id", required=True)
    validate.add_argument("--source-text", required=True)
    validate.add_argument("--source-statement-count", type=int, default=1)
    validate.add_argument("--translated-statement-count", type=int, default=1)
    reader = sub.add_parser("reader-fixtures", help="build bounded Stage 3 Reader Context fixtures")
    reader.add_argument("official_json", type=Path)
    reader.add_argument("--mtool", type=Path, required=True)
    reader.add_argument("--game-root", type=Path)
    reader.add_argument("--scene-manifest", type=Path, required=True)
    reader.add_argument("--run-metadata", type=Path)
    reader.add_argument("-o", "--output-dir", type=Path, required=True)
    pilot = sub.add_parser("semantic-pilot", help="run bounded semantic reading and automatic verification")
    pilot.add_argument("official_json", type=Path)
    pilot.add_argument("--mtool", type=Path, required=True)
    pilot.add_argument("--game-root", type=Path)
    pilot.add_argument("--scene-manifest", type=Path, required=True)
    pilot.add_argument("--run-metadata", type=Path)
    pilot.add_argument("--llm", choices=("fixture", "http"), default="fixture")
    pilot.add_argument("-o", "--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "probe-official":
        value = OfficialStaticBackend.probe()
        print(json.dumps(value, ensure_ascii=False, indent=2) if args.json else value)
        return 0

    if args.command == "adapt-official":
        snapshot = parse_translation_directory(args.tl_dir, source=args.source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.output} ({len(snapshot.blocks)} blocks)")
        return 0

    if args.command == "coverage":
        snapshot = enrich_snapshot(_snapshot_from_json(args.official_json), args.game_root)
        mtool = load_mtool_baseline(args.mtool)
        report = compare_coverage(snapshot, mtool)
        report["inputs"] = {
            "official_snapshot": str(args.official_json),
            "game_root": str(args.game_root),
            "mtool_extraction_baseline": str(args.mtool),
        }
        records = report.pop("records")
        if args.occurrences_output:
            args.occurrences_output.parent.mkdir(parents=True, exist_ok=True)
            with args.occurrences_output.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            report["occurrences_output"] = str(args.occurrences_output)
        else:
            report["occurrences"] = records
        if args.mtool_output:
            export = collapse_occurrences_to_mtool(records)
            args.mtool_output.parent.mkdir(parents=True, exist_ok=True)
            args.mtool_output.write_text(json.dumps(export, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["mtool_export"] = {
                "path": str(args.mtool_output),
                "collision_count": export["collision_count"],
                "key_count": len(export["data"]),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report["coverage"], ensure_ascii=False, indent=2))
        return 0

    if args.command == "context-index":
        snapshot = _snapshot_from_json(args.official_json)
        baseline = load_mtool_baseline(args.mtool)
        index = build_context_index(snapshot, baseline, game_root=args.game_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.output} ({len(index)} occurrences)")
        return 0

    if args.command == "prompt-fixtures":
        snapshot = _snapshot_from_json(args.official_json)
        baseline = load_mtool_baseline(args.mtool)
        records = build_occurrence_records(snapshot, baseline)
        if args.game_root:
            snapshot = enrich_snapshot(snapshot, args.game_root)
            records = build_occurrence_records(snapshot, baseline)
        index = build_context_index(snapshot, baseline)
        selected = (
            [row for row in records if row["occurrence_id"] in set(args.occurrence_ids or [])]
            if args.occurrence_ids
            else records[: max(0, args.sample_count)]
        )
        reader_inputs = _load_reader_context_inputs(args.reader_context_dir)
        fixture = build_prompt_fixtures(
            selected,
            index,
            target_language=args.language,
            **reader_inputs,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.output} ({len(selected)} selected occurrences)")
        return 0

    if args.command == "validate-response":
        payload = json.loads(args.response.read_text(encoding="utf-8"))
        result = validate_translation_response(
            payload,
            occurrence_id=args.occurrence_id,
            source_text=args.source_text,
            source_statement_count=args.source_statement_count,
            translated_statement_count=args.translated_statement_count,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.valid else 1

    if args.command == "reader-fixtures":
        snapshot = _snapshot_from_json(args.official_json)
        baseline = load_mtool_baseline(args.mtool)
        manifest = json.loads(args.scene_manifest.read_text(encoding="utf-8"))
        scenes = manifest.get("scenes") if isinstance(manifest, dict) else manifest
        if not isinstance(scenes, list) or not all(isinstance(scene, dict) for scene in scenes):
            parser.error("scene manifest must contain a JSON object with a scenes array")
        metadata = (
            json.loads(args.run_metadata.read_text(encoding="utf-8"))
            if args.run_metadata
            else {}
        )
        artifacts = build_reader_context_artifacts(
            snapshot,
            baseline,
            scenes,
            game_root=args.game_root,
            run_metadata=metadata,
        )
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "story_bible_fixture.json": artifacts["story_bible"],
            "character_cards_fixture.json": artifacts["character_cards"],
            "scene_summaries_fixture.json": artifacts["scene_summaries"],
            "timeline_fixture.json": artifacts["timeline"],
            "glossary_fixture.json": artifacts["glossary"],
            "reader_context_fixture.json": {
                "reader_contexts": artifacts["reader_contexts"],
                "metadata": artifacts["metadata"],
            },
        }
        for name, payload in files.items():
            (output_dir / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        schema_source = Path(__file__).resolve().parents[2] / "data" / "reader_context_schema.json"
        if schema_source.exists():
            (output_dir / "reader_context_schema.json").write_text(
                schema_source.read_text(encoding="utf-8"), encoding="utf-8"
            )
        print(
            json.dumps(
                {
                    "output_dir": str(output_dir),
                    "scenes": len(scenes),
                    "occurrences": artifacts["metadata"]["occurrences"],
                    "characters": len(artifacts["character_cards"]),
                    "glossary": len(artifacts["glossary"]),
                    "reader_contexts": len(artifacts["reader_contexts"]),
                    "llm_used": False,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "semantic-pilot":
        snapshot = _snapshot_from_json(args.official_json)
        baseline = load_mtool_baseline(args.mtool)
        manifest_payload = json.loads(args.scene_manifest.read_text(encoding="utf-8"))
        scenes = manifest_payload.get("scenes") if isinstance(manifest_payload, dict) else manifest_payload
        if not isinstance(scenes, list) or not all(isinstance(scene, dict) for scene in scenes):
            parser.error("scene manifest must contain a JSON object with a scenes array")
        source_files = {str(scene["source_file"]) for scene in scenes}
        snapshot = _selected_snapshot(snapshot, source_files)
        if args.game_root:
            snapshot = enrich_snapshot(snapshot, args.game_root)
        records = build_occurrence_records(snapshot, baseline)
        index = build_context_index(snapshot, baseline)
        selected_records = [row for row in records if row["source_file"] in source_files]
        import hashlib
        input_hash = hashlib.sha256(
            json.dumps(selected_records, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if args.llm == "http":
            reader = HTTPJsonReader.from_environment()
            verifier = HTTPJsonVerifier.from_environment(
                {row["occurrence_id"]: row for row in selected_records},
                {row["occurrence_id"] for row in selected_records},
            )
        else:
            reader = FixtureReader()
            verifier = None
        pilot_result = build_semantic_pilot(
            selected_records,
            index,
            scenes,
            reader=reader,
            verifier=verifier,
            input_hash=input_hash,
        )
        status_groups = claims_by_status(pilot_result["claims"])
        pilot_result["metadata"]["validation_errors"] = validate_claims(
            pilot_result["claims"],
            {row["occurrence_id"]: row for row in selected_records},
        )
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "reading_candidates.json": pilot_result["reading_candidates"],
            "verified_claims.json": status_groups["verified"],
            "rejected_claims.json": status_groups["rejected"],
            "unresolved_claims.json": status_groups["unresolved"],
            "semantic_context.json": {"contexts": list(pilot_result["semantic_context"].values()), "metadata": pilot_result["metadata"]},
            "pilot_metadata.json": pilot_result["metadata"],
        }
        sample_records = []
        for candidate in selected_records:
            if candidate.get("speaker") and not any(row.get("speaker") for row in sample_records):
                sample_records.append(candidate)
                break
        sample_records.extend(selected_records[:3])
        prompt_sample = build_prompt_fixtures(
            sample_records[:3],
            index,
            semantic_contexts=pilot_result["semantic_context"],
        )
        outputs["prompt_sample.json"] = prompt_sample
        for name, payload in outputs.items():
            (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(pilot_result["metadata"], ensure_ascii=False))
        return 0

    official_path = args.official_json or args.source
    if official_path is None:
        parser.error("compare requires an official snapshot path or --official-json")
    official = _snapshot_from_json(official_path)
    if args.official_file:
        official.blocks = [
            block for block in official.blocks if block.metadata.get("official_file") == args.official_file
        ]
    mtool = load_mtool_baseline(args.mtool) if args.mtool else None
    report = build_report(official, mtool)
    report["mtool_alignment"] = assess_alignment(official, mtool or {})
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _snapshot_from_json(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return snapshot_from_mapping(data)


def _load_reader_context_inputs(directory: Path | None) -> dict[str, object]:
    if directory is None:
        return {}
    def load(name: str, default: object) -> object:
        path = directory / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    wrapper = load("reader_context_fixture.json", {})
    contexts = wrapper.get("reader_contexts", []) if isinstance(wrapper, dict) else []
    return {
        "reader_contexts": {
            str(item["occurrence_id"]): item
            for item in contexts
            if isinstance(item, dict) and item.get("occurrence_id")
        },
        "story_bible": load("story_bible_fixture.json", None),
        "character_cards": load("character_cards_fixture.json", []),
        "scene_summaries": load("scene_summaries_fixture.json", []),
        "timeline_events": load("timeline_fixture.json", []),
        "glossary": load("glossary_fixture.json", []),
        "semantic_contexts": _load_semantic_contexts(directory),
    }


def _load_semantic_contexts(directory: Path) -> dict[str, dict[str, object]]:
    path = directory / "semantic_context.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("contexts", []) if isinstance(payload, dict) else payload
    return {
        str(item["occurrence_id"]): item
        for item in items
        if isinstance(item, dict) and item.get("occurrence_id")
    }


if __name__ == "__main__":
    raise SystemExit(main())
