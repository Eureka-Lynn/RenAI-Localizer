# RenAI Localizer

本地化任意 Ren'Py 游戏的 AI 工具。

> ⚠️ 项目处于早期开发阶段（Sprint 3.5 完成：文本值保真修复 —— 转义与空白折叠语义与 Ren'Py 8.0.3 源码对齐），目前实现了「解包 `.rpa` → 读取 `.rpy` → 提取文本 → 输出 JSON」。

## 项目文档

- [`PROJECT.md`](PROJECT.md) — 项目愿景、架构、路线图与开发原则

## 开发状态

- [x] Sprint 0：建立项目（骨架、工具链配置）
- [x] Sprint 1：文本提取 MVP（`.rpy` 读取 → 文本提取 → JSON 输出）
- [x] Sprint 2：提取器完善（覆盖更多 `.rpy` 语法场景）
- [x] Sprint 3：unrpa 选择性解包 + 提取器收尾修复 + 真实语料冒烟测试
- [x] Sprint 3.5：文本值保真修复（转义与空白折叠语义对齐 Ren'Py）

## 快速开始（开发环境）

本项目使用 **Anaconda** 管理 Python 环境，并为项目创建了独立的 conda 虚拟环境。

### 创建并激活环境

```bash
# 创建独立虚拟环境（Python 3.11）
conda create -n renai-localizer python=3.11 -y

# 激活环境
conda activate renai-localizer
```

### 安装项目（含开发依赖）

```bash
pip install -e ".[dev]"
```

## 使用：unrpa 薄封装解包

游戏内容通常封装在 `.rpa` 归档中（全量解包可能达数 GB），`tools/unpack_rpa.py`
复用 unrpa 库 API 做**选择性解包**：只解析归档头 / 索引（`UnRPA.get_index`），
仅解压匹配后缀的条目（默认 `.rpy`），不抽取图片、音频、`.rpyc` 等其它资源：

```bash
# 只抽取所有 .rpy（约 19MB），保持归档内相对目录结构写入输出目录
python tools/unpack_rpa.py "F:\SteamLibrary\...\game\archive.rpa" .cache/<game>/rpy/

# 只列出归档内容（按扩展名分组统计），不抽取任何文件
python tools/unpack_rpa.py "F:\SteamLibrary\...\game\archive.rpa" --list

# 同时抽取 .rpy 与 .rpyc
python tools/unpack_rpa.py archive.rpa out/ --suffix .rpy --suffix .rpyc
```

| 参数 | 说明 |
|------|------|
| `--list` | 只列出归档条目（按扩展名统计），不抽取 |
| `--suffix` | 要抽取的后缀，可重复指定；默认 `.rpy` |

> 解包输出写入项目本地 `.cache/`（已加入 `.gitignore`，不提交）；游戏目录保持只读，
> 绝不写入。

## 使用：提取文本

从 `.rpy` 脚本**或目录**中提取待翻译文本，保存为结构化 JSON：

```bash
# 单个脚本文件（文件模式）
renai-localize extract game/script.rpy -o output.json

# 目录模式：递归处理其中所有 .rpy，合并输出为一个 JSON，
# 每个单元的 source 为相对目录的路径（如 "scripts/day1.rpy"）
renai-localize extract .cache/scarlet_hollow/rpy -o extracted.json -v
```

可选参数：

| 参数 | 说明 |
|------|------|
| `-o, --output` | 输出 JSON 路径；默认与输入文件（或目录）同名（`.json`） |
| `--encoding` | 读取脚本编码，默认 `utf-8` |
| `-v, --verbose` | 输出提取统计（按文本种类计数） |

### 输出格式

```json
{
  "schema_version": 1,
  "source": "game/script.rpy",
  "units": [
    {
      "id": "dialogue-001",
      "kind": "dialogue",
      "text": "It's great to see you again, [player_name].",
      "line": 11,
      "source": "game/script.rpy",
      "speaker": "e",
      "context": "start"
    }
  ],
  "stats": { "dialogue": 6, "menu_choice": 3, "string": 1 }
}
```

### 支持提取的语法（Sprint 3）

- **对白（say 语句）**：`e "Hello"`、`"Narrator"`、单引号 `e 'Hi'`
- **say 变体**：`centered "..."`、`nvl "..."`、`nvl centered "..."`（均视为叙述，speaker 为 `None`）
- **say 的 `id` 子句**：`e "text" id start_xxx:` —— 文本照常提取，id 内容不进入文本
- **对白续写 `extend`**：`extend "..."` 提取为 dialogue（speaker 为 `None`）；
  尾部 `id` / `with` / 注释与普通 say 一致处理；**空文本 `extend ""` 不产出单元**
- **多行字符串**：三引号 `"""..."""` / `'''...'''` 可跨行，`line` 记录起始行
- **单引号字符串**：与双引号同等处理，支持 `\'` 转义
- **菜单选项（menu 块）**：`"Choice":`、`"Choice" if cond:`、`"Choice" (条件):`、单引号变体
- **可翻译字符串标记**：`_("...")` / `__("...")`，提取为 `kind="string"`
  （常见于 `define` / `default` 中的角色显示名、界面文本）
- **文本值保真（Sprint 3.5）**：`text` 等于 Ren'Py 运行时（lexed / Python
  求值后）的规范文本值 —— say / 菜单选项按 `Lexer.string()` 语义
  （连续空白折叠 + `\n`→换行、`\{`→`{{`、`\[`→`[[`、`\%`→`%%`、`\uXXXX`、
  其它 `\x`→`x`）；say 三引号去掉换行两侧水平空白；`_()` / `__()` 按 Python
  字符串转义还原。保证后续翻译标识符（MD5）与游戏内一致。
- **空文本过滤**：提取结果中空串 / 纯空白的单元一律丢弃（兜底，覆盖 `""`、`_("")` 等）
- **目录模式**：`renai-localize extract <目录>` 递归处理所有 `.rpy`，合并输出为一个 JSON，
  每个单元保留相对 `source` 路径与文件内 `line`

### 已知限制（暂不支持）

- `python` 块 / `$` 语句内的字符串（含 `_()` 标记）
- `define` / `default` 中的裸字符串（未用 `_()` / `__()` 标记，Ren'Py 不会将其加入可翻译字符串）
- `_p()` / `___()` 标记的字符串
- 屏幕语言（`screen`）中的属性字符串（如 `style_group ""`、`scrollbars "vertical"`、
  `thumb "gui/...png"`）—— 屏幕内只提取 `_()` / `__()` 标记的字符串
- 资源引用语句 `shader` / `font` / `voice` 已跳过（Sprint 3 修复，不再误提取）
- raw 字符串（`r"..."`）与三引号对白中的 monologue 分段（语料中无此场景，
  继续列入已知限制）
- 字符串拼接求值、翻译标识符（`id`）生成、文本去重

## 测试与代码质量

```bash
pytest                          # 运行测试
ruff check .                    # lint
ruff format --check .           # 格式检查
mypy src tests                  # 类型检查（strict）
```

> 业务功能（AI 翻译、翻译文件生成）将在后续 Sprint 中实现。
