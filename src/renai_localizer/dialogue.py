"""Sprint 3B：对话翻译标识符复刻与对话翻译文件生成。

本模块精确复刻 Ren'Py 8.0.3 的对话翻译标识符算法与 tl 文件生成逻辑，
使生成的 ``translate <lang> <identifier>:`` 块标识符与游戏内一致。

对齐点（只读引用 ``F:\\SteamLibrary\\...\\ScarletHollow\\renpy\\``）：

- ``encode_say_string`` 复刻 ``renpy/translation/__init__.py`` 218–228 行：
  转义顺序固定不可调换（先 ``\\``→``\\\\``、真换行→``\\n``、
  ``"``→``\\"``、最后把「空格前的空格」变 ``\\ ``），再包双引号。
- ``say_get_code`` 复刻 ``renpy/ast.py`` 836–870 行 ``Say.get_code()``：
  按顺序拼接 who / attributes / ``@``+temporary_attributes /
  encode_say_string(what) / nointeract / id+标识符 / arguments /
  ``with``+表达式，空格连接。
- ``dialogue_identifier`` 复刻 ``renpy/translation/__init__.py``
  249–317 行 ``unique_identifier`` / ``create_translate``：
  ``md5((code + "\\r\\n").encode("utf-8")).hexdigest()[:8]``；有 label 时
  ``label.replace(".", "_") + "_" + digest``，否则直接用 digest；与
  已用标识符冲突时依次加 ``_1`` / ``_2``…；显式 ``id`` 子句整体替换
  标识符（不参与自动冲突后缀，与 Ren'Py 一致）。
- tl 块结构复刻 ``renpy/translation/generation.py`` 149–192 行
  ``write_translates``：

  .. code-block:: renpy

      # <源文件相对路径>:<行号>
      translate <lang> <identifier>:

          # <原始 get_code>
          <翻译后的 get_code>

直通模式（未提供 ``translator``）下翻译后文本 == 原文。
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from renai_localizer.models import ExtractionResult, TextKind, TranslationUnit


def encode_say_string(s: str) -> str:
    """精确复刻 Ren'Py 8.0.3 ``encode_say_string()``（translation/__init__.py 218–228 行）。

    转义顺序固定、不可调换：先 ``\\``→``\\\\``，再真换行→``\\n``，
    ``"``→``\\"``，最后把「空格前的空格」变 ``\\ ``（连续空格的第二个及
    之后各空格），最后包双引号。返回可直接放入 say 语句的字符串字面量。
    """
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    s = s.replace('"', '\\"')
    s = re.sub(r"(?<= ) ", "\\ ", s)
    return '"' + s + '"'


def say_get_code(unit: TranslationUnit, what: str | None = None) -> str:
    """重建 ``Say.get_code()``（renpy/ast.py 836–870 行）。

    ``what`` 缺省用 ``unit.text``（翻译标识符计算时即原文；写 tl 时传
    翻译后的文本）。字段拼接顺序与 Ren'Py 完全一致：

    ``who`` → ``attributes`` → ``@ temporary_attributes`` →
    ``encode_say_string(what)`` → ``nointeract`` → ``id <标识符>`` →
    ``arguments`` → ``with <表达式>``

    ``say_arguments`` 为原文（含外层括号），与 ``Arguments.get_code()``
    的输出一致（如 ``(test=1)``）。
    """
    rv: list[str] = []

    if unit.say_who:
        rv.append(unit.say_who)

    if unit.say_attributes:
        rv.extend(unit.say_attributes)

    if unit.say_temporary_attributes:
        rv.append("@")
        rv.extend(unit.say_temporary_attributes)

    rv.append(encode_say_string(unit.text if what is None else what))

    if unit.say_nointeract:
        rv.append("nointeract")

    if unit.say_id:
        rv.append("id")
        rv.append(unit.say_id)

    if unit.say_arguments:
        rv.append(unit.say_arguments)

    if unit.say_with:
        rv.append("with")
        rv.append(unit.say_with)

    return " ".join(rv)


def _base_identifier(label: str | None, digest: str) -> str:
    """``unique_identifier`` 的 base：有 label 时 ``label.replace(".", "_") + "_" + digest``。"""
    if label is None:
        return digest
    return label.replace(".", "_") + "_" + digest


def dialogue_identifier(
    unit: TranslationUnit,
    label: str | None,
    used_ids: set[str],
) -> str:
    """计算对白翻译标识符（复刻 ``unique_identifier`` / ``create_translate``）。

    1. ``code = say_get_code(unit)``（原文），
       ``digest = md5((code + "\\r\\n").encode("utf-8")).hexdigest()[:8]``；
    2. 无显式 ``id``：base 为 ``label.replace(".", "_") + "_" + digest``
       （label 为 ``None`` 时直接用 digest）；若 base 已在 ``used_ids`` 中，
       依次尝试 ``_1``、``_2``…直到不冲突；
    3. 有显式 ``id``：整体替换为 ``unit.say_id``（不参与自动冲突后缀，
       与 Ren'Py ``create_translate`` 一致），并记入 ``used_ids``。

    ``used_ids`` 为已分配标识符集合（全局共享，模拟 ``Restructurer``
    的 ``self.identifiers``）。
    """
    if unit.say_id is not None:
        used_ids.add(unit.say_id)
        return unit.say_id

    code = say_get_code(unit)
    digest = hashlib.md5((code + "\r\n").encode("utf-8")).hexdigest()[:8]
    base = _base_identifier(label, digest)

    identifier = base
    i = 0
    while identifier in used_ids:
        i += 1
        identifier = f"{base}_{i}"

    used_ids.add(identifier)
    return identifier


class Translator(Protocol):
    """翻译器接口：按 unit id 返回新文本（与 ``writer.Translator`` 一致）。

    直通模式下不提供该参数，翻译后文本 == 原文。
    """

    def translate(self, units: list[TranslationUnit]) -> dict[str, str]:
        """返回 ``{unit.id: 新文本}``；未覆盖的 id 使用原文（直通）。"""
        ...


def _iter_units(
    data: ExtractionResult | Iterable[TranslationUnit],
) -> Iterable[TranslationUnit]:
    """统一输入形态：``ExtractionResult`` 取其 ``units``，否则直接迭代。"""
    if isinstance(data, ExtractionResult):
        return data.units
    return data


def normalize_sources(
    data: ExtractionResult | Iterable[TranslationUnit],
) -> ExtractionResult | list[TranslationUnit]:
    """把绝对 ``source`` 规范化为相对源根目录的路径。

    对话通道按 ``unit.source`` 镜像输出目录结构；若 ``source`` 是绝对路径，
    pathlib 的 ``out_root / language / source`` 会丢弃前缀直接返回绝对路径，
    导致 tl 内容覆盖源文件。此函数将绝对 ``source`` 转为相对路径（相对
    ``ExtractionResult.source`` 所在目录，或单文件提取时的文件所在目录），
    保证输出始终落在输出根目录之下。

    返回与输入同类型的新对象（绝对 source 才重建；否则原样返回）。
    """
    units = list(_iter_units(data))
    source_root = None
    if isinstance(data, ExtractionResult):
        root = Path(data.source)
        if root.suffix.lower() == ".rpy" or (root.exists() and root.is_file()):
            root = root.parent
        source_root = root

    if not any(Path(u.source).is_absolute() for u in units):
        return data if isinstance(data, ExtractionResult) else units

    new_units: list[TranslationUnit] = []
    for u in units:
        p = Path(u.source)
        if p.is_absolute() and source_root is not None:
            rel = os.path.relpath(p, source_root)
            u = u.model_copy(update={"source": rel})
        new_units.append(u)
    if isinstance(data, ExtractionResult):
        return ExtractionResult(source=data.source, units=new_units)
    return new_units


def collect_dialogue_units(
    data: ExtractionResult | Iterable[TranslationUnit],
) -> list[TranslationUnit]:
    """收集对话翻译单元（仅 ``kind == DIALOGUE``），保持输入顺序。"""
    return [u for u in _iter_units(data) if u.kind == TextKind.DIALOGUE]


def group_by_source(units: Iterable[TranslationUnit]) -> list[tuple[str, list[TranslationUnit]]]:
    """按 ``unit.source`` 分组（保持首次出现顺序，组内保持原顺序）。

    用于镜像源目录结构生成各源文件对应的 tl 文件。
    """
    grouped: OrderedDict[str, list[TranslationUnit]] = OrderedDict()
    for u in units:
        grouped.setdefault(u.source, []).append(u)
    return list(grouped.items())


def build_dialogue_tl(
    units: Iterable[TranslationUnit],
    language: str,
    *,
    source_path: str,
    translator: Translator | None = None,
    label_of: dict[str, str | None] | None = None,
) -> str:
    """生成单个源文件对应的对话 tl 文本（``translate <lang> <identifier>:`` 块）。

    ``source_path`` 为源文件相对路径，写入块头注释
    ``# <source_path>:<行号>``。``label_of`` 为 ``{unit.id: label}`` 映射
    （缺省用 ``unit.context``）；``used_ids`` 由本函数内部维护，因此该
    文件内重复文本的冲突后缀与 Ren'Py 一致（同文件内按文档顺序）。

    tl 块结构（与 Ren'Py ``write_translates`` 一致）：

    .. code-block:: renpy

        # <source_path>:<行号>
        translate <lang> <identifier>:

            # <原始 get_code>
            <翻译后的 get_code>

    翻译行由 ``say_get_code(unit, new_what)`` 重建；直通模式下
    ``new_what == unit.text``（new code == 原 code）。
    """
    units = list(units)
    new_by_id: dict[str, str] = {}
    if translator is not None:
        new_by_id = translator.translate(units)

    used_ids: set[str] = set()
    lines: list[str] = []

    for unit in units:
        label = label_of.get(unit.id, unit.context) if label_of else unit.context
        identifier = dialogue_identifier(unit, label, used_ids)
        original_code = say_get_code(unit)
        new_what = new_by_id.get(unit.id, unit.text)
        translated_code = say_get_code(unit, new_what)

        lines.append(f"# {source_path}:{unit.line}")
        lines.append(f"translate {language} {identifier}:")
        lines.append("")
        lines.append(f"    # {original_code}")
        lines.append(f"    {translated_code}")
        lines.append("")

    return "\n".join(lines)


def write_dialogue_tl(
    output_dir: Path,
    language: str,
    data: ExtractionResult | Iterable[TranslationUnit],
    *,
    translator: Translator | None = None,
) -> list[Path]:
    """按源文件分组生成对话 tl 文件，写入 ``<output_dir>/<language>/<源文件相对路径>.rpy``。

    返回写入的文件路径列表。镜像源目录结构：源文件 ``scripts/day1.rpy``
    对应输出 ``<output_dir>/<language>/scripts/day1.rpy``。

    注意：Ren'Py 的 ``Restructurer.identifiers`` 是全局共享的，但本函数
    按文件分别调用 ``build_dialogue_tl`` 时会各自维护 ``used_ids``；如需
    跨文件全局去重（真实语料冒烟要求无重复标识符），请在调用前把同一
    源文件集合一次性传入，或使用 CLI（其按全部单元排序后逐文件构建）。
    见 ``build_dialogue_tl_all``。
    """
    paths: list[Path] = []
    # 只处理 DIALOGUE 单元（与 build_dialogue_tl_all 一致），并先归一化绝对 source。
    for source_path, file_units in group_by_source(
        collect_dialogue_units(normalize_sources(data))
    ):
        text = build_dialogue_tl(
            file_units,
            language,
            source_path=source_path,
            translator=translator,
        )
        target = output_dir / language / source_path
        if target.suffix != ".rpy":
            target = target.with_suffix(".rpy")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        paths.append(target)
    return paths


def build_dialogue_tl_all(
    data: ExtractionResult | Iterable[TranslationUnit],
    language: str,
    *,
    translator: Translator | None = None,
) -> dict[str, str]:
    """一次性为全部对话单元生成各源文件的 tl 文本（全局共享 ``used_ids``）。

    与 Ren'Py ``Restructurer``（全局单实例、identifiers 全局共享）语义
    一致：跨文件相同的自动标识符也按文档顺序追加 ``_1`` 后缀，保证生成
    结果无重复标识符。返回 ``{源文件相对路径: tl 文本}``。
    """
    units = collect_dialogue_units(normalize_sources(data))
    new_by_id: dict[str, str] = {}
    if translator is not None:
        new_by_id = translator.translate(units)

    used_ids: set[str] = set()
    out: dict[str, list[str]] = {}

    for unit in units:
        label = unit.context
        identifier = dialogue_identifier(unit, label, used_ids)
        original_code = say_get_code(unit)
        new_what = new_by_id.get(unit.id, unit.text)
        translated_code = say_get_code(unit, new_what)

        lines = out.setdefault(unit.source, [])
        lines.append(f"# {unit.source}:{unit.line}")
        lines.append(f"translate {language} {identifier}:")
        lines.append("")
        lines.append(f"    # {original_code}")
        lines.append(f"    {translated_code}")
        lines.append("")

    return {source_path: "\n".join(lines) for source_path, lines in out.items()}
