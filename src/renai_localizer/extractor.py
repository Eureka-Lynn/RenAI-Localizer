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
- 资源引用语句跳过：``shader "..."`` / ``font "..."`` / ``voice "..."``
  是资源路径 / 音频引用，不是可翻译文本
- 空文本过滤：提取结果中空串 / 纯空白的单元一律丢弃（兜底）

文本值保真（Sprint 3.5）：提取出的 ``TranslationUnit.text`` 等于 Ren'Py
运行时（lexed / Python 求值后）的规范文本值，与 ``renpy/parser.py``
``Lexer.string()`` / ``Lexer.triple_string()`` 及 Python 字符串字面量语义
一致（详见 ``_unescape_say`` / ``_unescape_python`` / ``_unescape_triple``
的 docstring），确保后续生成的翻译标识符（MD5）与游戏内一致。

暂不支持（见 README「已知限制」）：

- ``python`` 块 / ``$`` 语句内的字符串
- ``define`` / ``default`` 中的裸字符串（未用 ``_()`` / ``__()`` 标记）
- ``_p()`` / ``___()`` 标记的字符串（后续 Sprint）
- raw 字符串（``r"..."``）与三引号对白中的 monologue 分段
- 字符串拼接求值、翻译标识符生成、文本去重
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit

# say 语句起始：可选 say 变体 + 可选说话者 + 字符串字面量起始。
# 注意变体（nvl centered / centered / nvl）优先匹配，避免把 centered / nvl 误认为 speaker。
_SAY_START_RE = re.compile(
    r"^\s*(?:(?P<variant>nvl centered|centered|nvl)\s+)?"
    r"(?:(?P<speaker>[A-Za-z_]\w*)\s+)?"
    r'(?P<quote>"""|\'\'\'|"|\')'
)

# 对白续写：``extend "..."``。extend 不是说话者，续写内容归属于当前
# 说话者（speaker 为 None），尾部子句处理与普通 say 一致。
_EXTEND_START_RE = re.compile(r'^\s*extend\s+(?P<quote>"""|\'\'\'|"|\')')

# 资源引用语句：``shader "..."`` / ``font "..."`` / ``voice "..."`` 是
# 资源路径 / 音频引用，不是可翻译文本，必须整体跳过（含可选跨行三引号，
# 但资源引用通常为单行短路径）。
_RESOURCE_STMT_RE = re.compile(r"^\s*(?:shader|font|voice)\s+")

# say 语句尾部（字符串闭合之后）：条件括号 / id 子句 / with 子句 / 注释。
# id 子句的内容不进入提取文本，仅用于 Ren'Py 的翻译标识。
_SAY_TAIL_RE = re.compile(
    r"(?:\s*\([^)]*\))?(?:\s+id\s+[\w.:]+:?)?(?:\s+with\s+[\w.]+)?\s*(?:#.*)?$"
)

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


@dataclass(frozen=True)
class _SayMatch:
    """一条 say 语句的匹配结果。"""

    text: str
    speaker: str | None
    last_index: int
    valid_tail: bool


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

            # 资源引用语句（shader / font / voice）：整行跳过。
            # 注意：style 块内的属性（缩进）与 transform 内的 shader 都在此匹配。
            if _RESOURCE_STMT_RE.match(stripped):
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

        续写归属于当前说话者（speaker 为 ``None``），尾部 ``id`` / ``with`` /
        注释与普通 say 一致处理。
        """
        m = _EXTEND_START_RE.match(raw)
        if m is None:
            return None
        lit = _match_string_literal(lines, index, m.start("quote"))
        if lit is None:
            return None
        text, last, after, multi = lit
        rest = lines[last][after:]
        valid_tail = _SAY_TAIL_RE.match(rest) is not None
        unescaped = _unescape_triple(text) if multi else _unescape_say(text)
        return _SayMatch(
            text=unescaped,
            speaker=None,
            last_index=last,
            valid_tail=valid_tail,
        )

    def _match_say(self, raw: str, index: int, lines: list[str]) -> _SayMatch | None:
        """匹配一行 say 语句（含变体、id 子句、跨行三引号）。"""
        # extend / shader / font / voice 等关键字开头由前置分支拦截，
        # 这里无需重复处理；_SAY_START_RE 只匹配合法说话者。
        m = _SAY_START_RE.match(raw)
        if m is None:
            return None
        speaker = m.group("speaker")
        lit = _match_string_literal(lines, index, m.start("quote"))
        if lit is None:
            return None
        text, last, after, multi = lit
        rest = lines[last][after:]
        valid_tail = _SAY_TAIL_RE.match(rest) is not None
        unescaped = _unescape_triple(text) if multi else _unescape_say(text)
        return _SayMatch(
            text=unescaped,
            speaker=speaker,
            last_index=last,
            valid_tail=valid_tail,
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
        )
