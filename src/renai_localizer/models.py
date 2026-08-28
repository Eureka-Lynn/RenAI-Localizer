"""Sprint 1：文本提取阶段的数据模型。

这些模型是「Extractor → Translator → Writer → Verifier」管道中各阶段之间
传递的结构化数据。Sprint 1 只实现 Extractor，但模型设计保持通用，
便于后续 Sprint 加入翻译与回写功能。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TextKind(StrEnum):
    """待翻译文本的种类。

    - ``dialogue``：say 语句对白（含 ``centered`` / ``nvl`` 变体）
    - ``menu_choice``：menu 块中的选项文本
    - ``string``：被 ``_()`` / ``__()`` 标记的可翻译字符串（Sprint 2 新增，
      常见于 ``define`` / ``default`` 中的角色名与界面文本）
    """

    DIALOGUE = "dialogue"
    MENU_CHOICE = "menu_choice"
    STRING = "string"


class TranslationUnit(BaseModel):
    """一条待翻译的文本单元。

    对应 Ren'Py 脚本中的一句对白或一个菜单选项。
    """

    id: str
    """唯一标识符，例如 ``dialogue-001``。"""

    kind: TextKind
    """文本种类（对白 / 菜单选项 / 标记字符串）。"""

    text: str
    """待翻译的原文，保留 Ren'Py 插值占位符（如 ``[name]``）。"""

    line: int
    """原文在源文件中的行号（从 1 开始）。"""

    source: str
    """来源文件路径。"""

    speaker: str | None = None
    """说话者标识符；叙述文本为 ``None``。"""

    context: str | None = None
    """上下文，例如所在的 ``label`` 名称。"""


class ExtractionResult(BaseModel):
    """一次文本提取的完整结果。"""

    schema_version: int = 1
    # Sprint 2 新增 TextKind.STRING 时保持 schema_version = 1：
    # JSON 结构与字段含义均未变化，仅 units 中可能出现新的 kind 值
    # （"string"），对既有消费者向后兼容，因此无需升级 schema。
    source: str
    units: list[TranslationUnit] = Field(default_factory=list)

    def stats(self) -> dict[str, int]:
        """按文本种类统计单元数量。"""
        counts: dict[str, int] = {}
        for unit in self.units:
            counts[unit.kind.value] = counts.get(unit.kind.value, 0) + 1
        return counts
