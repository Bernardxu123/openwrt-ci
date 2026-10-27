#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 UTF-8 常量表 + 分函数反汇编切片，便于人工审阅。纯静态。"""
import io
import json
import os
import sys
import types

import xdis.unmarshal as xu

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "extract")
OUT = os.path.join(HERE, "py")
MAGIC_313 = 3571


def walk(co, path="<module>"):
    yield path, co
    for c in co.co_consts:
        if isinstance(c, types.CodeType) or type(c).__name__.startswith("Code"):
            yield from walk(c, f"{path}.{c.co_name}")


def main():
    co = xu.load_code(io.BytesIO(open(os.path.join(EXT, "enable_telnet"), "rb").read()), MAGIC_313)

    lines = []
    lines.append("# enable_telnet.py 静态常量/名字清单（由 marshal 直接读取，未执行）\n")
    lines.append(f"模块 docstring:\n{co.co_consts[0]!r}\n")
    lines.append("## 模块级 co_names\n")
    lines.append(repr(co.co_names) + "\n")
    lines.append("\n## 模块级 co_consts（非 code）\n")
    for i, c in enumerate(co.co_consts):
        if isinstance(c, types.CodeType) or type(c).__name__.startswith("Code"):
            continue
        lines.append(f"[{i}] {c!r}\n")

    lines.append("\n\n# ===== 逐函数 =====\n")
    for path, c in walk(co):
        if path == "<module>":
            continue
        lines.append(f"\n## {path}\n")
        lines.append(f"  行号: {getattr(c, 'co_firstlineno', '?')}\n")
        lines.append(f"  co_names   : {list(c.co_names)}\n")
        lines.append(f"  co_varnames: {list(c.co_varnames)}\n")
        consts = [x for x in c.co_consts
                  if not (isinstance(x, types.CodeType) or type(x).__name__.startswith("Code"))]
        lines.append(f"  co_consts  :\n")
        for i, x in enumerate(consts):
            lines.append(f"    [{i}] {x!r}\n")
        inner = [x.co_name for x in c.co_consts
                 if isinstance(x, types.CodeType) or type(x).__name__.startswith("Code")]
        if inner:
            lines.append(f"  内嵌 code: {inner}\n")

    dst = os.path.join(OUT, "enable_telnet.consts.txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[+] {dst} ({os.path.getsize(dst)} B)")

    # 单独的“关键字符串”汇总（便于写报告）
    key = []
    for path, c in walk(co):
        for x in c.co_consts:
            if isinstance(x, str) and len(x) > 2:
                key.append((path, x))
    with open(os.path.join(OUT, "strings_from_consts.txt"), "w", encoding="utf-8") as f:
        for p, s in key:
            f.write(f"{p}\t{s!r}\n")
    print(f"[+] strings_from_consts.txt ({len(key)} strings)")


if __name__ == "__main__":
    main()
