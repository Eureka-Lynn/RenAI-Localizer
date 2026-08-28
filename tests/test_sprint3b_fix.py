"""Sprint 3B 修复回归测试：误提取（play/queue/show + ATL/style 块）。

覆盖：
- 保留语句关键字（``play`` / ``queue`` / ``stop`` / ``show`` / ``scene`` /
  ``camera`` / ``window`` / ``voice`` / ``shader`` / ``font``）开头的行
  整体跳过（关键字后可跟字符串字面量，但不是对白）
- ``image`` / ``transform`` / ``style`` 块内 ATL 引号行与样式属性行
  （``color`` / ``thumb`` / ``background`` / ``layout`` / ``size_group`` /
  ``unscrollable`` 等）不提取
- 块结束后对白仍正常提取（块状态正确退出）
- 单行 ``image x = ...`` / ``style x is y`` 不受影响
"""

from __future__ import annotations

from pathlib import Path

from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind

FIXTURE = Path(__file__).parent / "fixtures" / "sprint3b_fix.rpy"


def _extract() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def _texts() -> set[str]:
    return {u.text for u in _extract().units}


def test_statement_keywords_not_dialogue() -> None:
    texts = _texts()
    for text in [
        "audio/x.ogg",
        "audio/boom.ogg",
        "audio/step.ogg",
        "Hello on screen",
        "bg room",
        "audio/voice.ogg",
        "distortion_perlin",
        "gui/fonts/KelmscottRomanNF.ttf",
    ]:
        assert text not in texts, f"{text!r} 不应被提取"


def test_atl_image_block_not_dialogue() -> None:
    texts = _texts()
    assert "bg fire dark" not in texts
    assert "bg fire base" not in texts


def test_transform_block_not_dialogue() -> None:
    texts = _texts()
    assert "raw quoted line" not in texts


def test_style_block_properties_not_dialogue() -> None:
    texts = _texts()
    for prop in ["#000", "#cc0000", "gui/overlay/main_menu.png", "subtitle", "navigation", "hide"]:
        assert prop not in texts, f"style 属性值 {prop!r} 不应被提取"


def test_dialogue_after_blocks_still_extracted() -> None:
    result = _extract()
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    assert [u.text for u in dialogues] == [
        "Dialogue after statements.",
        "Dialogue after blocks.",
    ]


def test_single_line_image_and_style_unaffected() -> None:
    # 单行 image x = ... / style x is y 不影响后续对白提取。
    script = (
        "label start:\n"
        "    image bg fire single = \"bg fire base\"\n"
        "    style plain is default\n"
        "    e \"Still works.\"\n"
        "    return\n"
    )
    result = RpyExtractor().extract(script)
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    assert [u.text for u in dialogues] == ["Still works."]


def test_stats() -> None:
    result = _extract()
    # 2 条对白（语句后 / 块后）+ 1 条 _("Eileen") 标记字符串。
    assert result.stats() == {"dialogue": 2, "string": 1}
