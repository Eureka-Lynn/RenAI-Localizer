"""Sprint 3.5：文本值保真的回归测试。

覆盖：
- say 的 ``\\n`` 结尾 → 真换行（与 ``Lexer.string()`` dequote 语义一致）
- say 的 ``\\[`` / ``\\{`` / ``\\%`` / ``\\uXXXX`` 与未知转义 ``\\t`` 各自还原
- 菜单选项连续空格折叠为单空格
- ``_()`` / ``__()`` 按 Python 字符串转义规则还原（``\\n`` → 换行、``\\t`` → 制表符）
"""

from __future__ import annotations

from pathlib import Path

from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind

FIXTURE = Path(__file__).parent / "fixtures" / "sprint35.rpy"


def _extract() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def test_say_newline_ending() -> None:
    # 以 \n 结尾的 say 应还原为真换行（对应 flashback.rpy 真实语料形态）。
    result = _extract()
    dialogue = next(
        u
        for u in result.units
        if u.kind == TextKind.DIALOGUE and u.text.startswith("It's cold, and dark")
    )
    assert dialogue.text.endswith("somewhere.\n")
    assert dialogue.text.count("\n") == 1
    assert "\\n" not in dialogue.text


def test_say_literal_brackets_and_braces() -> None:
    # \[ → [[（字面量方括号，避免被当作插值起始）；
    # \{ → {{（字面量花括号，避免被当作文本标签起始）；
    # \] → ]、\} → }（Ren'Py 只对上述起始符加倍，其余 \x 去反斜杠保留字符）。
    result = _extract()
    dialogue = next(
        u for u in result.units if u.kind == TextKind.DIALOGUE and u.text.startswith("Bracket")
    )
    assert dialogue.text == "Bracket [[escaped] and brace {{escaped}."
    assert "[[" in dialogue.text
    assert "{{" in dialogue.text


def test_say_percent_unicode_unknown() -> None:
    # \% → %%（避免被解释为字符串格式化）；
    # \u4f60\u597d → 你好；
    # 未知转义 \t → t（Lexer.string dequote：去掉反斜杠保留字符本身）。
    result = _extract()
    dialogue = next(
        u for u in result.units if u.kind == TextKind.DIALOGUE and u.text.startswith("Percent")
    )
    assert dialogue.text == "Percent %% and unicode 你好 and unknown t."
    assert "%%" in dialogue.text
    assert "\\t" not in dialogue.text


def test_menu_choice_whitespace_collapsed() -> None:
    # 连续双空格折叠为单空格（Ren'Py 运行时对单行字符串做 \s+ → 单空格）。
    result = _extract()
    menu = next(u for u in result.units if u.kind == TextKind.MENU_CHOICE)
    assert menu.text == "{i}• Run.{/i}"


def test_marked_python_newline() -> None:
    # _("Line one.\nLine two.") 按 Python 规则 → 真换行。
    result = _extract()
    string = next(
        u for u in result.units if u.kind == TextKind.STRING and u.text.startswith("Line one.")
    )
    assert string.text == "Line one.\nLine two."
    assert "\\n" not in string.text


def test_marked_python_tab() -> None:
    # __("Column\tTabbed") 按 Python 规则 → 真制表符。
    result = _extract()
    string = next(
        u for u in result.units if u.kind == TextKind.STRING and u.text.startswith("Column")
    )
    assert string.text == "Column\tTabbed"
    assert "\\t" not in string.text


def test_stats() -> None:
    result = _extract()
    # 3 条 say + 1 菜单选项 + 2 条 _()/__() 标记字符串。
    assert result.stats() == {"dialogue": 3, "menu_choice": 1, "string": 2}
