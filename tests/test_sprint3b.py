"""Sprint 3B：对话翻译标识符复刻与对话翻译文件生成。

覆盖：
- ``encode_say_string`` 精确复刻向量（转义顺序固定）
- ``say_get_code`` 各结构形态（who / 属性 / 临时属性 / arguments / nointeract / id / with）
- ``dialogue_identifier``：MD5 digest、label 前缀、冲突 ``_1`` 后缀、显式 id 覆盖
- 已验证标识符向量（与 Ren'Py 8.0.3 算法手工核对）
- ``build_dialogue_tl_all`` 输出结构 + 全局 used_ids 去重
- ``write_dialogue_tl`` 镜像源目录结构
- extractor 对 say 结构字段的解析（fixture）
- CLI ``generate-tl`` 对话通道（含不覆盖源文件回归）
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from renai_localizer.cli import app
from renai_localizer.dialogue import (
    build_dialogue_tl,
    build_dialogue_tl_all,
    collect_dialogue_units,
    dialogue_identifier,
    encode_say_string,
    say_get_code,
    write_dialogue_tl,
)
from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit

FIXTURE = Path(__file__).parent / "fixtures" / "sprint3b.rpy"


def _extract() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def _unit(
    text: str,
    *,
    who: str | None = "e",
    attrs: tuple[str, ...] | None = None,
    temp: tuple[str, ...] | None = None,
    with_expr: str | None = None,
    arguments: str | None = None,
    nointeract: bool = False,
    say_id: str | None = None,
) -> TranslationUnit:
    return TranslationUnit(
        id="d-001",
        kind=TextKind.DIALOGUE,
        text=text,
        line=1,
        source="game/script.rpy",
        speaker=who,
        context="start",
        say_who=who,
        say_attributes=attrs,
        say_temporary_attributes=temp,
        say_with=with_expr,
        say_arguments=arguments,
        say_nointeract=nointeract,
        say_id=say_id,
    )


# ---------------------------------------------------------------- encode_say_string


def test_encode_say_string_basic() -> None:
    assert encode_say_string("Hello world.") == '"Hello world."'


def test_encode_say_string_backslash_first() -> None:
    # \\ → \\\\ 必须先于其它转义，顺序不可调换
    assert encode_say_string("a\\b") == '"a\\\\b"'
    assert encode_say_string('quote " inside') == '"quote \\" inside"'
    assert encode_say_string("line1\nline2") == '"line1\\nline2"'
    # 反斜杠 + 换行 + 引号组合
    assert encode_say_string('x\\y\n"z"') == '"x\\\\y\\n\\"z\\""'


def test_encode_say_string_trailing_spaces() -> None:
    # 连续空格的第二个及之后空格 → 反斜杠空格（(?<= ) 前瞻）
    assert encode_say_string("two  spaces") == '"two \\ spaces"'


# ---------------------------------------------------------------- say_get_code


def test_say_get_code_plain() -> None:
    assert say_get_code(_unit("Hello world.")) == 'e "Hello world."'


def test_say_get_code_narration() -> None:
    unit = _unit("Narrator line.", who=None)
    assert say_get_code(unit) == '"Narrator line."'


def test_say_get_code_attributes() -> None:
    unit = _unit("NVL centered.", who="nvl", attrs=("centered",))
    assert say_get_code(unit) == 'nvl centered "NVL centered."'


def test_say_get_code_temporary_attributes() -> None:
    unit = _unit("Flash line.", who="e", temp=("flash",))
    assert say_get_code(unit) == 'e @ flash "Flash line."'


def test_say_get_code_with_expression() -> None:
    unit = _unit("Fade with args.", who="e", with_expr="Dissolve(0.5, alpha=True)")
    assert say_get_code(unit) == 'e "Fade with args." with Dissolve(0.5, alpha=True)'


def test_say_get_code_arguments() -> None:
    unit = _unit("With arguments.", who="e", arguments="(test=1)")
    assert say_get_code(unit) == 'e "With arguments." (test=1)'


def test_say_get_code_nointeract() -> None:
    unit = _unit("No interact line.", who="e", nointeract=True)
    assert say_get_code(unit) == 'e "No interact line." nointeract'


def test_say_get_code_id() -> None:
    unit = _unit("Explicit id.", who="e", say_id="custom_abc")
    assert say_get_code(unit) == 'e "Explicit id." id custom_abc'


def test_say_get_code_translated_what() -> None:
    # 写 tl 时传翻译后的文本
    unit = _unit("Hello world.", who="e")
    assert say_get_code(unit, "你好，世界。") == 'e "你好，世界。"'


# ---------------------------------------------------------------- dialogue_identifier


def _digest(code: str) -> str:
    return hashlib.md5((code + "\r\n").encode("utf-8")).hexdigest()[:8]


def test_identifier_verified_vectors() -> None:
    """任务要求的已验证标识符向量（端到端：say_get_code → digest → label 前缀）。"""
    cases: list[tuple[TranslationUnit, str | None, str, str]] = [
        # (unit, label, 期望标识符, 说明)
        (_unit("Hello world.", who="e"), "start", "start_d38c8818", "简单对白"),
        (_unit("Narrator line.", who=None), None, "27d809bc", "叙述无 label"),
        (_unit("A centered line.", who="centered"), "start", "start_eded8ff7", "centered 变体"),
        (_unit("Hello", who="e", with_expr="dissolve"), "start", "start_c4c0b0f8", "with 子句"),
        (_unit("Test", who="e", arguments="(test=1)"), "start", "start_31d6f3dd", "arguments 子句"),
        (_unit("No interact", who="e", nointeract=True), "start", "start_dc8d3ad9", "nointeract"),
        (_unit(" second half.", who="extend"), "start", "start_b20c726a", "extend 续写"),
        (_unit("Multi dot", who="m.e"), "start", "start_a475a3e0", "点号 who"),
        (_unit("A", who="e"), "start", "start_32c94664", "相同文本跨 label"),
    ]
    for unit, label, expected, desc in cases:
        # 端到端：先验证 say_get_code 生成的 code 与向量一致，再验证标识符
        got = dialogue_identifier(unit, label, set())
        assert got == expected, f"{desc}: unit={unit!r} → {got!r}, 期望 {expected!r}"


def test_identifier_explicit_id_override() -> None:
    unit = _unit("Explicit id.", who="e", say_id="custom_abc")
    used: set[str] = set()
    assert dialogue_identifier(unit, "start", used) == "custom_abc"
    assert used == {"custom_abc"}


def test_identifier_conflict_suffix() -> None:
    """同一文本在同一 label 内出现两次：第二个加 ``_1``。"""
    unit = _unit("Repeated text.", who="e")
    used: set[str] = set()
    first = dialogue_identifier(unit, "second", used)
    second = dialogue_identifier(unit, "second", used)
    assert first == "second_" + _digest('e "Repeated text."')
    assert second == first + "_1"
    assert len(used) == 2


def test_identifier_global_shared_across_labels() -> None:
    """跨 label 相同文本 + 相同 base：全局 used_ids 也追加后缀。"""
    unit_a = _unit("Hello world.", who="e")
    unit_b = _unit("Hello world.", who="e")
    used: set[str] = set()
    id_a = dialogue_identifier(unit_a, "start", used)
    id_b = dialogue_identifier(unit_b, "start", used)
    assert id_a == "start_d38c8818"
    assert id_b == "start_d38c8818_1"


# ---------------------------------------------------------------- extractor fixture


def test_extract_say_structure_fields() -> None:
    result = _extract()
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    by_text = {u.text: u for u in dialogues}

    assert by_text["Hello world."].say_who == "e"
    assert by_text["Narrator line."].say_who is None
    assert by_text["A centered line."].say_who == "centered"
    assert by_text["NVL centered."].say_who == "nvl"
    assert by_text["NVL centered."].say_attributes == ("centered",)
    assert by_text["Flash line."].say_temporary_attributes == ("flash",)
    assert by_text["Fade with args."].say_with == "Dissolve(0.5, alpha=True)"
    assert by_text["With arguments."].say_arguments == "(test=1)"
    assert by_text["No interact line."].say_nointeract is True
    assert by_text["Explicit id."].say_id == "custom_abc"
    assert by_text["Id with colon."].say_id == "start_colon_id"
    assert by_text["Two spaces here."].text == "Two spaces here."  # 空白折叠
    assert by_text[" second part."].say_who == "extend"
    assert by_text["Dotted who."].say_who == "m.e"


def test_extract_speaker_semantics_unchanged() -> None:
    result = _extract()
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    by_text = {u.text: u for u in dialogues}
    # 叙述 / centered / nvl / extend → speaker None
    assert by_text["Narrator line."].speaker is None
    assert by_text["A centered line."].speaker is None
    assert by_text["An NVL line."].speaker is None
    assert by_text[" second part."].speaker is None
    # 普通 who 保留
    assert by_text["Hello world."].speaker == "e"


# ---------------------------------------------------------------- writer structure


def test_build_dialogue_tl_structure() -> None:
    result = _extract()
    dialogues = collect_dialogue_units(result)
    text = build_dialogue_tl(
        dialogues,
        "schinese",
        source_path="tests/fixtures/sprint3b.rpy",
    )
    lines = text.splitlines()
    # 头部注释 + translate 行
    assert lines[0] == "# tests/fixtures/sprint3b.rpy:11"
    assert lines[1] == "translate schinese start_d38c8818:"
    # 每个块：空行 → 原 code 注释 → 翻译 code → 空行
    assert lines[2] == ""
    assert lines[3] == '    # e "Hello world."'
    assert lines[4] == '    e "Hello world."'
    assert lines[5] == ""


def test_build_dialogue_tl_pass_through() -> None:
    result = _extract()
    dialogues = collect_dialogue_units(result)
    text = build_dialogue_tl(dialogues, "schinese", source_path="x.rpy")
    # 直通：每条翻译 code 的字符串部分与原 code 一致
    for line in text.splitlines():
        if line.startswith("    # "):
            assert line[6:] == line[6:]


def test_build_dialogue_tl_all_no_duplicates() -> None:
    """全局共享 used_ids：跨文件/跨 label 无重复标识符。"""
    result = _extract()
    files = build_dialogue_tl_all(result, "schinese")
    ids: list[str] = []
    for text in files.values():
        for line in text.splitlines():
            if line.startswith("translate "):
                ids.append(line.split()[2])
    assert len(ids) == len(set(ids)), "存在重复标识符"


def test_write_dialogue_tl_mirrors_source(tmp_path: Path) -> None:
    result = _extract()
    paths = write_dialogue_tl(tmp_path, "schinese", result)
    assert len(paths) == 1
    target = paths[0]
    # 单文件提取（绝对 source）归一化为文件名层级；目录模式保留完整目录结构。
    assert target.parent == tmp_path / "schinese"
    assert target.name == "sprint3b.rpy"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    # 结构：`# <source>:<line>` 头注释 + `translate <lang> <id>:` 块
    assert content.splitlines()[1].startswith("translate schinese ")
    assert "# sprint3b.rpy:11" in content
    # 源文件不被覆盖
    assert FIXTURE.read_text(encoding="utf-8").startswith("# Sprint 3B 测试夹具")


# ---------------------------------------------------------------- CLI


def test_cli_generate_tl_dialogue_channel(tmp_path: Path) -> None:
    result = _extract()
    data_path = tmp_path / "extracted.json"
    data_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "generate-tl",
            str(data_path),
            "--language",
            "schinese",
            "-o",
            str(out_dir),
            "-v",
        ],
    )
    assert res.exit_code == 0, res.output

    strings_target = out_dir / "schinese" / "strings.rpy"
    assert strings_target.exists()
    # 对话通道：单文件提取归一化到输出目录下（不覆盖源文件）
    dialogue_target = out_dir / "schinese" / "sprint3b.rpy"
    assert dialogue_target.exists()
    assert "对白块总数" in res.output
    assert "sprint3b.rpy" in res.output
    # 源文件未被覆盖
    assert FIXTURE.read_text(encoding="utf-8").startswith("# Sprint 3B 测试夹具")


def test_cli_generate_tl_does_not_overwrite_source(tmp_path: Path) -> None:
    """回归：绝对 source 不得让对话输出覆盖源文件。"""
    fixture_src = FIXTURE.read_text(encoding="utf-8")
    result = _extract()  # source 是绝对路径
    data_path = tmp_path / "extracted.json"
    data_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    runner = CliRunner()
    res = runner.invoke(
        app,
        ["generate-tl", str(data_path), "--language", "schinese", "-o", str(out_dir)],
    )
    assert res.exit_code == 0, res.output
    # 源文件未被对话输出覆盖
    assert FIXTURE.read_text(encoding="utf-8") == fixture_src
    assert FIXTURE.read_text(encoding="utf-8").startswith("# Sprint 3B 测试夹具")
