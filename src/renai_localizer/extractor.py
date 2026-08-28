"""Ren'Py ``.rpy`` 脚本文本提取器。

支持的语法（Sprint 3）：

- 对白（say 语句）：``e "Hello"`` / ``"Narrator"`` / ``e 'Hi'``
- say 变体：``centered "..."`` / ``nvl "..."`` / ``nvl centered "..."``
- say 语句的 ``id`` 子句：``e "text" id start_xxx:``（id 不进入文本）
- 对白续写：``extend "..."``（speaker 为 ``None``，空文本不产出单元；
  尾部 ``id`` / ``with`` / 注释与普通 say 一致处理）
- 三引号多行字符串：``e \"\"\"第一行\\n第二行\"\"\"``（``line`` 记录起始行）
- 单引号字符串（含 ``\\'`` 转义），与双引号同等处理
- 菜单选项（menu 块）：``"Choice":`` / ``"Choice" if cond:`` / 单引号变体
- 可翻译字符串标记：``_("...")`` / ``__("...")``（``kind="string"``，
  常见于 ``define`` / ``default`` 中的角色名与界面文本）
- Ren'Py 保留语句关键字拦截（镜像 ``renpy/parser.py`` 的语句分发）：
  ``play`` / ``queue`` / ``stop`` / ``show`` / ``scene`` / ``camera`` /
  ``window`` / ``voice`` / ``shader`` / ``font`` 开头的行是语句，关键字后
  可跟字符串字面量但不是对白（``play music "x"`` / ``show text "..."`` /
  ``scene "..."`` / ``voice "..."``），整行跳过
- ``image`` / ``transform`` / ``style`` 块（以冒号结尾的定义行）内不存在
  say 语句：ATL 行与样式属性（``color "#000"`` / ``thumb "..."`` /
  ``background "..."`` 等）不是可翻译文本，块内统一跳过（含 ``_()`` 标记，
  此类块内通常没有标记字符串）；单行 ``image x = ...`` / ``style x is y``
  不受影响
- 空文本过滤：提取结果中空串 / 纯空白的单元一律丢弃（兜底）

文本值保真（Sprint 3.5）：提取出的 ``TranslationUnit.text`` 等于 Ren'Py
运行时（lexed / Python 求值后）的规范文本值，与 ``renpy/parser.py``
``Lexer.string()`` / ``Lexer.triple_string()`` 及 Python 字符串字面量语义
一致（详见 ``_unescape_say`` / ``_unescape_python`` / ``_unescape_triple``
的 docstring），确保后续生成的翻译标识符（MD5）与游戏内一致。

say 语句结构字段（Sprint 3B）：``say_who`` / ``say_attributes`` /
``say_temporary_attributes`` / ``say_with`` / ``say_arguments`` /
``say_nointeract`` / ``say_id`` 完整解析并填充，与 Ren'Py ``ast.Say``
各属性一一对应，供 ``dialogue.say_get_code()`` 精确重建 ``Say.get_code()``：

- ``centered "x"`` → say_who="centered"；``nvl "x"`` → say_who="nvl"；
  ``nvl centered "x"`` → say_who="nvl" + say_attributes=("centered",)
- ``e "x" with Dissolve(0.5, alpha=True)`` → say_with="Dissolve(0.5, alpha=True)"
- ``e "x" (test=1)`` → say_arguments="(test=1)"
- ``e "x" nointeract`` → say_nointeract=True
- ``e "x" id custom_abc`` → say_id="custom_abc"

``speaker`` 字段保持既有语义（叙述 / ``centered`` / ``nvl`` / ``extend``
均为 ``None``），与 Sprint 2/3/3.5 测试一致。

暂不支持（见 README「已知限制」）：

- ``python`` 块 / ``$`` 语句内的字符串
- ``define`` / ``default`` 中的裸字符串（未用 ``_()`` / ``__()`` 标记）
- ``_p()`` / ``___()`` 标记的字符串（后续 Sprint）
- raw 字符串（``r"..."``）与三引号对白中的 monologue 分段
- 字符串拼接求值、翻译标识符生成（Sprint 3B 由 ``dialogue`` 模块负责）、文本去重
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit

# who 表达式起始：简单表达式（允许点号，如 m.e），对应 Ren'Py
# ``Lexer.say_expression()`` 常见形态（完整 simple_expression 的复杂形态
# 不在语料中，继续列入已知限制）。
_SAY_WHO_RE = re.compile(r"[A-Za-z_][\w.]*")

# say 属性组件：可带 ``-`` 前缀，对应 ``image_name_component`` 语义。
_SAY_ATTR_RE = re.compile(r"-?[\w.]+")

# 对白续写：``extend "..."``。extend 不是说话者，续写内容归属于当前
# 说话者（speaker 为 None），尾部子句处理与普通 say 一致。
_EXTEND_START_RE = re.compile(r'^\s*extend\s+(?P<quote>"""|\'\'\'|"|\')')

# Ren'Py 保留语句关键字（镜像 ``renpy/parser.py`` 的语句分发）：这些关键字
# 开头的行是语句，关键字后可跟字符串字面量（``play music "x"`` /
# ``show text "..."`` / ``voice "..."``），但不是对白，必须整体跳过。
# 这些关键字是 Ren'Py 保留字，不能用作说话者 / 变量名，因此 ``\\b`` 词
# 边界后拦截整行是安全的（``show_foo`` 这类标识符不命中）。
_STATEMENT_KEYWORD_RE = re.compile(
    r"^\s*(?:play|queue|stop|show|scene|camera|window|voice|shader|font)\b"
)

# image / transform / style 块：以冒号结尾的定义行（``image bg fire:`` /
# ``transform flip:`` / ``style default:``）进入块状态，块内 ATL 行与样式
# 属性不是对白，统一跳过。``image x = ...`` / ``style x is y`` 这类无冒号
# 的单行定义不受影响。
_ATL_BLOCK_START_RE = re.compile(r"^\s*(?:image|transform|style)\b.*:\s*(?:#.*)?$")

# 菜单选项：支持单引号 / 双引号，以及 "if 条件" / "(条件)" 变体。
_MENU_CHOICE_RE = re.compile(
    r"^\s*(?P<quote>\"|\')(?P<text>(?:\\.|(?!(?P=quote))[^\\])*)(?P=quote)"
    r"(?:\s*(?:\([^)]*\)|\bif\b.*))?\s*:\s*(?:#.*)?$"
)

_MENU_START_RE = re.compile(r"^\s*menu\s*:\s*(?:#.*)?$")
_LABEL_RE = re.compile(r"^\s*label\s+(?P<name>[\w.]+)\s*:")
_SCREEN_START_RE = re.compile(r"^\s*screen\s+[\w.]+\s*\(.*\)\s*:\s*(?:#.*)?$")
# python 块（含 init 优先级前缀变体，如 `init -1500 python:`），块内字符串一律不提取。
_PYTHON_BLOCK_RE = re.compile(r"^\s*(?:init\b.*?)?python\b.*:\s*(?:#.*)?$")

# 可翻译字符串标记：_("...") / __("...")。
# 负向后顾 / (?!_) 排除 _p( / ___( 等其它下划线前缀函数（不属于本 Sprint 范围）。
_MARKED_OPEN_RE = re.compile(r"(?<![A-Za-z0-9_])__(?=\s*\()|(?<![A-Za-z0-9_])_(?!_)(?=\s*\()")

# 单行 say 字符串：连续空白（\s+）折叠为单个空格（Lexer.string 语义）。
_SAY_WHITESPACE_RE = re.compile(r"\s+")

# say / 菜单选项字符串 dequote：\uXXXX → 对应字符，其它 \x → x（去反斜杠）。
_SAY_DEQUOTE_RE = re.compile(r"\\(?:u[0-9a-fA-F]{4}|.)")

# Python 字符串转义（_() / __()）：匹配一条完整转义，供逐条按 Python 规则解码。
_PY_ESCAPE_RE = re.compile(
    r"\\(?:N\{[^}]*\}|U[0-9a-fA-F]{8}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}"
    r"|[0-7]{1,3}|.)"
)


def _indent(line: str) -> int:
    """返回行首缩进字符数（空格与制表符各计 1）。"""
    return len(line) - len(line.lstrip(" \t"))


def _skip_ws(s: str, pos: int) -> int:
    """跳过空格与制表符，返回新位置。"""
    while pos < len(s) and s[pos] in " \t":
        pos += 1
    return pos


def _is_word_char(s: str, i: int) -> bool:
    """``s[i]`` 是否属于词字符（用于关键字边界判断，防止 ``with_foo`` 误命中 ``with``）。"""
    return i < len(s) and (s[i].isalnum() or s[i] in "_.")


def _unescape_say(content: str) -> str:
    """还原 say / 菜单选项字符串（``Lexer.string()`` 语义）。

    处理顺序必须与 Ren'Py ``renpy/parser.py`` 一致：先折叠单行内连续空白
    （``\\s+`` → 单个空格），再 dequote：

    - ``\\n`` → 换行符
    - ``\\{`` → ``{{``（字面量花括号，避免被解释为文本标签）
    - ``\\[`` → ``[[``（字面量方括号，避免被解释为插值）
    - ``\\%`` → ``%%``（字面量百分号，避免被解释为字符串格式化）
    - ``\\uXXXX`` → 对应字符
    - 其它 ``\\x`` → ``x``（去掉反斜杠保留字符本身）

    ``content`` 为未还原转义的原始字面量内容（不含两端引号）。
    """
    folded = _SAY_WHITESPACE_RE.sub(" ", content)
    return _SAY_DEQUOTE_RE.sub(_say_dequote, folded)


def _say_dequote(m: re.Match[str]) -> str:
    """``Lexer.string()`` dequote 回调：``\\x`` / ``\\uXXXX`` → 对应文本。"""
    esc = m.group(0)
    body = esc[1:]
    if body.startswith("u") and len(body) == 5:
        return chr(int(body[1:], 16))
    mapping = {"n": "\n", "{": "{{", "[": "[[", "%": "%%"}
    return mapping.get(body, body)


_PY_ESCAPES = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\a": "\a",
    "\\b": "\b",
    "\\f": "\f",
    "\\v": "\v",
    "\\\\": "\\",
    "\\'": "'",
    '\\"': '"',
}


def _py_dequote(m: re.Match[str]) -> str:
    """Python 字符串转义还原（``_()`` / ``__()`` 按 Python 求值）。"""
    esc = m.group(0)
    if esc in _PY_ESCAPES:
        return _PY_ESCAPES[esc]
    body = esc[1:]
    if body.startswith("x") and len(body) == 3:
        return chr(int(body[1:], 16))
    if body.startswith("u") and len(body) == 5:
        return chr(int(body[1:], 16))
    if body.startswith("U") and len(body) == 9:
        return chr(int(body[1:], 16))
    if body.startswith("N{") and body.endswith("}"):
        name = body[2:-1]
        try:
            return unicodedata.lookup(name)
        except KeyError:
            return esc
    if body[0].isdigit():
        # 八进制 \0..\377：仅接受不超过 255 的值，越界原样保留。
        code = int(body, 8)
        if code <= 0xFF:
            return chr(code)
        return esc
    # 未知转义（如 \{\} \. \s）：Python 原样保留反斜杠与字符。
    return esc


def _unescape_python(content: str) -> str:
    """还原 Python 字符串转义（``_()`` / ``__()`` 的实参）。

    按 Python 字符串字面量规则求值：``\\n`` / ``\\t`` / ``\\\\`` / ``\\\"`` /
    ``\\'`` / ``\\r\\a\\b\\f\\v`` / ``\\0``（八进制）/ ``\\x\\u\\U\\N``；
    未知转义（如 ``\\{``）原样保留。
    """
    return _PY_ESCAPE_RE.sub(_py_dequote, content)


def _unescape_triple(content: str) -> str:
    """还原 say 三引号字符串（``Lexer.triple_string()`` 语义，不含 monologue）。

    跨行内容按行保留换行；对每个换行去掉两侧水平空白（`` *\\n *`` → ``\\n``）。
    当前不额外实现 monologue 分段（语料无此场景，列入已知限制）。
    """
    return re.sub(r"[ \t]*\n[ \t]*", "\n", content)


def _match_string_literal(
    lines: list[str], index: int, pos: int
) -> tuple[str, int, int, bool] | None:
    """从 ``lines[index][pos:]`` 解析一个 Ren'Py 字符串字面量。

    支持 ``"``、``'`` 以及三引号 ``\"\"\"`` / ``\'\'\'``（三引号可跨行，
    跨行内容保留换行）。

    返回 ``(text, last_index, after_pos, multi)``：

    - ``text``：去掉两端引号、尚未还原转义的原始内容
    - ``last_index``：闭合引号所在行的索引
    - ``after_pos``：闭合引号之后第一个字符的列位置
    - ``multi``：是否为三引号字符串

    ``pos`` 处不是合法字符串起始时返回 ``None``。
    """
    line = lines[index]
    tail = line[pos:]
    quote: str | None = None
    for candidate in ('"""', "'''", '"', "'"):
        if tail.startswith(candidate):
            quote = candidate
            break
    if quote is None:
        return None

    multi = len(quote) == 3
    parts: list[str] = []
    cur = index
    scan_from = pos + len(quote)

    while True:
        text_part = lines[cur]
        i = scan_from
        n = len(text_part)
        close = -1
        while i < n:
            ch = text_part[i]
            if ch == "\\":
                i += 2
                continue
            if text_part.startswith(quote, i):
                close = i
                break
            i += 1
        if close >= 0:
            parts.append(text_part[scan_from:close])
            return "\n".join(parts), cur, close + len(quote), multi
        parts.append(text_part[scan_from:])
        if not multi:
            # 普通字符串不允许跨行：视为该行不是合法字符串。
            return None
        cur += 1
        if cur >= len(lines):
            # 文件结束仍未闭合：按已收集内容处理（宽松容错）。
            return "\n".join(parts), cur - 1, len(lines[cur - 1]), multi
        scan_from = 0


def _read_balanced_parens(s: str, pos: int) -> tuple[str | None, int]:
    """从 ``s[pos] == '('`` 读取到配对的 ``)``。

    返回 ``(原文, 结束位置)``；未闭合时返回 ``(None, pos)``。
    """
    depth = 0
    q = pos
    while q < len(s):
        ch = s[q]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[pos : q + 1], q + 1
        q += 1
    return None, pos


def _read_simple_expression(s: str, pos: int) -> tuple[str | None, int]:
    """读取一个简单表达式（``with`` 子句实参，如 ``dissolve`` / ``Dissolve(0.5, alpha=True)``）。

    返回 ``(原文, 结束位置)``；无法解析时返回 ``(None, pos)``。
    """
    pos = _skip_ws(s, pos)
    m = _SAY_WHO_RE.match(s, pos)
    if m is None:
        return None, pos
    # ``m.end()`` 返回绝对位置（相对整个 ``s``），不能再加 ``pos``。
    end = m.end()
    p = _skip_ws(s, end)
    if s.startswith("(", p):
        args, p2 = _read_balanced_parens(s, p)
        if args is None:
            return None, pos
        end = p2
    return s[pos:end], end


def _read_id(s: str, pos: int) -> tuple[str | None, int]:
    """读取 ``id`` 子句的标识符（``[\\w.:]+``，允许行尾冒号）。

    返回 ``(标识符, 结束位置)``；无法解析时返回 ``(None, pos)``。
    """
    pos = _skip_ws(s, pos)
    m = re.match(r"[A-Za-z_][\w.:]*", s[pos:])
    if m is None:
        return None, pos
    name = m.group(0)
    end = pos + m.end()
    if name.endswith(":"):
        name = name[:-1]
    return name, end


@dataclass(frozen=True)
class _SayTail:
    """say 尾部子句的解析结果（对应 ``finish_say`` 的循环产物）。"""

    nointeract: bool = False
    with_expr: str | None = None
    arguments: str | None = None
    identifier: str | None = None


def _parse_say_tail(rest: str) -> _SayTail | None:
    """解析 say 字符串闭合之后的尾部子句（模拟 ``finish_say`` 循环）。

    支持按任意顺序出现的 ``nointeract`` / ``with <expr>`` / ``id <name>`` /
    ``(<arguments>)`` 子句，其后可跟行尾注释；重复子句或出现其它 token
    视为非法尾部（返回 ``None``）。
    """
    pos = 0
    n = len(rest)
    nointeract = False
    with_expr: str | None = None
    arguments: str | None = None
    identifier: str | None = None

    while True:
        pos = _skip_ws(rest, pos)
        if pos >= n or rest[pos] == "#":
            break

        if rest.startswith("nointeract", pos) and not _is_word_char(rest, pos + len("nointeract")):
            nointeract = True
            pos += len("nointeract")
            continue

        if rest.startswith("with", pos) and not _is_word_char(rest, pos + len("with")):
            if with_expr is not None:
                return None
            pos += len("with")
            expr, pos = _read_simple_expression(rest, pos)
            if expr is None:
                return None
            with_expr = expr
            continue

        if rest.startswith("id", pos) and not _is_word_char(rest, pos + len("id")):
            if identifier is not None:
                return None
            pos += len("id")
            name, pos = _read_id(rest, pos)
            if name is None:
                return None
            identifier = name
            continue

        if rest[pos] == "(":
            if arguments is not None:
                return None
            args, pos = _read_balanced_parens(rest, pos)
            if args is None:
                return None
            arguments = args
            continue

        return None

    return _SayTail(
        nointeract=nointeract,
        with_expr=with_expr,
        arguments=arguments,
        identifier=identifier,
    )


@dataclass(frozen=True)
class _SayMatch:
    """一条 say 语句的匹配结果（含 Sprint 3B 的 say 结构字段）。"""

    text: str
    speaker: str | None
    last_index: int
    valid_tail: bool
    say_who: str | None = None
    say_attributes: tuple[str, ...] | None = None
    say_temporary_attributes: tuple[str, ...] | None = None
    say_with: str | None = None
    say_arguments: str | None = None
    say_nointeract: bool = False
    say_id: str | None = None


class RpyExtractor:
    """从 Ren'Py 脚本文本中提取待翻译文本。"""

    def extract(self, text: str, *, source: str = "<memory>") -> ExtractionResult:
        """从脚本内容中提取文本单元。"""
        units: list[TranslationUnit] = []
        counters: dict[str, int] = {}
        lines = text.splitlines()

        current_label: str | None = None
        menu_indents: list[int] = []
        python_indent: int | None = None
        screen_indent: int | None = None
        atl_indent: int | None = None

        i = 0
        total = len(lines)
        while i < total:
            raw = lines[i]
            stripped = raw.strip()
            indent = _indent(raw)
            line_no = i + 1

            # 空行与注释不影响 python 块 / screen 块边界判断
            # （块内空行的 indent 可能为 0，不能据此误判块已结束）。
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            # python 块：跳过块内所有行，直到遇到缩进回退的非空非注释行。
            if python_indent is not None:
                if indent <= python_indent:
                    python_indent = None
                else:
                    i += 1
                    continue

            # screen 块：块内不存在 say 语句（只有界面组件），但 _() 标记文本仍要提取。
            if screen_indent is not None:
                if indent <= screen_indent:
                    screen_indent = None
                else:
                    # 仍在 screen 块内：只处理 _()/__() 标记，不匹配 say。
                    marked = self._collect_marked(raw, i, lines, source, counters)
                    if marked is not None:
                        marked_units, last = marked
                        units.extend(marked_units)
                        i = last + 1
                    else:
                        i += 1
                    continue

            # ATL 块（image/transform/style）：块内不存在 say 语句（ATL 行、
            # 样式属性字符串不是对白），统一跳过（含 _()/__() 标记；此类块内
            # 通常没有标记字符串）。
            if atl_indent is not None:
                if indent <= atl_indent:
                    atl_indent = None
                else:
                    i += 1
                    continue

            # $ 语句（含行尾 \ 的续行）整体跳过。
            if stripped.startswith("$"):
                i += 1
                while i < total and lines[i].rstrip().endswith("\\"):
                    i += 1
                continue

            if _PYTHON_BLOCK_RE.match(stripped):
                python_indent = indent
                i += 1
                continue

            # 缩进回退到 menu 层级或以上时，退出已结束的 menu 块。
            while menu_indents and indent <= menu_indents[-1]:
                menu_indents.pop()

            if _SCREEN_START_RE.match(stripped):
                screen_indent = indent
                i += 1
                continue

            # image/transform/style 块入口：以冒号结尾的定义行进入块状态。
            # 单行 image x = ... / style x is y（无冒号）不受影响。
            if _ATL_BLOCK_START_RE.match(raw):
                atl_indent = indent
                i += 1
                continue

            label_match = _LABEL_RE.match(raw)
            if label_match:
                current_label = label_match.group("name")
                i += 1
                continue

            if _MENU_START_RE.match(raw):
                menu_indents.append(indent)
                i += 1
                continue

            if menu_indents:
                choice_match = _MENU_CHOICE_RE.match(raw)
                if choice_match:
                    units.append(
                        self._make_unit(
                            counters,
                            kind=TextKind.MENU_CHOICE,
                            text=_unescape_say(choice_match.group("text")),
                            line=line_no,
                            source=source,
                            speaker=None,
                            context=current_label,
                        )
                    )
                    i += 1
                    continue

            # 保留语句关键字（play/queue/stop/show/scene/camera/window 及
            # voice/shader/font）：这些关键字开头的行是 Ren'Py 语句（镜像
            # parser.py 的语句分发），关键字后可跟字符串字面量但不是对白。
            if _STATEMENT_KEYWORD_RE.match(stripped):
                i += 1
                continue

            marked = self._collect_marked(raw, i, lines, source, counters)
            if marked is not None:
                marked_units, last = marked
                units.extend(marked_units)
                i = last + 1
                continue

            # 对白续写：extend "..."，speaker 为 None。
            # 空文本（extend ""）不产出单元。
            extend = self._match_extend(raw, i, lines)
            if extend is not None:
                if extend.valid_tail and extend.text.strip():
                    units.append(
                        self._make_unit(
                            counters,
                            kind=TextKind.DIALOGUE,
                            text=extend.text,
                            line=line_no,
                            source=source,
                            speaker=None,
                            context=current_label,
                            say_who=extend.say_who,
                            say_attributes=extend.say_attributes,
                            say_temporary_attributes=extend.say_temporary_attributes,
                            say_with=extend.say_with,
                            say_arguments=extend.say_arguments,
                            say_nointeract=extend.say_nointeract,
                            say_id=extend.say_id,
                        )
                    )
                i = extend.last_index + 1
                continue

            say = self._match_say(raw, i, lines)
            if say is not None:
                if say.valid_tail and say.text.strip():
                    units.append(
                        self._make_unit(
                            counters,
                            kind=TextKind.DIALOGUE,
                            text=say.text,
                            line=line_no,
                            source=source,
                            speaker=say.speaker,
                            context=current_label,
                            say_who=say.say_who,
                            say_attributes=say.say_attributes,
                            say_temporary_attributes=say.say_temporary_attributes,
                            say_with=say.say_with,
                            say_arguments=say.say_arguments,
                            say_nointeract=say.say_nointeract,
                            say_id=say.say_id,
                        )
                    )
                i = say.last_index + 1
                continue

            i += 1

        # 兜底：丢弃空串 / 纯空白单元（覆盖 ""、_("") 等场景）。
        units = [u for u in units if u.text.strip()]

        return ExtractionResult(source=source, units=units)

    def extract_file(self, path: str | Path, *, encoding: str = "utf-8") -> ExtractionResult:
        """读取 ``.rpy`` 文件并提取文本单元。"""
        file_path = Path(path)
        text = file_path.read_text(encoding=encoding)
        return self.extract(text, source=str(file_path))

    def _match_extend(self, raw: str, index: int, lines: list[str]) -> _SayMatch | None:
        """匹配一行对白续写 ``extend "..."``。

        续写归属于当前说话者（speaker 为 ``None``），``say_who`` 为
        ``"extend"``；尾部 ``nointeract`` / ``with`` / ``id`` / 参数 / 注释
        与普通 say 一致处理。
        """
        m = _EXTEND_START_RE.match(raw)
        if m is None:
            return None
        lit = _match_string_literal(lines, index, m.start("quote"))
        if lit is None:
            return None
        text, last, after, multi = lit
        tail = _parse_say_tail(lines[last][after:])
        unescaped = _unescape_triple(text) if multi else _unescape_say(text)
        return _SayMatch(
            text=unescaped,
            speaker=None,
            last_index=last,
            valid_tail=tail is not None,
            say_who="extend",
            say_with=tail.with_expr if tail is not None else None,
            say_arguments=tail.arguments if tail is not None else None,
            say_nointeract=tail.nointeract if tail is not None else False,
            say_id=tail.identifier if tail is not None else None,
        )

    def _match_say(self, raw: str, index: int, lines: list[str]) -> _SayMatch | None:
        """匹配一行 say 语句（含变体、属性、id 子句、跨行三引号）。

        who / 属性 / 临时属性的解析与 Ren'Py ``say_statement`` 一致：
        第一个表达式词是 who（``centered`` / ``nvl`` 变体同样作为 who），
        其后连续的属性组件（``say_attributes``），``@`` 后为临时属性
        （``say_temporary_attributes``），再匹配字符串字面量与尾部子句。
        """
        # extend / play / queue / stop / show / scene / camera / window /
        # voice / shader / font 等保留语句关键字开头由前置分支拦截，
        # 这里无需重复处理。
        pos = _indent(raw)
        rest = raw[pos:]

        who: str | None = None
        attrs: tuple[str, ...] | None = None
        temp_attrs: tuple[str, ...] | None = None
        lit_pos = pos

        who_m = _SAY_WHO_RE.match(rest)
        if who_m is not None:
            who = who_m.group(0)
            p = _skip_ws(rest, who_m.end())
            attr_list: list[str] = []
            while not rest.startswith(('"""', "'''", '"', "'"), p):
                am = _SAY_ATTR_RE.match(rest, p)
                if am is None:
                    break
                attr_list.append(am.group(0))
                p = _skip_ws(rest, am.end())
            if attr_list:
                attrs = tuple(attr_list)
            # @ 临时属性（在字符串之前，如 e @ flash "x"）。
            if rest.startswith("@", p):
                p += 1
                tmp: list[str] = []
                p = _skip_ws(rest, p)
                while not rest.startswith(('"""', "'''", '"', "'"), p):
                    am = _SAY_ATTR_RE.match(rest, p)
                    if am is None:
                        break
                    tmp.append(am.group(0))
                    p = _skip_ws(rest, am.end())
                if tmp:
                    temp_attrs = tuple(tmp)
            # ``p`` 是相对于 ``rest`` 子串的位置，``_match_string_literal``
            # 需要绝对列位置，必须加上缩进 ``pos`` 换算。
            lit_pos = pos + p
        # else：无 who，单参数叙述 say（"..."）。

        lit = _match_string_literal(lines, index, lit_pos)
        if lit is None:
            return None
        text, last, after, multi = lit
        tail = _parse_say_tail(lines[last][after:])
        unescaped = _unescape_triple(text) if multi else _unescape_say(text)

        # speaker 保持既有语义：叙述与 centered/nvl 变体均为 None。
        speaker = None if who in (None, "centered", "nvl") else who
        return _SayMatch(
            text=unescaped,
            speaker=speaker,
            last_index=last,
            valid_tail=tail is not None,
            say_who=who,
            say_attributes=attrs,
            say_temporary_attributes=temp_attrs,
            say_with=tail.with_expr if tail is not None else None,
            say_arguments=tail.arguments if tail is not None else None,
            say_nointeract=tail.nointeract if tail is not None else False,
            say_id=tail.identifier if tail is not None else None,
        )

    def _collect_marked(
        self,
        raw: str,
        index: int,
        lines: list[str],
        source: str,
        counters: dict[str, int],
    ) -> tuple[list[TranslationUnit], int] | None:
        """收集一行（及跨行）中所有 ``_()`` / ``__()`` 标记字符串。

        返回 ``(units, last_index)``，其中 ``last_index`` 为最后消费行的索引。
        该行没有标记字符串时返回 ``None``。
        """
        units: list[TranslationUnit] = []
        cur = index
        cur_line = raw
        pos = 0
        while True:
            m = _MARKED_OPEN_RE.search(cur_line, pos)
            if m is None:
                break
            paren = cur_line.find("(", m.start())
            if paren < 0:
                break
            scan = paren + 1
            while scan < len(cur_line) and cur_line[scan].isspace():
                scan += 1
            lit = _match_string_literal(lines, cur, scan)
            if lit is None:
                pos = paren + 1
                continue
            text, last, after, multi = lit
            unescaped = _unescape_triple(text) if multi else _unescape_python(text)
            units.append(
                self._make_unit(
                    counters,
                    kind=TextKind.STRING,
                    text=unescaped,
                    line=index + 1,
                    source=source,
                    speaker=None,
                    context=None,
                )
            )
            cur = last
            cur_line = lines[cur]
            pos = after
        if not units:
            return None
        return units, cur

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
        say_who: str | None = None,
        say_attributes: tuple[str, ...] | None = None,
        say_temporary_attributes: tuple[str, ...] | None = None,
        say_with: str | None = None,
        say_arguments: str | None = None,
        say_nointeract: bool = False,
        say_id: str | None = None,
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
            say_who=say_who,
            say_attributes=say_attributes,
            say_temporary_attributes=say_temporary_attributes,
            say_with=say_with,
            say_arguments=say_arguments,
            say_nointeract=say_nointeract,
            say_id=say_id,
        )
