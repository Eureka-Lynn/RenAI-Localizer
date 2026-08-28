"""Sprint 3：review 收尾项的回归测试。

覆盖：
- ``extend`` 对白续写（speaker 为 None，尾部 id / with / 注释一致处理）
- ``extend ""`` 空文本不产出单元
- 资源引用语句 ``shader`` / ``font`` / ``voice`` 跳过
- 空文本兜底过滤（``""``、``_("")`` 等）
- CLI 目录模式：递归处理目录内所有 .rpy，source 为相对路径，id 全局编号
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from renai_localizer.cli import app
from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind

FIXTURE = Path(__file__).parent / "fixtures" / "sprint3.rpy"

EXTEND_EXPECTED = [
    " second half.",
    " and a trailing bit.",
    " with an id.",
    " with a comment.",
]


def _extract() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def test_extend_dialogue_speaker_none() -> None:
    result = _extract()
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    texts = [u.text for u in dialogues]
    # 4 条 extend 续写 + 1 条普通 say "First half of the line."
    assert texts == ["First half of the line.", *EXTEND_EXPECTED]
    # 续写单元 speaker 均为 None
    for text in EXTEND_EXPECTED:
        unit = next(u for u in dialogues if u.text == text)
        assert unit.speaker is None


def test_extend_tail_clauses() -> None:
    result = _extract()
    by_text = {u.text: u for u in result.units if u.kind == TextKind.DIALOGUE}
    # id / with / 注释尾部不进入文本
    assert "id start_extend_1" not in by_text
    assert all("with dissolve" not in t for t in by_text)


def test_extend_empty_not_produced() -> None:
    result = _extract()
    assert all(u.text.strip() for u in result.units)
    texts = {u.text for u in result.units}
    assert "" not in texts


def test_resource_statements_skipped() -> None:
    result = _extract()
    texts = {u.text for u in result.units}
    assert "distortion_perlin" not in texts
    assert "gui/fonts/KelmscottRomanNF.ttf" not in texts
    assert "audio/v001.ogg" not in texts
    assert "Silent" not in texts


def test_empty_units_filtered() -> None:
    # 空 say、extend ""、python 块内 _("") 均不产出单元
    result = _extract()
    assert all(u.text.strip() for u in result.units)
    assert len(result.units) == 6  # 1 say + 4 extend + 1 string (_("Eileen"))


def test_stats() -> None:
    result = _extract()
    assert result.stats() == {"dialogue": 5, "string": 1}


def test_resource_keyword_as_speaker_still_works() -> None:
    # shader/font/voice 作为资源语句被跳过，但不影响同名字符变量做说话者
    script = 'label start:\n    font "A real dialogue line."\n    return\n'
    result = RpyExtractor().extract(script)
    assert result.units == []


def test_cli_extract_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    # 构造目录：两个 .rpy 各含一条对白
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "a.rpy").write_text(
        'label start:\n    e "Hello from a."\n    return\n', encoding="utf-8"
    )
    (sub / "b.rpy").write_text(
        'label start:\n    e "Hello from b."\n    return\n', encoding="utf-8"
    )
    output = tmp_path / "out.json"
    result = runner.invoke(app, ["extract", str(tmp_path), "-o", str(output), "-v"])
    assert result.exit_code == 0, result.output

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["stats"] == {"dialogue": 2}
    assert data["units"][0]["source"] == "a.rpy"
    assert data["units"][1]["source"] == str(Path("sub") / "b.rpy")
    assert data["units"][0]["id"] == "dialogue-001"
    assert data["units"][1]["id"] == "dialogue-002"
    assert "dialogue: 2" in result.output
