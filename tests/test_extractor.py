"""RpyExtractor 与 CLI extract 命令的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from renai_localizer.cli import app
from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TextKind

FIXTURE = Path(__file__).parent / "fixtures" / "sample.rpy"

DIALOGUE_EXPECTED = [
    ("Welcome to Scarlet Hollow.", None, 8),
    ("Hello, traveler!", "e", 10),
    ("It's great to see you again, [player_name].", "e", 11),
    ("The town has many secrets.", "e", 15),
    ("You decide to leave.", None, 17),
    ('Farewell. "Take care of yourself."', "e", 21),
]

MENU_EXPECTED = [
    ("Ask about the town", 14),
    ("Talk to [npc_name]", 16),
    ("Stay quiet", 18),
]


def _extract_fixture() -> ExtractionResult:
    return RpyExtractor().extract_file(FIXTURE)


def test_extract_fixture_dialogue() -> None:
    result = _extract_fixture()
    dialogues = [u for u in result.units if u.kind == TextKind.DIALOGUE]
    assert [(u.text, u.speaker, u.line) for u in dialogues] == DIALOGUE_EXPECTED


def test_extract_fixture_menu_choices() -> None:
    result = _extract_fixture()
    menus = [u for u in result.units if u.kind == TextKind.MENU_CHOICE]
    assert [(u.text, u.line) for u in menus] == MENU_EXPECTED


def test_extract_context_label() -> None:
    result = _extract_fixture()
    assert all(u.context == "start" for u in result.units)


def test_extract_skips_code_and_comments() -> None:
    texts = {u.text for u in _extract_fixture().units}
    # define 中的字符串不属于待翻译文本。
    assert "Eileen" not in texts
    assert "pass" not in texts


def test_stats() -> None:
    result = _extract_fixture()
    assert result.stats() == {"dialogue": 6, "menu_choice": 3}


def test_extract_empty_script() -> None:
    result = RpyExtractor().extract("")
    assert result.units == []


def test_extract_pure_code() -> None:
    script = "label start:\n    $ x = 1\n    return\n"
    result = RpyExtractor().extract(script)
    assert result.units == []


def test_json_roundtrip() -> None:
    result = _extract_fixture()
    payload = {
        "schema_version": result.schema_version,
        "source": result.source,
        "units": [u.model_dump(mode="json") for u in result.units],
        "stats": result.stats(),
    }
    loaded = json.loads(json.dumps(payload, ensure_ascii=False))
    assert loaded["stats"] == {"dialogue": 6, "menu_choice": 3}
    assert loaded["units"][0]["kind"] == "dialogue"
    assert loaded["units"][0]["id"] == "dialogue-001"
    assert loaded["units"][-1]["id"] == "dialogue-006"
    assert loaded["units"][-1]["text"] == 'Farewell. "Take care of yourself."'
    menu_ids = [u["id"] for u in loaded["units"] if u["kind"] == "menu_choice"]
    assert menu_ids == ["menu_choice-001", "menu_choice-002", "menu_choice-003"]


def test_cli_extract(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "out.json"
    result = runner.invoke(app, ["extract", str(FIXTURE), "-o", str(output)])
    assert result.exit_code == 0, result.output
    assert output.exists()

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["source"] == str(FIXTURE)
    assert data["stats"] == {"dialogue": 6, "menu_choice": 3}
    assert data["units"][0]["text"] == "Welcome to Scarlet Hollow."
