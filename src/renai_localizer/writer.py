"""Sprint 3A：Writer —— 生成 Ren'Py 字符串翻译（tl）文件。

打通「提取 → 翻译（先直通）→ 生成 tl 文件」最小闭环中的 Writer 环节：
把 ``ExtractionResult``（或 unit 列表）写成 Ren'Py 合法的 ``strings.rpy``
（``translate <lang> strings:`` 块），只处理 ``menu_choice`` / ``string``
两类单元（对白 say / extend 走对话翻译通道，其标识符生成留待 Sprint 3B）。

与 Ren'Py 8.0.3 源码的对齐点（只读引用，不一致处以源码为准）：

- ``quote_unicode`` 精确复刻 ``renpy/translation/__init__.py`` 378–389 行：
  转义顺序固定（先 ``\\`` 再 ``\"``，随后 ``\\a \\b \\f \\n \\r \\t \\v``），
  不可调换。
- 菜单选项在注册字符串翻译前做 ``s.replace("%%", "%")``
  （``renpy/config.py:480`` 的 ``old_substitutions = True`` 使能该运行时行为，
  见 ``renpy/translation/__init__.py`` 143–144 行）；``_()`` / ``__()`` 标记的
  string 不做该替换。
- 菜单选项与标记字符串同走「字符串翻译」通道：tl 文件中的
  ``translate <lang> strings:`` 块每对 ``old`` / ``new``，运行时按 old 值匹配。

去重规则：按 old 值（menu_choice 已做 ``%%``→``%`` 之后的规范值）去重，
相同 old 只保留一条，以第一次出现的单元为准；重复条目的 new 取第一条
对应单元经 Translator 的翻译结果（直通模式下 new == old，无差别）。
输出顺序与去重后条目第一次出现的顺序一致（稳定）。
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit

# Ren'Py 8.0.3 ``renpy/translation/__init__.py`` ``quote_unicode()`` 的转义表：
# 顺序不可调换（先反斜杠、再双引号、最后控制字符）。
_QUOTE_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("\a", "\\a"),
    ("\b", "\\b"),
    ("\f", "\\f"),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
    ("\v", "\\v"),
)


def quote_unicode(s: str) -> str:
    """精确复刻 Ren'Py 8.0.3 ``quote_unicode()``（translation/__init__.py 378–389 行）。

    转义 ``\\`` → ``\\\\``、``"`` → ``\\"``、以及 ``\\a \\b \\f \\n \\r \\t \\v``，
    返回可直接放入 ``old "..."`` / ``new "..."`` 双引号内的内容。
    """
    for src, dst in _QUOTE_ESCAPES:
        s = s.replace(src, dst)
    return s


class Translator(Protocol):
    """翻译器接口：按 unit id 返回新文本。

    实现该 protocol 的翻译器（后续接 LLM）只需把 ``units`` 逐条翻译并返回
    ``{unit.id: 新文本}`` 映射；Writer 无需改动结构。未覆盖的 id 直通原文。
    """

    def translate(self, units: list[TranslationUnit]) -> dict[str, str]:
        """返回 ``{unit.id: 新文本}``；未覆盖的 id 使用原文（直通）。"""
        ...


def _iter_units(
    data: ExtractionResult | Iterable[TranslationUnit],
) -> Iterable[TranslationUnit]:
    """统一输入形态：``ExtractionResult`` 取其 ``units``，否则直接迭代。"""
    if isinstance(data, ExtractionResult):
        return data.units
    return data


def collect_string_entries(
    data: ExtractionResult | Iterable[TranslationUnit],
) -> list[tuple[str, TranslationUnit]]:
    """收集字符串翻译条目（仅 ``menu_choice`` / ``string``），按 old 值去重。

    返回 ``(old, first_unit)`` 列表：``old`` 为写入 tl 的规范旧值
    （menu_choice 先做 ``%%``→``%``），``first_unit`` 为首次出现该 old 的单元
    （重复条目的 new 以其翻译结果为准）。顺序稳定（首次出现顺序）。
    """
    ordered: OrderedDict[str, TranslationUnit] = OrderedDict()
    for unit in _iter_units(data):
        if unit.kind not in (TextKind.MENU_CHOICE, TextKind.STRING):
            continue
        if unit.kind is TextKind.MENU_CHOICE:
            old = unit.text.replace("%%", "%")
        else:
            old = unit.text
        ordered.setdefault(old, unit)
    return list(ordered.items())


def build_strings_tl(
    data: ExtractionResult | Iterable[TranslationUnit],
    language: str,
    *,
    translator: Translator | None = None,
) -> str:
    """生成 Ren'Py 合法的 ``strings.rpy`` 文本。

    输出结构（头部 + 每对 old/new 缩进 4 空格 + 条目间空行，与 Ren'Py
    生成文件一致）：:

        translate schinese strings:

            old "Eileen"
            new "Eileen"

            old "Go West"
            new "Go West"

    直通模式（未提供 ``translator``）下 ``new == old``。
    """
    entries = collect_string_entries(data)

    new_by_id: dict[str, str] = {}
    if translator is not None:
        new_by_id = translator.translate([unit for _, unit in entries])

    lines = [f"translate {language} strings:", ""]
    for old, first in entries:
        new = new_by_id.get(first.id, old)
        lines.append(f'    old "{quote_unicode(old)}"')
        lines.append(f'    new "{quote_unicode(new)}"')
        lines.append("")
    return "\n".join(lines)


def write_strings_tl(
    output_dir: Path,
    language: str,
    data: ExtractionResult | Iterable[TranslationUnit],
    *,
    translator: Translator | None = None,
) -> Path:
    """把 ``strings.rpy`` 写入 ``<output_dir>/<language>/strings.rpy`` 并返回路径。"""
    text = build_strings_tl(data, language, translator=translator)
    target = output_dir / language / "strings.rpy"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
