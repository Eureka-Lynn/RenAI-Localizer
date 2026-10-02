# 迁移说明

## 保留为参考

- 旧项目 extractor 只保留在历史 evidence 文件中，不属于 v2 生产链路。
- 旧项目 `dialogue.py` 中已经核对过的 Ren'Py ID 向量被复制到 `data/regression_vectors.json`，作为回归数据，不作为新 parser 的实现来源。
- `tests/fixtures/sample.rpy` 和 `tests/fixtures/sprint3b.rpy` 是少量、可审计的 fixture。旧项目 `.cache` 没有复制。
- `ManualTransFile.json` 作为外部 **MTool extraction baseline** 输入，由调用方显式传入；它是 Scarlet Hollow 的文本覆盖和 MTool 兼容基线，不是翻译质量 baseline。v2 只读导入，不改写它；`source == target` 不报错。

## 不再作为生产设计

- 旧 extractor 的正则扫描和单条 `TranslationUnit` 不再是 v2 的核心模型，也不再由 v2 import。
- 相同原文不会被自动合并；比较和翻译都保留每个 source/line occurrence。
- 只有在输出 MTool `source_text -> translation` 格式时才合并重复 key，并记录冲突数量；内部使用 occurrence 记录。
- MTool 值只用于三方比较，不被视为绝对正确答案。
- 旧 writer、全量 LLM 流程、向量数据库和复杂 tl 验证不在本阶段实现。

## v2 目标边界

生产链路目标是 `Ren'Py 官方翻译提取 -> 标准化 TranslationBlock -> 故事/场景/角色/术语上下文 -> LLM 翻译 -> 自动审校 -> tl 生成和验证`。阶段 1/2 已在真实 Scarlet Hollow 源码上用 Ren'Py 8.0.3 转换 68,342 个官方 block，并完成 occurrence 级 MTool 覆盖；阶段 3 只为四个受限真实场景建立来源可追踪的 Reader Context fixture，未接入 LLM、全量翻译、向量数据库或生产 tl writer。
