"""Sprint 3A：Writer —— 字符串翻译通道（menu_choice + string）的测试。

覆盖：
- ``quote_unicode``：``\\``、``"``、真实换行、制表符、``\\a\\b\\f\\r\\v``
- 按 old 值去重（相同 old 只输出一条）
- ``%%``→``%``：菜单选项替换、``_()`` string 不替换
- 集成测试：混合 menu_choice + string 的输出文件结构（头部 / old/new 配对 / 顺序稳定）
- 直通模式 ``new == old``
- 对白（dialogue）不进入字符串翻译通道
- CLI ``generate-tl`` 命令
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from typer.testing import CliRunner

from renai_localizer.cli import app
from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit
from renai_localizer.writer import (
    build_strings_tl,
    collect_string_entries,
    quote_unicode,
    write_strings_tl,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sprint3a.rpy"


def _extract() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def _parse_pairs(text: str) -> list[tuple[str, str]]:
    """把 strings.rpy 文本解析为 ``[(old, new), ...]``（解码转义后的规范值）。

    Writer 输出的 old/new 是合法 Ren'Py 双引号字符串字面量（转义规则与
    Python 相同），用 ``ast.literal_eval`` 解码还原规范文本值。
    """
    pairs: list[tuple[str, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("old "):
            old = ast.literal_eval(line.strip()[len("old ") :])
            new = ast.literal_eval(lines[i + 1].strip()[len("new ") :])
            pairs.append((old, new))
            i += 2
        else:
            i += 1
    return pairs


# ---------------------------------------------------------------- quote_unicode


def test_quote_unicode_backslash_and_quote() -> None:
    assert quote_unicode("a\\b") == "a\\\\b"
    assert quote_unicode('say "hi"') == 'say \\"hi\\"'
    assert quote_unicode('"both \\ and quote"') == '\\"both \\\\ and quote\\"'


def test_quote_unicode_control_characters() -> None:
    assert quote_unicode("a\nb") == "a\\nb"
    assert quote_unicode("a\tb") == "a\\tb"
    assert quote_unicode("a\rb") == "a\\rb"
    assert quote_unicode("a\ab") == "a\\ab"
    assert quote_unicode("a\bb") == "a\\bb"
    assert quote_unicode("a\fb") == "a\\fb"
    assert quote_unicode("a\vb") == "a\\vb"


def test_quote_unicode_plain_text_unchanged() -> None:
    assert quote_unicode("Eileen") == "Eileen"
    assert quote_unicode("{i}• Run.{/i}") == "{i}• Run.{/i}"


def test_quote_unicode_roundtrip_in_string_literal() -> None:
    # quote_unicode 的输出可直接放入 Ren'Py 双引号字符串字面量内；
    # 用 ast.literal_eval 解码后应还原原文（无信息丢失、无未转义引号）。
    sample = 'He said "hi"\\bye\n\t\a\b\f\r\v'
    quoted = quote_unicode(sample)
    assert ast.literal_eval(f'"{quoted}"') == sample


# ---------------------------------------------------------------- 去重 / %%


def _unit(
    kind: TextKind,
    text: str,
    *,
    id: str = "x-001",
    line: int = 1,
    source: str = "s.rpy",
) -> TranslationUnit:
    return TranslationUnit(id=id, kind=kind, text=text, line=line, source=source)


def test_dedup_same_old_output_once() -> None:
    units = [
        _unit(TextKind.MENU_CHOICE, "Go West", id="menu-001"),
        _unit(TextKind.MENU_CHOICE, "Go West", id="menu-002"),
        _unit(TextKind.STRING, "Eileen", id="string-001"),
    ]
    entries = collect_string_entries(units)
    assert [old for old, _ in entries] == ["Go West", "Eileen"]

    text = build_strings_tl(units, "schinese")
    pairs = _parse_pairs(text)
    assert len(pairs) == 2
    assert [old for old, _ in pairs] == ["Go West", "Eileen"]


def test_dedup_new_taken_from_first_unit() -> None:
    # 相同 old：以第一次出现的单元为准（直通下无差别，这里验证合并数量）。
    units = [
        _unit(TextKind.STRING, "Eileen", id="string-001"),
        _unit(TextKind.STRING, "Eileen", id="string-002"),
    ]
    text = build_strings_tl(units, "schinese")
    pairs = _parse_pairs(text)
    assert len(pairs) == 1
    assert pairs[0][0] == "Eileen"


def test_menu_choice_percent_replaced() -> None:
    # 菜单选项在注册字符串翻译前做 %% → %（config.old_substitutions）。
    units = [_unit(TextKind.MENU_CHOICE, "Keep 100%% of it.", id="menu-001")]
    text = build_strings_tl(units, "schinese")
    pairs = _parse_pairs(text)
    assert pairs[0][0] == "Keep 100% of it."
    assert pairs[0][1] == "Keep 100% of it."


def test_string_percent_not_replaced() -> None:
    # _() 标记 string 不做 %% → % 替换（old_substitutions 只作用于菜单选项）。
    units = [_unit(TextKind.STRING, "50%% off", id="string-001")]
    text = build_strings_tl(units, "schinese")
    pairs = _parse_pairs(text)
    assert pairs[0][0] == "50%% off"


def test_menu_and_string_same_raw_text_stay_distinct() -> None:
    # 同一字面量 "50%% off"：菜单选项 old 为 "50% off"，string old 为 "50%% off"，
    # 二者是运行时不同的字符串，不能合并。
    units = [
        _unit(TextKind.MENU_CHOICE, "50%% off", id="menu-001"),
        _unit(TextKind.STRING, "50%% off", id="string-001"),
    ]
    entries = collect_string_entries(units)
    assert len(entries) == 2
    assert [old for old, _ in entries] == ["50% off", "50%% off"]


# ---------------------------------------------------------------- 集成测试


def test_integration_output_structure() -> None:
    result = _extract()
    text = build_strings_tl(result, "schinese")

    lines = text.splitlines()
    assert lines[0] == "translate schinese strings:"
    assert lines[1] == ""
    # 每个条目以 "    old " / "    new " 缩进 4 空格
    for line in lines[2:]:
        if line.strip():
            assert line.startswith("    ")

    pairs = _parse_pairs(text)
    assert len(pairs) == 7  # 见 test_integration_expected_entries

    # 对白不进入字符串翻译通道
    assert "This dialogue must NOT appear" not in text

    # 空 old 不允许
    assert all(old for old, _ in pairs)


def test_integration_expected_entries() -> None:
    result = _extract()
    entries = collect_string_entries(result)
    assert len(entries) == 7  # 3 string + 4 menu（5 个选项去重后 4 条）

    text = build_strings_tl(result, "schinese")
    pairs = _parse_pairs(text)
    assert [old for old, _ in pairs] == [
        # string 不替换
        "Discount 50%% for you.",
        # \t 真实制表符 → \t；[slot] 插值保留
        "Save file\t[slot]",
        # \n 真实换行 → \n
        "Column one.\nColumn two.",
        # menu_choice：%% → %；两条 "Keep 100%% of it." 去重为一条
        "Keep 100% of it.",
        # 引号与反斜杠经 quote_unicode 转义后还原
        'A quote " and slash \\ inside choice.',
        "Choice with newline.\nSecond line.",
        # 与 string 的 "Discount 50%% for you." 是不同 old 值，分开保留
        "Discount 50% for you.",
    ]


def test_integration_order_stable() -> None:
    # 输出顺序与去重后第一次出现的顺序一致（稳定）。
    result = _extract()
    text1 = build_strings_tl(result, "schinese")
    text2 = build_strings_tl(result, "schinese")
    assert text1 == text2

    first_menus = [u for u in result.units if u.kind == TextKind.MENU_CHOICE]
    assert len(first_menus) == 5  # fixture 中 5 个选项，两条重复


def test_pass_through_new_equals_old() -> None:
    result = _extract()
    text = build_strings_tl(result, "schinese")
    pairs = _parse_pairs(text)
    for old, new in pairs:
        assert new == old


def test_quoted_escape_pairs_in_output() -> None:
    # old/new 行是合法 Ren'Py 字符串字面量：引号内容经 quote_unicode 转义。
    result = _extract()
    text = build_strings_tl(result, "schinese")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("old ", "new ")):
            continue
        value = stripped.split(" ", 1)[1]
        assert value.startswith('"') and value.endswith('"')
        # 值内部不得出现未转义的双引号
        inner = value[1:-1]
        assert '\\"'.join(inner.split('\\"')) == inner


def test_extraction_result_or_units_input() -> None:
    # 主函数同时接受 ExtractionResult 与 unit 列表。
    result = _extract()
    from_units = build_strings_tl(result.units, "schinese")
    from_result = build_strings_tl(result, "schinese")
    assert from_units == from_result


class _UppercaseTranslator:
    """最小 Translator 实现：把每个单元翻译为大写（模拟未来 LLM 接入）。"""

    def translate(self, units: list[TranslationUnit]) -> dict[str, str]:
        return {u.id: u.text.upper() for u in units}


def test_translator_protocol_custom_translation() -> None:
    # 提供 Translator 时 new 使用其返回文本；未覆盖的 id 直通原文。
    units = [
        _unit(TextKind.MENU_CHOICE, "Go West", id="menu-001"),
        _unit(TextKind.STRING, "Eileen", id="string-001"),
    ]
    text = build_strings_tl(units, "schinese", translator=_UppercaseTranslator())
    pairs = _parse_pairs(text)
    assert [old for old, _ in pairs] == ["Go West", "Eileen"]
    assert [new for _, new in pairs] == ["GO WEST", "EILEEN"]


# ---------------------------------------------------------------- write / CLI


def test_write_strings_tl_writes_language_dir(tmp_path: Path) -> None:
    result = _extract()
    target = write_strings_tl(tmp_path, "schinese", result)
    assert target == tmp_path / "schinese" / "strings.rpy"
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("translate schinese strings:\n\n")


def test_cli_generate_tl(tmp_path: Path) -> None:
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
        ],
    )
    assert res.exit_code == 0, res.output

    target = out_dir / "schinese" / "strings.rpy"
    assert target.exists()
    pairs = _parse_pairs(target.read_text(encoding="utf-8"))
    assert len(pairs) == 7
    assert all(new == old for old, new in pairs)  # 直通
    assert "已生成" in res.output


def test_cli_generate_tl_default_output_dir() -> None:
    # 不指定 -o：默认 .cache/<source 父目录名>/tl/（不写入游戏目录）。
    runner = CliRunner()
    with runner.isolated_filesystem():
        data = {
            "schema_version": 1,
            "source": ".cache/sample/rpy",
            "units": [
                {
                    "id": "menu-001",
                    "kind": "menu_choice",
                    "text": "Go West",
                    "line": 1,
                    "source": "script.rpy",
                    "speaker": None,
                    "context": None,
                }
            ],
        }
        Path("extracted.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        res = runner.invoke(app, ["generate-tl", "extracted.json", "--language", "schinese"])
        assert res.exit_code == 0, res.output

        target = Path(".cache") / "sample" / "tl" / "schinese" / "strings.rpy"
        assert target.exists()
        assert target.read_text(encoding="utf-8").startswith("translate schinese strings:\n\n")
        assert "schinese" in res.output


def test_cli_generate_tl_missing_file(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["generate-tl", str(tmp_path / "nope.json")])
    assert res.exit_code == 1
    assert "路径不存在" in res.output


def test_cli_generate_tl_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(app, ["generate-tl", str(bad)])
    assert res.exit_code == 1
    assert "无法读取" in res.output
