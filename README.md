# RenAI Localizer

本地化任意 Ren'Py 游戏的 AI 工具。

> ⚠️ 项目处于早期开发阶段（Sprint 0），目前仅建立项目骨架，尚无可用功能。

## 项目文档

- [`PROJECT.md`](PROJECT.md) — 项目愿景、架构、路线图与开发原则

## 开发状态

- [x] Sprint 0：建立项目（骨架、工具链配置）
- [ ] Sprint 1：MVP 端到端（提取 → 翻译 → 生成）

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

> 业务功能将在后续 Sprint 中实现。
