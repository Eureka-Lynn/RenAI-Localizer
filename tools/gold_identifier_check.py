"""Sprint 3B 金标准集成检查：与游戏内置 Ren'Py 8.0.3 黑盒比对标识符算法。

背景
----
我们复刻了 Ren'Py 8.0.3 的对白翻译标识符算法（``encode_say_string``、
``Say.get_code``、``unique_identifier``）。本脚本用 **游戏自带解释器**
（``ScarletHollow/lib/py3-windows-x86_64/python.exe``）直接导入游戏内置
``renpy`` 模块，对同一组输入计算真实的 get_code / 标识符，再与我们的
``renai_localizer.dialogue`` 输出逐一比对，确保两端完全一致（黑盒金标准，
不依赖人工向量）。

比对内容
--------
1. ``encode_say_string``：纯函数黑盒比对（转义顺序固定）。
2. ``Say.get_code()``：用游戏内置 ``ast.Say`` 构造各形态 say 语句比对。
3. ``unique_identifier``：用游戏内置 ``Restructurer`` 比对 label/digest 与
   冲突 ``_1`` / ``_2`` 后缀。
4. 端到端标识符：黑盒组合 ``get_code → md5 → unique_identifier`` 与我们
   ``dialogue_identifier`` 的自动路径逐项比对。

输入向量与 ``tests/test_sprint3b.py::test_identifier_verified_vectors`` 的
已验证向量完全一致（标识符期望值已按 Ren'Py 8.0.3 算法手工核对），黑盒
交叉验证同一输入。

显式 ``id`` 覆盖是 ``create_translate`` 的额外语义（不属于
``unique_identifier`` 本身），由本地静态向量与单元测试覆盖，黑盒部分不做
端到端比对。

``arguments``（say 参数）用例保留在本地静态向量与单元测试中，但**不参与
黑盒比对**：游戏内置 ``renpy.ast.Arguments`` 无公开可构造类（只有
``renpy.parser.parse_arguments`` 函数），而 ``Say.get_code()`` 会调用
``arguments.get_code()``，字符串参数无法直接喂给黑盒；真实语料（Scarlet
Hollow 67,225 对白块）无 arguments 形态，影响可忽略。被排除的用例由
``BLACKBOX_EXCLUDED`` 统一过滤（见下方定义）。

约束
----
- 游戏目录保持**只读**：不写入任何内容，只创建到 ``renpy`` 目录的 junction
  （Windows），所有产物只放在 ``.cache/gold/`` 下，不进 git。
- 本脚本**不在默认 pytest 集合中**（工具脚本，手动执行）。

用法
----
    python tools/gold_identifier_check.py                 # 默认游戏路径
    python tools/gold_identifier_check.py --game <dir>    # 指定游戏目录
    python tools/gold_identifier_check.py --only-local    # 只跑本地静态检查

全部通过打印 ``GOLD STANDARD OK``；任一不匹配打印详细差异并以非零退出。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast

# Windows 终端（如 cmd.exe）默认使用 GBK，直接输出中文会乱码，重配置为 UTF-8。
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GAME_DEFAULT = Path(r"F:\SteamLibrary\steamapps\common\ScarletHollow")

# 我们自己的实现（金标准脚本运行在本机系统 Python 下）。
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from renai_localizer.dialogue import (  # noqa: E402
    dialogue_identifier,
    encode_say_string,
    say_get_code,
)
from renai_localizer.models import TextKind, TranslationUnit  # noqa: E402

# ---------------------------------------------------------------------------
# 测试向量
# ---------------------------------------------------------------------------

# 纯函数向量（encode_say_string）：(原文, 期望输出)
ENCODE_VECTORS: list[tuple[str, str]] = [
    ("Hello world.", '"Hello world."'),
    ("two  spaces", '"two \\ spaces"'),
    ('say "quote" \\ back\n newline', '"say \\"quote\\" \\\\ back\\n newline"'),
    ("a\\b", '"a\\\\b"'),
    ("line1\nline2", '"line1\\nline2"'),
]

# say 结构向量：(名称, 字段覆盖, 期望 get_code, 期望标识符)
#
# 输入与 ``tests/test_sprint3b.py::test_identifier_verified_vectors`` 的已
# 验证向量完全一致（标识符期望值已按 Ren'Py 8.0.3 算法手工核对），金标准
# 脚本用游戏内置 Ren'Py 黑盒交叉验证同一输入。
# 字段覆盖基于 _unit() 默认值；say_who=None 表示叙述（真 None），
# context=None 表示无 label（叙述时标识符直接用 digest，无前缀）。
SAY_CASES: list[tuple[str, dict[str, object], str, str]] = [
    (
        "plain",
        {"text": "Hello world.", "context": "start", "say_who": "e"},
        'e "Hello world."',
        "start_d38c8818",
    ),
    (
        "narration",
        {"text": "Narrator line.", "context": None, "say_who": None},
        '"Narrator line."',
        "27d809bc",
    ),
    (
        "attributes",
        {
            "text": "A centered line.",
            "context": "start",
            "say_who": "centered",
        },
        'centered "A centered line."',
        "start_eded8ff7",
    ),
    (
        "with_dissolve",
        {"text": "Hello", "context": "start", "say_who": "e", "say_with": "dissolve"},
        'e "Hello" with dissolve',
        "start_c4c0b0f8",
    ),
    (
        "arguments",
        {
            "text": "Test",
            "context": "start",
            "say_who": "e",
            "say_arguments": "(test=1)",
        },
        'e "Test" (test=1)',
        "start_31d6f3dd",
    ),
    (
        "nointeract",
        {"text": "No interact", "context": "start", "say_who": "e", "say_nointeract": True},
        'e "No interact" nointeract',
        "start_dc8d3ad9",
    ),
    (
        "extend",
        {"text": " second half.", "context": "start", "say_who": "extend"},
        'extend " second half."',
        "start_b20c726a",
    ),
    (
        "dotted_who",
        {"text": "Multi dot", "context": "start", "say_who": "m.e"},
        'm.e "Multi dot"',
        "start_a475a3e0",
    ),
    (
        "same_text",
        {"text": "A", "context": "start", "say_who": "e"},
        'e "A"',
        "start_32c94664",
    ),
]

# 黑盒排除的用例（见模块 docstring：真实语料无 arguments，且游戏内置
# renpy.ast.Arguments 不可直接构造）。保留本地静态向量与单元测试覆盖。
BLACKBOX_EXCLUDED: frozenset[str] = frozenset({"arguments"})

# 冲突后缀向量：(label, digest, 预置 used_ids, 期望)
UNIQUE_VECTORS: list[tuple[str | None, str, set[str], str]] = [
    ("start", "d38c8818", set(), "start_d38c8818"),
    (None, "d38c8818", set(), "d38c8818"),
    ("start", "d38c8818", {"start_d38c8818"}, "start_d38c8818_1"),
    ("start", "d38c8818", {"start_d38c8818", "start_d38c8818_1"}, "start_d38c8818_2"),
]


def _unit(**kw: object) -> TranslationUnit:
    """构造 TranslationUnit（只填充金标准比对需要的字段）。"""
    defaults: dict[str, object] = {
        "id": "u1",
        "kind": TextKind.DIALOGUE,
        "text": "Hello world.",
        "source": "gold.rpy",
        "line": 1,
        "context": "start",
        "say_who": "e",
    }
    defaults.update(kw)
    return TranslationUnit(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 本地静态检查（系统 Python，不需要游戏目录）
# ---------------------------------------------------------------------------

def _check_encode_say_string() -> list[str]:
    failures: list[str] = []
    for raw, expected in ENCODE_VECTORS:
        got = encode_say_string(raw)
        if got != expected:
            failures.append(f"encode_say_string({raw!r}) = {got!r}, 期望 {expected!r}")
    return failures


def _check_say_get_code() -> list[str]:
    failures: list[str] = []
    for name, fields, expected_code, _expected_id in SAY_CASES:
        unit = _unit(**fields)
        got = say_get_code(unit)
        if got != expected_code:
            failures.append(f"[{name}] say_get_code = {got!r}, 期望 {expected_code!r}")
    return failures


def _check_dialogue_identifier() -> list[str]:
    failures: list[str] = []
    for name, fields, _expected_code, expected_id in SAY_CASES:
        unit = _unit(**fields)
        got = dialogue_identifier(unit, unit.context, set())
        if got != expected_id:
            failures.append(f"[{name}] dialogue_identifier = {got!r}, 期望 {expected_id!r}")

    # 显式 id 覆盖（create_translate 语义）
    unit = _unit(say_id="custom_abc")
    used: set[str] = set()
    got = dialogue_identifier(unit, "start", used)
    if got != "custom_abc":
        failures.append(f"[explicit_id] dialogue_identifier = {got!r}, 期望 'custom_abc'")
    if used != {"custom_abc"}:
        failures.append(f"[explicit_id] used_ids = {used!r}, 期望 {{'custom_abc'}}")

    return failures


def _check_unique_suffix() -> list[str]:
    """冲突后缀：复刻 unique_identifier 的 while 循环语义。"""
    failures: list[str] = []

    def local_unique(label: str | None, digest: str, used: set[str]) -> str:
        base = digest if label is None else label.replace(".", "_") + "_" + digest
        identifier = base
        i = 0
        while identifier in used:
            i += 1
            identifier = f"{base}_{i}"
        return identifier

    for label, digest, used_ids, expected in UNIQUE_VECTORS:
        got = local_unique(label, digest, set(used_ids))
        if got != expected:
            failures.append(
                f"unique_identifier({label!r}, {digest!r}, used={sorted(used_ids)}) "
                f"= {got!r}, 期望 {expected!r}"
            )
    return failures


def run_local_checks() -> list[str]:
    failures: list[str] = []
    failures += _check_encode_say_string()
    failures += _check_say_get_code()
    failures += _check_dialogue_identifier()
    failures += _check_unique_suffix()
    return failures


# ---------------------------------------------------------------------------
# 黑盒：用游戏自带解释器运行计算代码
# ---------------------------------------------------------------------------

# 注入到游戏解释器的计算代码。输入变量：
#   ENC: list[str]                   —— encode_say_string 输入
#   SAY: list[(name, dict)]          —— Say 构造字段（见 _fields_to_renpy；
#                                      arguments 用例被 BLACKBOX_EXCLUDED 排除）
#   UNIQ: list[(label, digest, used)]—— unique_identifier 输入
# 输出：
#   enc_out: list[(raw, result)]
#   say_out: list[(name, get_code)]
#   uniq_out: list[(label, digest, used_sorted, result)]
#   e2e_out: list[(name, get_code, digest, identifier)]
GOLD_CALC = r"""
import sys
sys.path.insert(0, r"{game}")

for _m in [
    "renpy.config", "renpy.log", "renpy.arguments", "renpy.compat.fixes",
    "renpy.debug", "renpy.object", "renpy.revertable", "renpy.rollback",
    "renpy.python", "renpy.parser", "renpy.ast", "renpy.translation",
]:
    __import__(_m)

import hashlib
import renpy
import renpy.ast as _ast
import renpy.translation as _tr


class _StubTranslator:
    default_translates = {{}}


class _StubScript:
    translator = _StubTranslator()


class _StubGame:
    script = _StubScript()


renpy.game = _StubGame()

_LOC = ("gold.rpy", 1)

# 1) encode_say_string
enc_out = []
for _raw in ENC:
    enc_out.append((_raw, _tr.encode_say_string(_raw)))

# 2) Say.get_code
say_out = []
for _name, _f in SAY:
    _say = _ast.Say(
        _LOC,
        _f.get("who"),
        _f.get("what", "Hello world."),
        _f.get("with"),
        interact=_f.get("interact", True),
        attributes=_f.get("attributes"),
        arguments=_f.get("arguments"),
        temporary_attributes=_f.get("temporary_attributes"),
        identifier=_f.get("identifier"),
    )
    say_out.append((_name, _say.get_code()))

# 3) unique_identifier（含冲突后缀）
uniq_out = []
for _label, _digest, _used in UNIQ:
    _r = _tr.Restructurer([])
    _r.identifiers = set(_used)
    _uniq = _r.unique_identifier(_label, _digest)
    uniq_out.append((_label, _digest, sorted(_used), _uniq))

# 4) 端到端自动标识符：get_code → md5 → unique_identifier（无预置 used）
e2e_out = []
for _name, _f in SAY:
    _say = _ast.Say(
        _LOC,
        _f.get("who"),
        _f.get("what", "Hello world."),
        _f.get("with"),
        interact=_f.get("interact", True),
        attributes=_f.get("attributes"),
        arguments=_f.get("arguments"),
        temporary_attributes=_f.get("temporary_attributes"),
        identifier=_f.get("identifier"),
    )
    _code = _say.get_code()
    _digest = hashlib.md5((_code + "\r\n").encode("utf-8")).hexdigest()[:8]
    _r = _tr.Restructurer([])
    _r.identifiers = set()
    _id = _r.unique_identifier(_f.get("label", "start"), _digest)
    e2e_out.append((_name, _code, _digest, _id))

print("__GOLD__" + repr((enc_out, say_out, uniq_out, e2e_out)))
"""


def _fields_to_renpy(fields: dict[str, object]) -> dict[str, object]:
    """把我们的 TranslationUnit 字段映射为游戏 Say 构造参数。

    ``say_who`` 为 ``None``（叙述）→ who=None；否则原样传。
    """
    who: object = fields.get("say_who")
    if who == "":
        who = None
    return {
        "who": who,
        "what": fields.get("text", "Hello world."),
        "with": fields.get("say_with"),
        "arguments": fields.get("say_arguments"),
        "interact": not fields.get("say_nointeract", False),
        "attributes": (
            list(cast(Iterable[object], fields["say_attributes"]))
            if fields.get("say_attributes")
            else None
        ),
        "temporary_attributes": (
            list(cast(Iterable[object], fields["say_temporary_attributes"]))
            if fields.get("say_temporary_attributes")
            else None
        ),
        "identifier": fields.get("say_id"),
        "label": fields.get("context"),
    }


def run_gold(
    game_dir: Path,
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[tuple[str | None, str, list[str], str]],
    list[tuple[str, str, str, str]],
]:
    """运行游戏内置 Ren'Py 黑盒，返回四组比对结果。"""
    if not (game_dir / "renpy").is_dir():
        raise FileNotFoundError(f"游戏目录缺少 renpy/ 子目录：{game_dir}")

    py = game_dir / "lib" / "py3-windows-x86_64" / "python.exe"
    if not py.exists():
        py = game_dir / "lib" / "python3" / "python"
        if not py.exists():
            raise FileNotFoundError(f"未找到游戏自带解释器：{game_dir}")

    cache_dir = PROJECT_ROOT / ".cache" / "gold"
    cache_dir.mkdir(parents=True, exist_ok=True)
    junction = cache_dir / "renpy_junction"

    # 只读引用：Windows 下创建 junction 指向游戏 renpy 目录（避免把整个游戏
    # 目录加入 sys.path 导致误写），POSIX 下直接注入路径。
    use_junction = os.name == "nt"
    if use_junction:
        if junction.exists() or junction.is_symlink():
            if junction.is_dir():
                junction.rmdir()
            else:
                junction.unlink()
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(game_dir / "renpy")],
                check=True,
                capture_output=True,
            )
        except Exception:
            use_junction = False

    try:
        # 探针端 `for _raw in ENC` 期望字符串列表（直接传给 encode_say_string）。
        enc_input = [raw for raw, _ in ENCODE_VECTORS]
        # arguments 用例不参与黑盒（见模块 docstring / BLACKBOX_EXCLUDED）。
        say_input = [
            (name, _fields_to_renpy(fields))
            for name, fields, _, _ in SAY_CASES
            if name not in BLACKBOX_EXCLUDED
        ]
        uniq_input = [(label, digest, sorted(used)) for label, digest, used, _ in UNIQUE_VECTORS]

        code = GOLD_CALC.format(game=str(game_dir))
        probe = (
            "import sys\n"
            f"sys.path.insert(0, {str(game_dir)!r})\n"
            "import hashlib\n"
            "ENC = "
            + repr(enc_input)
            + "\nSAY = "
            + repr(say_input)
            + "\nUNIQ = "
            + repr(uniq_input)
            + "\n"
            + code
        )
        result = subprocess.run(
            [str(py), "-c", probe],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise RuntimeError("游戏内置 Ren'Py 黑盒执行失败")
        stdout = result.stdout
        marker = "__GOLD__"
        if marker not in stdout:
            raise RuntimeError("黑盒输出缺少 __GOLD__ 标记")
        payload = stdout.split(marker, 1)[1].strip()
        # 受控输入：游戏自带解释器输出，格式为 (enc_out, say_out, uniq_out, e2e_out)
        parsed = eval(payload)  # noqa: S307
        enc_out, say_out, uniq_out, e2e_out = parsed
        return (
            [(raw, out) for raw, out in enc_out],
            [(name, code) for name, code in say_out],
            [(label, digest, used, out) for label, digest, used, out in uniq_out],
            [(name, code, digest, id_) for name, code, digest, id_ in e2e_out],
        )
    finally:
        if use_junction and junction.exists():
            try:
                junction.rmdir()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 主检查流程
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sprint 3B 金标准：与游戏内置 Ren'Py 8.0.3 黑盒比对标识符算法。",
    )
    parser.add_argument(
        "--game",
        type=Path,
        default=GAME_DEFAULT,
        help="游戏根目录（含 renpy/ 与 lib/）。",
    )
    parser.add_argument(
        "--only-local",
        action="store_true",
        help="只跑本地静态向量检查，不调用游戏解释器。",
    )
    args = parser.parse_args(argv)

    print(f"项目根目录：{PROJECT_ROOT}")

    # 1) 本地静态检查
    print("\n[1/2] 本地静态向量检查（encode_say_string / say_get_code / dialogue_identifier）…")
    failures = run_local_checks()
    if failures:
        for f in failures:
            print(f"  FAIL {f}")
        print("本地静态检查失败")
        return 1
    print(
        f"  OK：{len(ENCODE_VECTORS)} 个编码向量、{len(SAY_CASES)} 个 get_code/标识符向量、"
        f"{len(UNIQUE_VECTORS)} 个冲突后缀向量全部匹配"
    )

    if args.only_local:
        print("\nGOLD STANDARD OK (local only)")
        return 0

    # 2) 游戏内置黑盒比对
    print(f"\n[2/2] 游戏内置 Ren'Py 黑盒比对（{args.game}）…")
    try:
        enc_out, say_out, uniq_out, e2e_out = run_gold(args.game)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"  跳过黑盒（无法初始化游戏解释器）：{e}")
        print("  提示：可用 --game 指定游戏目录，或 --only-local 只跑静态检查。")
        return 1

    # encode_say_string
    for (raw, expected), (g_raw, g_out) in zip(ENCODE_VECTORS, enc_out, strict=False):
        if raw != g_raw or expected != g_out:
            failures.append(f"encode_say_string 黑盒：{raw!r} → {g_out!r}，期望 {expected!r}")

    # Say.get_code
    say_cases_bb = [c for c in SAY_CASES if c[0] not in BLACKBOX_EXCLUDED]
    for (name, fields, expected_code, _eid), (g_name, g_code) in zip(
        say_cases_bb, say_out, strict=False
    ):
        if name != g_name:
            failures.append(f"黑盒 say 顺序错位：{name} vs {g_name}")
            continue
        if g_code != expected_code:
            failures.append(f"[{name}] 黑盒 get_code = {g_code!r}，期望 {expected_code!r}")
        # 本地 say_get_code 与黑盒直接比对
        unit = _unit(**fields)
        local_code = say_get_code(unit)
        if local_code != g_code:
            failures.append(f"[{name}] 本地 say_get_code ≠ 黑盒：{local_code!r} vs {g_code!r}")

    # unique_identifier 冲突后缀
    for (_label, _digest, _used, expected), (g_label, g_digest, g_used, g_out) in zip(
        UNIQUE_VECTORS, uniq_out, strict=False
    ):
        if g_out != expected:
            failures.append(
                f"黑盒 unique_identifier({g_label!r}, {g_digest!r}, used={g_used}) "
                f"= {g_out!r}，期望 {expected!r}"
            )

    # 端到端：本地 dialogue_identifier（自动路径） vs 黑盒组合
    for (name, fields, _ec, _eid), (g_name, g_code, g_digest, g_id) in zip(
        say_cases_bb, e2e_out, strict=False
    ):
        if name != g_name:
            failures.append(f"黑盒 e2e 顺序错位：{name} vs {g_name}")
            continue
        unit = _unit(**fields)
        local_id = dialogue_identifier(unit, unit.context, set())
        if local_id != g_id:
            failures.append(
                f"[{name}] 端到端标识符：本地 {local_id!r} vs 黑盒 {g_id!r}"
                f"（code={g_code!r}, digest={g_digest!r}）"
            )

    if failures:
        print("\n金标准检查失败：")
        for f in failures:
            print(f"  FAIL {f}")
        return 1

    print("  全部一致")
    print("\nGOLD STANDARD OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
