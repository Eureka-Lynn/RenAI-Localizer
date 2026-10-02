# RenAI Localizer v2

RenAI Localizer v2 是一个**官方提取优先**的 Ren'Py 故事上下文翻译项目。它重构旧项目的边界，不把旧正则 extractor 继续堆叠成最终 parser。

目标管道：

```text
Ren'Py 官方翻译提取
    -> 标准化 TranslationBlock
    -> 故事、场景、角色、术语上下文
    -> LLM 翻译
    -> 自动审校
    -> 生成和验证 tl 文件
```

## 当前阶段

阶段 1/2 已通过契约验收，阶段 3 Reader Context Layer 已完成受限 fixture 实验：

- `ExtractionBackend` 契约和两个生产 backend：`OfficialStaticBackend`、`RuntimeBackend`。
- `TranslationBlock` 可包含多个有序 Ren'Py statements，并保留每次出现的位置。
- `OccurrenceRecord` 保留每个 source/line occurrence；`source == target` 是未翻译模板的正常状态。
- 未翻译 occurrence 的 `translated_text` 和 `raw_translated_code` 均为 `null`；MTool 文本命中只记录为 text candidate，重复文本保留 ambiguity diagnostics。
- `ManualTransFile.json` 的只读 **MTool extraction baseline** importer；baseline 通过 `--mtool` 显式传入。
- official / MTool 比较报告、确定性 context index、single/context-aware prompt fixture 和约束验证。
- Stage 3 Reader Context Layer 只对 `data/scarlet_hollow_context_scenes.json` 中的四个真实场景生成有来源的 fixture；未知故事事实保持空值，不调用 LLM。
- 少量旧 fixture 和 Ren'Py ID 回归向量。
- Ren'Py 8.0.3 在真实 Scarlet Hollow 源码上的官方提取、tl 输出 adapter、MTool 覆盖比较和 official vs legacy 报告，见 [`scarlet_hollow_official/coverage-analysis.md`](scarlet_hollow_official/coverage-analysis.md)。最小 fixture 的验证证据仍在 [`official_validation/validation-report.md`](official_validation/validation-report.md)。

当前不做全量翻译、真实 LLM 调用、向量数据库或生产 tl writer。

## 运行

无需第三方依赖即可运行：

```powershell
python -m renai_localizer_v2 probe-official --json
python -m renai_localizer_v2 compare scarlet_hollow_official/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --output compare.json

python -m renai_localizer_v2 coverage `
  scarlet_hollow_official/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root scarlet_hollow_official/game `
  --output scarlet_hollow_official/coverage-report.json `
  --occurrences-output scarlet_hollow_official/occurrences.jsonl `
  --mtool-output scarlet_hollow_official/mtool-export.json
```

如果从源码目录运行，请设置 `PYTHONPATH=src`，或先执行 `pip install -e .`。v2 不导入旧项目代码，也没有旧项目默认路径；`compare` 和 `coverage` 只读取显式提供的官方 snapshot、隔离的 Scarlet Hollow 源码和 MTool extraction baseline。

## 阶段 1/2 产物

```powershell
python -m renai_localizer_v2 context-index `
  scarlet_hollow_official/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root scarlet_hollow_official/game `
  --output context-index.json

python -m renai_localizer_v2 prompt-fixtures `
  scarlet_hollow_official/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root scarlet_hollow_official/game `
  --sample-count 3 --output prompt-fixtures.json
```

Prompt fixture 明确要求模型只返回 `occurrence_id`、`translation`、`notes` 三个 JSON 字段。`ManualTransFile.json` 仅作为只读 source-text baseline；重复文本在内部保持 occurrence 级记录。

`validate-response` 命令和 `validate_translation_response` API 会自动检查 JSON shape、占位符、Ren'Py 文本标签、百分号、反斜杠、换行和 statement 数量。

Reader Context fixture 可重复生成：

```powershell
python -m renai_localizer_v2 reader-fixtures `
  scarlet_hollow_official/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root scarlet_hollow_official/game `
  --scene-manifest data/scarlet_hollow_context_scenes.json `
  --run-metadata scarlet_hollow_official/run-metadata.json `
  --output-dir data
```

输出的 `story_bible_fixture.json`、`character_cards_fixture.json`、`scene_summaries_fixture.json`、`timeline_fixture.json`、`glossary_fixture.json` 和 `reader_context_fixture.json` 均保留 `source_refs`；当前没有已确认的全局故事事实或时间线事件。

## 数据和迁移边界

fixture 清单在 `data/fixtures-manifest.json`。没有复制旧项目 `.cache`，没有删除或改写旧项目的 `ManualTransFile.json`。迁移决策详见 [`docs/MIGRATION.md`](docs/MIGRATION.md)。
