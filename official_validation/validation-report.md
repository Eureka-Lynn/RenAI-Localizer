# Official Ren'Py Extraction Validation

## Runtime

- Ren'Py version: `8.0.3.22090809`
- Executable: `F:\SteamLibrary\steamapps\common\ScarletHollow\ScarletHollow.exe`
- Runtime source: `F:\SteamLibrary\steamapps\common\ScarletHollow\renpy`
- Command: see `renpy-command.txt`
- Runtime log: `log.txt`
- Launcher stdout/stderr captures: `renpy-version.log`, `translate-run.log`

The command exited with status `0` and generated real files under
`game/tl/schinese/`, including `script.rpy` and `common.rpy`.

## Official output evidence

`game/tl/schinese/script.rpy` contains official identifiers such as:

```text
translate schinese start_c209ba5a:
translate schinese start_3013da9a:
translate schinese explicit_validation_id:
```

`start_3013da9a` contains two ordered statements:

```text
# nvl clear
# n "This is an NVL-style narrator line."
nvl clear
n "This is an NVL-style narrator line."
```

`official_snapshot.json` is produced by the v2 adapter from these files. The
adapter preserves the official identifier, header source location, original
comment code, translated statement text, raw statement code, and statement
order. It never computes an official ID from source/line/ordinal.

## Official vs legacy

`official-vs-legacy.json` runs `LegacyStaticBackend` on the same
`official_validation/game/script.rpy` fixture.

Observed differences:

- `voice "audio/voice.ogg"`: present in the official translation block, absent from legacy extraction.
- `start_3013da9a`: official has two statements; legacy retains one text statement and loses the `nvl clear` structure.
- Menu labels: official source line is the `Menu` node line (`12`); legacy reports the quoted option line (`13`). These are text matches with a source-location difference.
- `$ marked_one = _()` and `$ marked_two = __()`: present in the official strings block, absent from legacy extraction.
- Repeated `Repeated dialogue.` occurrences remain separate in both outputs.

## MTool alignment

The imported `ManualTransFile.json` is a `text -> text` map with no source file,
line, or occurrence index. The report therefore records:

- text lookup is possible only when the exact source text is present;
- repeated text such as `Repeated dialogue.` is ambiguous;
- source and line agreement cannot be proven;
- a stable alignment requires at least `source`, `line`, and per-source
  `occurrence` (or the official Ren'Py identifier for dialogue blocks).

`ManualTransFile.json` remains an external read-only MTool extraction baseline
and is not treated as authoritative extraction or translation truth. Equal
source and target values are expected for this untranslated template.
