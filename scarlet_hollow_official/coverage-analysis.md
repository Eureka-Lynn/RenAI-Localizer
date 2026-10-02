# Scarlet Hollow Coverage Analysis

This report compares the real Ren'Py output in `official_snapshot.json` with
the read-only `D:\RenAI Localizer\ManualTransFile.json` MTool extraction
baseline. The MTool values are untouched template values: all 179,884 entries
currently have `source_text == translation`, which is expected for an
untranslated extraction and is not counted as an error.

## Coverage

| Measure | Count |
| --- | ---: |
| MTool keys | 179,884 |
| Official unique source texts | 55,651 |
| Official text occurrences | 76,435 |
| Exact key intersection | 30,445 |
| MTool keys only | 149,439 |
| Official texts only | 25,206 |
| Official duplicate source texts | 10,538 |
| Duplicate occurrences beyond first | 20,784 |
| Normalization-only pairs | 103 |

The difference is a coverage and representation difference, not evidence that
either input is correct or incorrect. MTool has no source file, line, official
identifier, or occurrence index. Its keys also contain many formatting and
fragment variants: 67,662 keys end in a quote character and 368 start with
`!`. These patterns are investigation signals, not automatic error labels.
Official output also includes Ren'Py common strings and generated string
blocks, while MTool's extraction scope is not recoverable from its text-only
map.

The 103 normalization pairs include trailing newlines and punctuation choices
such as `...` versus `…`. They are reported separately from exact matches.

## Occurrence records and export

`occurrences.jsonl` keeps one record per official occurrence with
`occurrence_id`, source file and line, official identifier, label, speaker,
source text, MTool value, and a reserved `our_translation` field. Repeated
source text is never merged in this internal representation.

`mtool-alignment.json` records the text-only limitations explicitly: exact
lookup finds 43,869 of the 76,435 official text occurrences, but source, line, and
occurrence indexes are unavailable. Repeated text therefore needs an external
index before it can be aligned deterministically.

`mtool-export.json` is the boundary format. It collapses repeated source keys
only for MTool compatibility and reports `collision_count` and the conflicting
values. A source equal to its MTool value is preserved as a normal untranslated
template entry.

## Official versus legacy

The full report is `official-vs-legacy-full.json`. It runs the preserved legacy
extractor against the same 199 copied Scarlet Hollow source files:

| Result | Count | Interpretation |
| --- | ---: | --- |
| Exact text match | 66,555 | Both backends found the same occurrence text. |
| Text match, location differs | 9,595 | Mostly menu text reported at the Ren'Py Menu node line by official extraction and at the quoted option line by legacy extraction. |
| Legacy missing | 285 | Official found nonempty text that the legacy parser did not, including generated/common strings and marked or command-adjacent forms. Empty structural continuations remain in official blocks but are excluded from text alignment. |
| Official missing | 4,242 | Legacy found text that official generation omitted from translation blocks, often screen/UI literals outside the official translatable set. |
| Legacy under-grouped | 7 | Official `strings` blocks contain multiple ordered statements while legacy emits one unit. |

The rows distinguish extraction scope, location semantics, and grouping. They
do not treat the official output as a text-only quality oracle.

## Files

- `official_snapshot.json`: adapter output with official identifiers and ordered statements.
- `coverage-report.json`: set coverage, duplicate, and normalization summary.
- `occurrences.jsonl`: occurrence-level alignment records.
- `mtool-alignment.json`: text-only alignment limits and required extra index.
- `mtool-export.json`: optional MTool-shaped export plus collision report.
- `official-vs-legacy-full.json`: same-source official/legacy comparison.
- `log.txt`, `official-command.log`, `renpy-command.txt`, `renpy-version.txt`: runtime evidence.

The runtime log contains a nonfatal Steam initialization warning from the
headless extraction environment. The process exited with code `0`, loaded the
scripts, initialized translation, and wrote the official files.
