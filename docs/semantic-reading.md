# Semantic reading pilot

`semantic-pilot` reads only the occurrence records selected by
`data/scarlet_hollow_context_scenes.json`. It writes candidates first, then
runs an independent verifier. A claim carries a `candidate`, `verified`,
`rejected`, or `unresolved` status and a status transition record. Every
reference is an occurrence id from the selected scene; missing or out of
scope references are rejected.

The default `fixture` reader is deterministic and offline. It is useful for
regression tests and produces negative controls so a successful run contains
rejected and unresolved diagnostics. The optional `http` reader uses
`RENAI_LLM_ENDPOINT`, `RENAI_LLM_API_KEY`, `RENAI_LLM_MODEL`, and
`RENAI_LLM_TEMPERATURE`. Independent verification uses
`RENAI_VERIFIER_ENDPOINT`, `RENAI_VERIFIER_API_KEY`,
`RENAI_VERIFIER_MODEL`, and `RENAI_VERIFIER_TEMPERATURE`; a network call is
recorded as `llm_used: true` and is never reported as fixture output.

The checked-in pilot metadata records an offline fixture run, not an HTTP
model quality evaluation. Full `semantic_context.json` output is generated
locally and excluded from Git; bounded claims, metadata, and a prompt sample
are checked in. The command below requires the local full-game snapshot,
isolated game source, and MTool export, which are not distributed in this
repository. See the root [README](../README.md) for a clone-ready small
fixture example.

### HTTP integration contract

With `--llm http`, configure both reader and verifier endpoints. The reader
sends a JSON POST containing `scene_id` and `occurrences` and expects a claim
array or an object containing `claims`. The verifier sends `claim` and its
referenced `occurrences` and expects `decision` and `reason`; supported
decisions are `supported`, `unsupported`, `ambiguous`, and `contradictory`.
Both requests use an `Authorization: Bearer` header. Configure a service
that implements these JSON contracts. Reader and verifier model settings
are recorded as metadata; the current request bodies do not send a model
or temperature selection to the service.

`RENAI_LLM_ENDPOINT` and `RENAI_LLM_API_KEY` are required for the reader;
`RENAI_VERIFIER_ENDPOINT` is required for the verifier. The verifier API key
and model default to the reader's values when their own environment variables
are unset. Temperature defaults to `0`. Configuration is read directly from
environment variables; `.env` files are not loaded automatically. Keep keys
in your local environment rather than in fixture files.

```powershell
$env:PYTHONPATH = "src"
python -m renai_localizer_v2 semantic-pilot `
  scarlet_hollow_official/official_snapshot.json `
  --mtool scarlet_hollow_official/mtool-export.json `
  --game-root scarlet_hollow_official/game `
  --scene-manifest data/scarlet_hollow_context_scenes.json `
  --output-dir data/semantic_reading_pilot
```

Only claims with `status: verified` are eligible for semantic prompt context.
Rejected and unresolved claims remain in their diagnostic files and unresolved
questions. Timeline output is intentionally empty unless a source establishes
an explicit temporal relation.
