# RenAI Localizer

RenAI Localizer 是一个以 **Ren'Py 官方翻译提取**为基础、为翻译构建故事上下文的 Python 项目。当前维护版本为 **v2**，已接替本仓库原来的 v1；v1 不再维护，其代码和开发记录保留在 Git 历史中。

项目仍处于开发和验证阶段，尚未实现完整的游戏自动翻译流程。安装包、Python 模块和命令沿用 v2 名称：`renai-localizer-v2` / `renai_localizer_v2`。

```text
Ren'Py 官方翻译提取
    -> TranslationBlock / occurrence 标准化
    -> 故事、场景、角色、术语上下文
    -> LLM 翻译（待实现）
    -> 自动审校与 tl 生成、验证（待实现）
```

## 当前功能与边界

- **阶段 1/2：提取与对齐。** 官方 tl adapter 保留官方 identifier、结构语句顺序和每次文本出现的位置；提供只读 MTool baseline 导入、覆盖比较、context index、prompt fixture 和翻译响应约束验证。历史真实语料验收记录见 [`data/stage12_acceptance_report.json`](data/stage12_acceptance_report.json)。
- **阶段 3：受限上下文实验。** 四个 Scarlet Hollow 场景已有带来源的 Reader Context fixture。未知解释性故事事实保持为空；角色、术语和场景记录可追溯到 source refs。
- **语义阅读 pilot。** 候选 claim 经验证后分为 `verified`、`rejected`、`unresolved`；仅 `verified` 进入翻译 prompt。默认使用离线 fixture reader 和确定性 verifier，另提供需显式启用的 HTTP reader / verifier 接口。
- **验证范围。** 已有 Ren'Py 8.0.3 的小型官方输出验证，以及 Scarlet Hollow 的历史覆盖分析。当前提交的 pilot 记录为离线运行（`llm_used: false`），不代表真实 LLM 质量验收。

`OfficialStaticBackend` 需要明确的运行命令或 adapter；`RuntimeBackend` 是需要调用方提供运行时桥接的接口。当前 CLI 可以转换已生成的官方 tl 文件，不会自动发现并完成游戏解包、提取和翻译。全量翻译、生产 tl writer、向量数据库和 GUI 尚未实现。可选 HTTP 接口用于语义阅读与验证，不是翻译器；协议见 [`docs/semantic-reading.md`](docs/semantic-reading.md)。

## 安装与快速验证

需要 Python **3.11+**。核心运行时只使用 Python 标准库；构建和开发检查使用独立依赖。

```powershell
git clone https://github.com/Eureka-Lynn/RenAI-Localizer.git
cd RenAI-Localizer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

python -m renai_localizer_v2 --help
```

以下示例只使用仓库内的小型 fixture，克隆后即可运行，不需要 Scarlet Hollow 或 MTool 数据：

```powershell
# 将已生成的官方 tl 文件转换为标准化 snapshot。
python -m renai_localizer_v2 adapt-official `
  official_validation/game/tl/schinese `
  --output .cache/fixture-snapshot.json

# 检查 snapshot，MTool 输入在 compare 中是可选项。
python -m renai_localizer_v2 compare `
  .cache/fixture-snapshot.json `
  --output .cache/fixture-report.json

# 探测 PATH / Python 中的 Ren'Py；available=false 不影响上述 fixture 示例。
python -m renai_localizer_v2 probe-official --json
```

也可使用安装后的 `renai-localizer-v2` 命令。直接从源码运行而不安装时，在 PowerShell 中设置 `$env:PYTHONPATH = "src"`。

## 使用自己的数据

先使用与你的游戏兼容的 Ren'Py 运行时，在隔离项目副本中生成 `game/tl/<language>/`，再用 `adapt-official` 转换输出。历史验证过程见 [`docs/official-extraction-validation.md`](docs/official-extraction-validation.md)；其中的运行时路径是验证记录，需替换为自己的路径。

`ManualTransFile.json` 是调用方提供的外部 **MTool extraction baseline**，不随仓库分发，也不被改写。`source == target` 是未翻译模板的正常状态；重复文本保留 occurrence 记录和匹配歧义。

```powershell
python -m renai_localizer_v2 coverage `
  path/to/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root path/to/isolated/game `
  --output .cache/coverage-report.json `
  --occurrences-output .cache/occurrences.jsonl `
  --mtool-output .cache/mtool-export.json

python -m renai_localizer_v2 context-index `
  path/to/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root path/to/isolated/game `
  --output .cache/context-index.json

python -m renai_localizer_v2 prompt-fixtures `
  path/to/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --sample-count 3 --output .cache/prompt-fixtures.json
```

Prompt 响应要求 `occurrence_id`、`translation`、`notes` 三个 JSON 字段。`validate-response` 检查 JSON 结构、占位符、Ren'Py 标签、百分号、反斜杠、换行和语句数量；具体参数可用 `python -m renai_localizer_v2 validate-response --help` 查看。

## 重建受限上下文实验

以下命令需要本地保留的完整 Scarlet Hollow snapshot、隔离源码和 MTool 数据，**这些大文件不包含在 Git 仓库中**。`data/scarlet_hollow_context_scenes.json` 仅适用于该历史实验的四个场景；其他游戏需要自己的场景清单。

```powershell
python -m renai_localizer_v2 reader-fixtures `
  scarlet_hollow_official/official_snapshot.json `
  --mtool path/to/ManualTransFile.json `
  --game-root scarlet_hollow_official/game `
  --scene-manifest data/scarlet_hollow_context_scenes.json `
  --run-metadata scarlet_hollow_official/run-metadata.json `
  --output-dir .cache/reader-context

python -m renai_localizer_v2 semantic-pilot `
  scarlet_hollow_official/official_snapshot.json `
  --mtool scarlet_hollow_official/mtool-export.json `
  --game-root scarlet_hollow_official/game `
  --scene-manifest data/scarlet_hollow_context_scenes.json `
  --output-dir .cache/semantic-pilot
```

pilot 不执行翻译或生成 tl 文件。要调用真实 reader / verifier，需显式指定 `--llm http` 并配置环境变量，详见[语义阅读说明](docs/semantic-reading.md)。

## 文件与验证

- [`PROJECT.md`](PROJECT.md)：当前架构、阶段边界和后续目标。
- [`docs/MIGRATION.md`](docs/MIGRATION.md)：v1 退役、历史保留和数据迁移说明。
- [`official_validation/validation-report.md`](official_validation/validation-report.md)：可分发小型 fixture 的官方提取验证。
- [`scarlet_hollow_official/coverage-analysis.md`](scarlet_hollow_official/coverage-analysis.md)：完整游戏的历史覆盖分析；原始大文件仅保存在本地。
- [`data/fixtures-manifest.json`](data/fixtures-manifest.json)：fixture 清单；完整 occurrence context 为可再生成的本地产物。

```powershell
python -m pytest -q
ruff check src tests
python -m compileall -q src
```

仓库提交源码、测试、小型 fixture、schema 和验证摘要；游戏源码、大型提取结果、缓存、密钥和完整生成上下文由 `.gitignore` 排除。
