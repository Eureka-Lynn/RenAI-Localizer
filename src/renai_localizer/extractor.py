"""Ren'Py ``.rpy`` 脚本文本提取器。

Sprint 1 支持的场景：

- 对白（say 语句）：``e "Hello"`` / ``"Narrator"``
- 菜单选项（menu 块）：``"Choice":`` / ``"Choice" if cond:``

暂不支持的复杂语法（见 PROJECT.md MVP 范围）：

- 多行字符串
- ``python`` / ``$`` 内嵌表达式中的字符串
- ``define`` / ``default`` 中的字符串
"""

from __future__ import annotations

import re
from pathlib import Path

from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit

_DIALOGUE_RE = re.compile(
    r'^\s*(?:(?P<speaker>[A-Za-z_]\w*)\s+)?(?P<text>"(?:\\.|[^"\\])*")'
    r"(?:\s*\([^)]*\))?\s*(?:#.*)?$"
)

_MENU_CHOICE_RE = re.compile(
    r'^\s*(?P<text>"(?:\\.|[^"\\])*")'
    r"(?:\s*(?:\([^)]*\)|\bif\b.*))?\s*:\s*(?:#.*)?$"
)

_MENU_START_RE = re.compile(r"^\s*menu\s*:\s*(?:#.*)?$")
_LABEL_RE = re.compile(r"^\s*label\s+(?P<name>[\w.]+)\s*:")

_UNESCAPE_RE = re.compile(r'\\(["\\\[\]])')


def _indent(line: str) -> int:
    """返回行首缩进字符数（空格与制表符各计 1）。"""
    return len(line) - len(line.lstrip(" \t"))


def _unquote(raw: str) -> str:
    """去掉字符串两端的引号并还原转义序列。

    处理 Ren'Py 中的 ``\\"``、``\\\\``、``\\[``、``\\]`` 转义。
    """
    return _UNESCAPE_RE.sub(r"\1", raw[1:-1])


class RpyExtractor:
    """从 Ren'Py 脚本文本中提取待翻译文本。"""

    def extract(self, text: str, *, source: str = "<memory>") -> ExtractionResult:
        """从脚本内容中提取文本单元。"""
        units: list[TranslationUnit] = []
        counters: dict[str, int] = {}

        current_label: str | None = None
        menu_indents: list[int] = []

        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.rstrip("\r")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = _indent(line)

            # 缩进回退到 menu 层级或以上时，退出已结束的 menu 块。
            while menu_indents and indent <= menu_indents[-1]:
                menu_indents.pop()

            label_match = _LABEL_RE.match(line)
            if label_match:
                current_label = label_match.group("name")
                continue

            if _MENU_START_RE.match(line):
                menu_indents.append(indent)
                continue

            if menu_indents:
                choice_match = _MENU_CHOICE_RE.match(line)
                if choice_match:
                    units.append(
                        self._make_unit(
                            counters,
                            kind=TextKind.MENU_CHOICE,
                            text=_unquote(choice_match.group("text")),
                            line=line_no,
                            source=source,
                            speaker=None,
                            context=current_label,
                        )
                    )
                    continue

            dialogue_match = _DIALOGUE_RE.match(line)
            if dialogue_match:
                units.append(
                    self._make_unit(
                        counters,
                        kind=TextKind.DIALOGUE,
                        text=_unquote(dialogue_match.group("text")),
                        line=line_no,
                        source=source,
                        speaker=dialogue_match.group("speaker"),
                        context=current_label,
                    )
                )

        return ExtractionResult(source=source, units=units)

    def extract_file(self, path: str | Path, *, encoding: str = "utf-8") -> ExtractionResult:
        """读取 ``.rpy`` 文件并提取文本单元。"""
        file_path = Path(path)
        text = file_path.read_text(encoding=encoding)
        return self.extract(text, source=str(file_path))

    @staticmethod
    def _make_unit(
        counters: dict[str, int],
        *,
        kind: TextKind,
        text: str,
        line: int,
        source: str,
        speaker: str | None,
        context: str | None,
    ) -> TranslationUnit:
        seq = counters.get(kind.value, 0) + 1
        counters[kind.value] = seq
        return TranslationUnit(
            id=f"{kind.value}-{seq:03d}",
            kind=kind,
            text=text,
            line=line,
            source=source,
            speaker=speaker,
            context=context,
        )
