"""Sprint 2：新增语法场景的测试（TDD：先红后绿）。

覆盖：
- 三引号多行字符串（``line`` 记录起始行）
- 单引号字符串（含 ``\\'`` 转义），与双引号同等处理
- ``_()`` / ``__()`` 标记字符串（``kind="string"``）
- say 语句的 ``id`` 子句（id 内容不进入文本）
- say 变体 ``centered`` / ``nvl`` / ``nvl centered``（speaker 为 None）
- 反例：注释内引号、``$`` / ``python`` 块、裸 define 字符串、``_p()`` / ``___()``
"""

from __future__ import annotations

from pathlib import Path

from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind

FIXTURE = Path(__file__).parent / "fixtures" / "sprint2.rpy"

DIALOGUE_EXPECTED: list[tuple[str, str | None, int]] = [
    ("A centered line.", None, 16),
    ("An NVL line.", None, 17),
    ("NVL centered line.", None, 18),
    ("Single-quoted dialogue.", "e", 21),
    ("It's got an escaped quote.", "s", 22),
    ("This is a multi-line\ndialogue that spans\nseveral lines.", "e", 25),
    ("This has an id.", "e", 30),
    ("This has an id with colon.", "e", 31),
    ("Fade text.", "e", 32),
    ("Commented line.", "e", 35),
]

STRING_EXPECTED: list[tuple[str, int]] = [
    ("Eileen", 4),
    ("curious", 7),
    ("hello", 8),
    ("Screen Label", 56),
    ("Screen Button", 57),
]

NOT_EXTRACTED = {
    "Silent",
    "not translatable",
    "also not translatable",
    "not here either",
    "multi line paragraph",
    "triple",
    "not real dialogue",
    "init python string",
    "init python double",
    "vertical",  # screen 属性字符串，非对白
}


def _extract() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def test_sprint2_dialogue() -> None:
    result = _extract()
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    assert [(u.text, u.speaker, u.line) for u in dialogues] == DIALOGUE_EXPECTED


def test_sprint2_marked_strings() -> None:
    result = _extract()
    strings = [u for u in result.units if u.kind == TextKind.STRING]
    assert [(u.text, u.line) for u in strings] == STRING_EXPECTED
    assert all(u.speaker is None and u.context is None for u in strings)


def test_sprint2_say_variants_not_speaker() -> None:
    result = _extract()
    by_text = {u.text: u for u in result.units if u.kind == TextKind.DIALOGUE}
    assert by_text["A centered line."].speaker is None
    assert by_text["An NVL line."].speaker is None
    assert by_text["NVL centered line."].speaker is None


def test_sprint2_id_clause_not_in_text() -> None:
    result = _extract()
    for u in result.units:
        if u.kind == TextKind.DIALOGUE:
            assert "id start_special" not in u.text


def test_sprint2_negative_cases() -> None:
    result = _extract()
    texts = {u.text for u in result.units}
    assert NOT_EXTRACTED.isdisjoint(texts)


def test_sprint2_stats() -> None:
    result = _extract()
    assert result.stats() == {"dialogue": 10, "string": 5}
