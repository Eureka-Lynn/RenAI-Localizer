# RenAI Localizer 项目说明

当前维护版本为 v2，已接替原 v1。项目目标是基于 Ren'Py 官方提取和可追溯故事上下文，逐步完成可靠的本地化流程；当前成果是提取、对齐、上下文与语义阅读验证工具，尚不是完整自动汉化产品。

## 架构与数据契约

```text
官方 tl 文件 -> official_adapter -> ExtractionSnapshot
    -> TranslationBlock / TranslationStatement
    -> OccurrenceRecord -> 覆盖分析 / context index
    -> Reader Context / semantic claims -> 翻译 prompt
    -> LLM 翻译 -> 自动审校 -> tl writer / 游戏验证（后续）
```

- `backends.py`：`ExtractionBackend` 契约。`OfficialStaticBackend` 接受显式命令或 adapter；`RuntimeBackend` 预留调用方注入的运行时桥接，不是现成的游戏扫描器。
- `official_adapter.py` / `models.py`：转换官方输出，保留官方 identifier、源位置和有序结构语句，不重新计算官方 ID。
- `baseline.py` / `compare.py` / `coverage.py`：只读 MTool baseline、覆盖比较和 occurrence 记录；重复原文不在内部合并，只在 MTool 导出边界折叠并报告冲突。
- `context.py` / `reader_context.py`：同一源文件内的局部上下文、角色、场景和术语候选；解释性信息需要来源，未知事实保持未知。
- `semantic_reading.py`：离线或可选 HTTP reader 生成候选，独立 verifier 决定状态，保留引用和状态变更。只有 verified claim 可以进入 prompt。
- `prompts.py` / `validation.py`：构造单条及上下文 prompt，验证响应结构和 Ren'Py 文本约束；不调用翻译模型或写出生产翻译文件。

未翻译 occurrence 的 `translated_text` 与 `raw_translated_code` 为 `null`。MTool 按文本命中只能证明候选关系，不能代替 source/line/occurrence 对齐。故事阅读的验证与译文审校是不同步骤。

## 已完成的验证范围

阶段 1/2 的历史 Scarlet Hollow 验收包含 68,342 个官方 block、76,435 个非空文本 occurrence；详细记录见 [阶段 1/2 报告](data/stage12_acceptance_report.json)和[覆盖分析](scarlet_hollow_official/coverage-analysis.md)。

阶段 3 保留四个场景的来源可追溯 fixture，并加入语义阅读 pilot。提交的 pilot 是离线 fixture reader 结果：160 个候选中 152 个 verified、4 个 rejected、4 个 unresolved；这是受限回归证据，不是模型翻译质量指标，也不代表全局故事理解已完成。

小型 `official_validation/` fixture 可在克隆后转换与检查。完整游戏源码、snapshot 和 occurrence 级上下文仅存于本地；重建真实语料实验需要用户自己的数据和兼容的 Ren'Py 运行时。

## 后续目标

1. 验证真实 HTTP reader / verifier 的协议适配、来源约束和错误处理。
2. 在受限场景接入实际翻译器，比较单条与上下文翻译，保留占位符和结构语句。
3. 实现生产 tl writer、译文审校与 Ren'Py 运行验证，再考虑批量、缓存及增量翻译。

以上为方向性目标，未标记为已实现。当前没有向量数据库、GUI 或完整游戏自动翻译命令。

## 开发与分发

Python 3.11+；核心运行时依赖标准库，CLI 使用 `argparse`，开发检查使用 pytest 和 Ruff。安装、可运行示例与检查命令见 [README](README.md)。模块和包名继续使用 `renai_localizer_v2` / `renai-localizer-v2`。

v1 的正则 extractor、旧 writer、旧 CLI `renai-localize` 和 Sprint 路线图已退役；历史提交仍可查阅，迁移策略见 [MIGRATION](docs/MIGRATION.md)。
