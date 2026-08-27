# RenAI Localizer

本地化任意 Ren'Py 游戏的 AI 工具。

> ⚠️ 项目处于早期开发阶段（Sprint 1 完成：文本提取 MVP），目前实现了「读取 `.rpy` → 提取文本 → 输出 JSON」。

## 项目文档

- [`PROJECT.md`](PROJECT.md) — 项目愿景、架构、路线图与开发原则

## 开发状态

- [x] Sprint 0：建立项目（骨架、工具链配置）
- [x] Sprint 1：文本提取 MVP（`.rpy` 读取 → 文本提取 → JSON 输出）
- [ ] Sprint 2：提取器完善（覆盖更多 `.rpy` 语法场景）

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

## 使用：提取文本

从 `.rpy` 脚本中提取待翻译文本，保存为结构化 JSON：

```bash
renai-localize extract game/script.rpy -o output.json
```

可选参数：

| 参数 | 说明 |
|------|------|
| `-o, --output` | 输出 JSON 路径；默认与输入文件同名（`.json`） |
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
  "stats": { "dialogue": 6, "menu_choice": 3 }
}
```

### 支持提取的语法（Sprint 1）

- **对白（say 语句）**：`e "Hello"`、`"Narrator"`
- **菜单选项（menu 块）**：`"Choice":`、`"Choice" if cond:`、`"Choice" (条件):`

暂不支持（后续 Sprint 支持）：多行字符串、`python`/`$` 内嵌字符串、`define`/`default` 字符串。

## 测试与代码质量

```bash
pytest                          # 运行测试
ruff check .                    # lint
ruff format --check .           # 格式检查
mypy src tests                  # 类型检查（strict）
```

> 业务功能（AI 翻译、翻译文件生成）将在后续 Sprint 中实现。
