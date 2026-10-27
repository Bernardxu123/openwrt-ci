#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 xdis 交叉反汇编 Python 3.13 的 code object（宿主是 3.14，dis 模块不兼容）。
纯静态：只读字节，不执行目标代码。"""
import io
import os
import sys

import xdis.unmarshal as xu
from xdis.disasm import disco

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "extract")
OUT = os.path.join(HERE, "py")
os.makedirs(OUT, exist_ok=True)

MAGIC_313 = 3571  # CPython 3.13 pyc magic int (0x0df3)


def load():
    d = open(os.path.join(EXT, "enable_telnet"), "rb").read()
    return xu.load_code(io.BytesIO(d), MAGIC_313)


def main():
    co = load()
    print(f"loaded: {co.co_name} from {co.co_filename}", file=sys.stderr)
    dst = os.path.join(OUT, "enable_telnet.disasm.txt")
    with open(dst, "w", encoding="utf-8", errors="replace") as f:
        try:
            disco((3, 13, 0), co, None, out=f)
        except Exception as e:  # noqa: BLE001
            print(f"[disco fail] {type(e).__name__}: {e}", file=f)
            raise
    print(f"[+] disassembly -> {dst}", file=sys.stderr)
    print(f"    size = {os.path.getsize(dst)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
