# 官方提取可行性验证

验证日期：2026-10-01（Asia/Singapore）。

## 实际探测

在本机执行了以下探测：

```text
where renpy
where renpy.exe
where renpy.sh
python -c "import renpy"
```

初始 PATH/Python 探测没有找到全局 launcher 或 `renpy` 模块，但进一步扫描发现可用的 Ren'Py 游戏运行时：

- `F:\SteamLibrary\steamapps\common\ScarletHollow\ScarletHollow.exe`
- `F:\SteamLibrary\steamapps\common\ScarletHollow\renpy`
- 日志版本：`Ren'Py 8.0.3.22090809`

读取该版本源码后确认真实命令为 `basedir translate language`，并确认了 `--no-todo` 参数。v2 随后对独立 fixture 实际执行了该命令，并进一步对 Scarlet Hollow 的 199 个隔离 `.rpy` 源文件实际执行，生成 185 个 `game/tl/schinese/` 文件。完整证据、命令、日志、覆盖比较和差异结果见 `official_validation/validation-report.md` 与 `../scarlet_hollow_official/coverage-analysis.md`。

## Scarlet Hollow 实跑结果

`scarlet_hollow_official/official_snapshot.json` 由 v2 adapter 从真实官方
输出生成，包含 68,342 个官方 translation block 和 76,435 个非空文本
occurrence；另保留 2,259 个空结构语句的 block 顺序。官方 identifier 直接来自 `translate schinese <id>:`，没有用
source/line/ordinal 重算。运行版本、命令、输出目录和退出码保存在
`scarlet_hollow_official/run-metadata.json`，运行日志保存在同目录。

MTool 对齐结果保存在 `scarlet_hollow_official/coverage-report.json`，其中
`ManualTransFile.json` 被命名为 MTool extraction baseline；当前
`source == target` 是未翻译模板的正常状态。occurrence 级记录在
`occurrences.jsonl`，官方与 legacy 的同源比较在
`official-vs-legacy-full.json`。

## 设计约束

`OfficialStaticBackend` 仍接受调用方明确传入的 command 或 adapter。实际官方输出由 `official_adapter.py` 解析为 v2 `ExtractionSnapshot`；adapter 保留官方 identifier，不用 source/line/ordinal 重新生成 ID。
