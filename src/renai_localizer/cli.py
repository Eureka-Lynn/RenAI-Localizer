"""RenAI Localizer 命令行入口。"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from renai_localizer import __version__
from renai_localizer.dialogue import (
    build_dialogue_tl_all,
    collect_dialogue_units,
    normalize_sources,
)
from renai_localizer.extractor import RpyExtractor
from renai_localizer.models import ExtractionResult, TranslationUnit
from renai_localizer.writer import collect_string_entries, write_strings_tl

app = typer.Typer(
    help="RenAI Localizer — 本地化任意 Ren'Py 游戏的 AI 工具。",
    no_args_is_help=True,
)

# Windows 终端（如 cmd.exe）默认使用 GBK 编码，直接输出中文会乱码。
# 将标准输出/错误重配置为 UTF-8，保证跨平台中文正常显示。
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"renai-localizer {__version__}")
        raise typer.Exit()


def _write_payload(
    payload: dict[str, object],
    output_file: Path,
    units: list[TranslationUnit],
    stats: dict[str, int],
    verbose: bool,
) -> None:
    """写 JSON 并输出摘要。"""
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"已提取 {len(units)} 条文本 → {output_file}")
    if verbose:
        for kind, count in stats.items():
            typer.echo(f"  {kind}: {count}")


def _extract_directory(directory: Path, encoding: str) -> ExtractionResult:
    """递归处理目录下所有 ``.rpy``，合并为一个结果。

    每个单元的 ``source`` 为相对目录的相对路径，便于跨文件引用；
    ``line`` 保留文件内行号。合并后 id 全局重新编号。
    """
    files = sorted(directory.rglob("*.rpy"))
    extractor = RpyExtractor()
    counters: dict[str, int] = {}
    merged: list[TranslationUnit] = []
    for file_path in files:
        result = extractor.extract_file(file_path, encoding=encoding)
        for unit in result.units:
            seq = counters.get(unit.kind.value, 0) + 1
            counters[unit.kind.value] = seq
            merged.append(
                unit.model_copy(
                    update={
                        "id": f"{unit.kind.value}-{seq:03d}",
                        "source": str(file_path.relative_to(directory)),
                    }
                )
            )
    return ExtractionResult(source=str(directory), units=merged)


@app.command("extract")
def extract(
    input_file: Annotated[
        Path, typer.Argument(help="要提取的 Ren'Py .rpy 脚本文件或包含 .rpy 的目录。")
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="输出 JSON 文件路径；默认与输入文件同名（.json）。"),
    ] = None,
    encoding: Annotated[str, typer.Option("--encoding", help="读取脚本文件使用的编码。")] = "utf-8",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="输出提取统计信息。")] = False,
) -> None:
    """从 Ren'Py .rpy 脚本中提取待翻译文本，并保存为结构化 JSON。

    ``input_file`` 为文件时处理单个脚本；为目录时递归处理其中所有 ``.rpy``，
    合并输出为一个 JSON，每个单元的 ``source`` 为相对目录的路径。
    """

    if not input_file.exists():
        typer.echo(f"错误：路径不存在：{input_file}", err=True)
        raise typer.Exit(code=1)

    if input_file.is_dir():
        result = _extract_directory(input_file, encoding)
        output_file = output or input_file.with_suffix(".json")
    else:
        result = RpyExtractor().extract_file(input_file, encoding=encoding)
        output_file = output or input_file.with_suffix(".json")

    payload = {
        "schema_version": result.schema_version,
        "source": result.source,
        "units": [unit.model_dump(mode="json") for unit in result.units],
        "stats": result.stats(),
    }
    _write_payload(payload, output_file, result.units, result.stats(), verbose)


@app.command("generate-tl")
def generate_tl(
    input_file: Annotated[
        Path,
        typer.Argument(
            help="extract 命令产出的 extracted.json（含 units 数组，元素须有 id/kind/text）。"
        ),
    ],
    language: Annotated[
        str,
        typer.Option("--language", help="目标语言代码，如 schinese / piglatin。"),
    ] = "schinese",
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="输出根目录（默认 .cache/<语料名>/tl/，不会写入游戏目录）。"
            "实际输出到 <output_dir>/<language>/strings.rpy。",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="输出去重前后统计。")] = False,
) -> None:
    """从 extracted.json 生成 Ren'Py 翻译文件（字符串 + 对话两个通道）。

    字符串通道：只处理 ``menu_choice`` / ``string`` 两类单元，按 old 值
    去重后写入 ``translate <language> strings:`` 块（``strings.rpy``）。

    对话通道（Sprint 3B）：处理 ``dialogue`` 单元，按源文件镜像目录结构
    生成 ``<输出目录>/<language>/<源文件相对路径>.rpy``，标识符复刻
    Ren'Py 自动生成算法（MD5 + label 前缀 + 冲突后缀 + 显式 id 覆盖）。

    翻译暂为直通（new == old），结构为后续接入 Translator / LLM 预留。
    """
    if not input_file.exists():
        typer.echo(f"错误：路径不存在：{input_file}", err=True)
        raise typer.Exit(code=1)

    try:
        payload = json.loads(input_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        typer.echo(f"错误：无法读取提取结果 {input_file}：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        result = ExtractionResult.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - 对用户展示解析错误
        typer.echo(f"错误：{input_file} 不是合法的提取结果：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    # 绝对 source 规范化为相对路径，防止对话输出覆盖源文件（见 dialogue.normalize_sources）。
    normalized = normalize_sources(result)
    if isinstance(normalized, ExtractionResult):
        result = normalized

    # 默认输出目录：.cache/<语料源目录名>/tl/（如 .cache/scarlet_hollow/tl/），
    # 与解包语料的 source（如 .cache/scarlet_hollow/rpy）保持对应；不回写游戏目录。
    source_dir = Path(result.source).parent.name or "game"
    out_root = output_dir or Path(".cache") / source_dir / "tl"

    # ---- 字符串通道（Sprint 3A，行为保持不变）----
    entries = collect_string_entries(result)
    dedup_total = len(entries)
    target = write_strings_tl(out_root, language, result)
    size = target.stat().st_size
    typer.echo(f"已生成 {target}（{size} 字节，{dedup_total} 条唯一字符串）")

    # ---- 对话通道（Sprint 3B）----
    dialogue_units = collect_dialogue_units(result)
    dialogue_files = build_dialogue_tl_all(result, language)
    if dialogue_files:
        # 按源文件路径排序写出（保持稳定输出顺序），镜像源目录结构。
        for source_path, text in sorted(dialogue_files.items()):
            rel = Path(source_path)
            if rel.suffix != ".rpy":
                rel = rel.with_suffix(".rpy")
            d_target = out_root / language / rel
            d_target.parent.mkdir(parents=True, exist_ok=True)
            d_target.write_text(text, encoding="utf-8")
    if dialogue_units:
        typer.echo(
            f"已生成对话翻译 {len(dialogue_units)} 个对白块 → "
            f"{out_root}/{language}/（按源文件镜像）"
        )

    if verbose:
        by_file: dict[str, int] = {}
        for u in dialogue_units:
            by_file[u.source] = by_file.get(u.source, 0) + 1
        typer.echo(f"  units: {len(result.units)}（menu_choice+string {len(entries)} 去重后）")
        typer.echo(f"  对白块总数: {len(dialogue_units)}")
        for source_path, count in sorted(by_file.items()):
            typer.echo(f"    {source_path}: {count}")
        typer.echo(f"  stats: {result.stats()}")


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            help="显示版本信息并退出。",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """RenAI Localizer 命令组。"""


if __name__ == "__main__":
    app()
