"""unrpa 薄封装：从 Ren'Py RPA 归档中选择性抽取指定后缀的文件。

unrpa CLI（`unrpa -mp out archive.rpa`）只能全量解包，不支持按文件名过滤。
unrpa 库 API 支持按条目选择性抽取，因此本工具复用库 API 实现薄封装：

- 解析归档头 / 索引（`UnRPA.get_index`，返回
  ``dict[str, Iterable[(offset, length, prefix)]]``，offset/length 已按 key 解密，
  路径分隔符已归一化为 ``os.sep``）；
- 仅解压匹配 ``--suffix`` 的条目，保持相对目录结构写入输出目录；
- 不抽取图片、音频、``.rpyc`` 等其它资源。

使用方式：:

    python tools/unpack_rpa.py <archive.rpa> <输出目录> [--suffix .rpy]...
    python tools/unpack_rpa.py <archive.rpa> --list
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from unrpa import UnRPA

# Windows 终端（如 cmd.exe）默认使用 GBK 编码，直接输出中文会乱码。
# 将标准输出/错误重配置为 UTF-8，保证跨平台中文正常显示。
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8")


def _matches(name: str, suffixes: list[str]) -> bool:
    """判断归档条目名是否以给定后缀之一结尾（大小写不敏感）。"""
    lower = name.lower()
    return any(lower.endswith(suf.lower()) for suf in suffixes)


def list_archive(archive: Path) -> None:
    """只列出归档内容，按扩展名分组统计，不抽取任何文件。"""
    unrpa = UnRPA(str(archive), verbosity=-1)
    version = unrpa.detect_version()
    with open(archive, "rb") as f:
        index = unrpa.get_index(f, version)
    counts: dict[str, int] = {}
    for name in index:
        ext = os.path.splitext(name)[1].lower() or "(no ext)"
        counts[ext] = counts.get(ext, 0) + 1
    print(f"归档 {archive}（{version}）共 {len(index)} 个条目：")
    for ext in sorted(counts):
        print(f"  {ext:<12} {counts[ext]}")


def extract(archive: Path, out_dir: Path, suffixes: list[str]) -> tuple[int, int, int]:
    """选择性抽取匹配后缀的条目到输出目录。

    返回 ``(归档条目总数, 抽取文件数, 总字节数)``。
    """
    unrpa = UnRPA(str(archive), verbosity=-1)
    version = unrpa.detect_version()
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    extracted = 0
    total_bytes = 0
    with open(archive, "rb") as f:
        index = unrpa.get_index(f, version)
        total = len(index)
        for file_number, (name, data) in enumerate(index.items()):
            if not _matches(name, suffixes):
                continue
            # 归档内路径理论上可信，但仍做穿越防护，避免写出到输出目录之外。
            rel = os.path.normpath(name)
            if os.path.isabs(rel) or rel.split(os.sep)[0] == "..":
                raise ValueError(f"归档内非法路径：{name}")
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            view = unrpa.extract_file(name, data, file_number, total, f)
            with open(target, "wb") as out:
                # postprocess 将 view（含 RPA-3.0 的 prefix 分段）写出到 sink，
                # 与 unrpa 自身的全量解包路径完全一致。
                version.postprocess(view, out)
            extracted += 1
            total_bytes += target.stat().st_size
    return total, extracted, total_bytes


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="unpack_rpa.py",
        description="用 unrpa 库 API 从 RPA 归档中选择性抽取指定后缀的文件。",
    )
    parser.add_argument("archive", type=Path, help="RPA 归档路径（如 game/archive.rpa）。")
    parser.add_argument("out_dir", type=Path, nargs="?", help="输出目录。")
    parser.add_argument(
        "--list",
        action="store_true",
        help="只列出归档内容（按扩展名分组统计），不抽取任何文件。",
    )
    parser.add_argument(
        "--suffix",
        action="append",
        default=[],
        metavar=".ext",
        help="要抽取的后缀，可重复指定（如 --suffix .rpy --suffix .rpyc）；默认仅 .rpy。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.archive.is_file():
        print(f"错误：归档不存在：{args.archive}", file=sys.stderr)
        return 1

    if args.list:
        list_archive(args.archive)
        return 0

    if args.out_dir is None:
        print("错误：抽取模式需要提供输出目录（或使用 --list）。", file=sys.stderr)
        return 1

    suffixes = args.suffix or [".rpy"]
    total, extracted, total_bytes = extract(args.archive, args.out_dir, suffixes)
    print(f"归档条目总数: {total}")
    print(f"抽取文件数:   {extracted}（后缀: {', '.join(suffixes)}）")
    print(f"总字节数:     {total_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
