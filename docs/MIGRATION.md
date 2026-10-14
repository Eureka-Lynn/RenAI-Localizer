# v1 → v2 迁移说明

## 仓库与工作目录

2026-10-14 起，`Eureka-Lynn/RenAI-Localizer` 的 `master` 分支以 v2 为当前维护实现。v1 已停止使用和维护；`D:\RenAI Localizer-v2` 是当前开发目录，`D:\RenAI Localizer` 保留为本机旧版本与外部数据存档。

迁移将 v2 的独立历史与原仓库历史合并，以 v2 文件树作为主分支内容，通过普通推送更新 `master`。原 v1 最后提交为 `a35d033cc899684f7e355bd122654fd2456206da`；v2 的初始提交为 `3d2171f`。两条历史均保留，可以从旧提交查看 v1 源码和开发记录。

根目录 `README.md` 与 `PROJECT.md` 已改为当前 v2 说明；v1 的 `src/renai_localizer`、旧 CLI、工具和 Sprint 文档不再属于当前文件树。安装名、命令和模块保留 `renai-localizer-v2` / `renai_localizer_v2`，不是 v1 CLI 的兼容替换。

## 保留为参考

- 旧 extractor 仅作为历史对比证据，不在 v2 生产链路中导入或运行。
- 已核对的 Ren'Py ID 向量保留于 `data/regression_vectors.json`，用于回归参考，不作为新 parser 的实现来源。
- `tests/fixtures/sample.rpy` 与 `tests/fixtures/sprint3b.rpy` 是少量可审计 fixture；旧项目 `.cache` 没有迁入。
- `ManualTransFile.json` 作为外部只读 MTool extraction baseline，由命令显式传入，不是翻译质量标准答案。旧目录中的它及 `ManualTransFile.zh.json` 留在本地，不提交到远程，也不删除或改写。
- `official_validation/` 的小型官方输出与历史报告可分发。`scarlet_hollow_official/` 只提交摘要和运行元数据；完整游戏源码及大型提取结果由 `.gitignore` 排除。
- `data/reader_context_fixture.json` 与 `data/semantic_reading_pilot/semantic_context.json` 是可重新生成的完整 occurrence 上下文，只保存在本地。schema、受限摘要、pilot 状态结果和 prompt 样例保留在仓库。

## 当前设计边界

标准化模型以官方 `TranslationBlock` 和有序 statements 为基础，内部保留每个 occurrence。相同原文不会自动合并；只有 MTool 导出边界按 source text 折叠并记录冲突。未翻译模板的 `source == target` 正常，不能视为已翻译。

目标流程为 `官方提取 -> 故事/场景/角色/术语上下文 -> LLM 翻译 -> 审校 -> tl 生成与验证`。阶段 1/2 有历史真实语料验收，阶段 3 已有四个场景的 Reader Context fixture 和语义阅读 pilot。默认 pilot 离线运行；可选 HTTP reader / verifier 需显式配置，提交的 fixture 不表示真实模型验收。完整翻译器、生产 tl writer 和游戏内译文验证仍待实现。
