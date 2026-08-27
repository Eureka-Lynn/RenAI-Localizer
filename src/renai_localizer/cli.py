"""RenAI Localizer 命令行入口。"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from renai_localizer import __version__
from renai_localizer.extractor import RpyExtractor

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


@app.command("extract")
def extract(
    input_file: Annotated[Path, typer.Argument(help="要提取的 Ren'Py .rpy 脚本文件。")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="输出 JSON 文件路径；默认与输入文件同名（.json）。"),
    ] = None,
    encoding: Annotated[str, typer.Option("--encoding", help="读取脚本文件使用的编码。")] = "utf-8",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="输出提取统计信息。")] = False,
) -> None:
    """从 Ren'Py .rpy 脚本中提取待翻译文本，并保存为结构化 JSON。"""

    if not input_file.exists():
        typer.echo(f"错误：文件不存在：{input_file}", err=True)
        raise typer.Exit(code=1)

    result = RpyExtractor().extract_file(input_file, encoding=encoding)

    output_file = output or input_file.with_suffix(".json")
    payload = {
        "schema_version": result.schema_version,
        "source": result.source,
        "units": [unit.model_dump(mode="json") for unit in result.units],
        "stats": result.stats(),
    }
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    typer.echo(f"已提取 {len(result.units)} 条文本 → {output_file}")
    if verbose:
        for kind, count in result.stats().items():
            typer.echo(f"  {kind}: {count}")


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
