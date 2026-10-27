#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态分析：解 PYZ、读主脚本 pyc 的常量/名字，不执行目标代码。"""
import dis
import json
import marshal
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "extract")
OUT = os.path.join(HERE, "py")
os.makedirs(OUT, exist_ok=True)

from PyInstaller.archive.readers import ZlibArchiveReader  # noqa: E402


def load_pyc(path):
    """PyInstaller 6.x 把入口脚本存成裸 marshal 流（无 pyc 头）。
    依次尝试 0/16/12 字节偏移。"""
    with open(path, "rb") as f:
        data = f.read()
    print(f"  raw size={len(data)} first16={data[:16].hex(' ')}")
    for off in (0, 16, 12, 8):
        try:
            code = marshal.loads(data[off:])
            print(f"  marshal ok at offset {off} (raw marshal stream, no pyc header)"
                  if off == 0 else f"  marshal ok at offset {off}")
            return code, data[:4].hex(), off
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit("cannot marshal-load entry script")


def walk_codes(code, depth=0, seen=None):
    yield code, depth
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from walk_codes(c, depth + 1)


def summarize(code, label):
    print(f"\n===== {label} =====")
    print(f"co_filename = {code.co_filename!r}")
    print(f"co_name     = {code.co_name!r}")
    print(f"co_names({len(code.co_names)}) = {code.co_names}")
    print(f"co_varnames({len(code.co_varnames)}) = {code.co_varnames}")
    consts = [c for c in code.co_consts if not isinstance(c, types.CodeType)]
    print(f"co_consts ({len(consts)} non-code):")
    for c in consts:
        r = repr(c)
        if len(r) > 400:
            r = r[:400] + f"...<len={len(r)}>"
        print("   ", r)
    inner = [c.co_name for c in code.co_consts if isinstance(c, types.CodeType)]
    if inner:
        print(f"  inner code objects: {inner}")


def main():
    # --- 1. 主脚本 enable_telnet ---
    main_path = os.path.join(EXT, "enable_telnet")
    print("[1] entry script:", main_path)
    code, magic, flags = load_pyc(main_path)
    summarize(code, "enable_telnet <module>")
    # 递归
    def rec(c, path="enable_telnet"):
        for k in c.co_consts:
            if isinstance(k, types.CodeType):
                summarize(k, f"{path}.{k.co_name}")
                rec(k, f"{path}.{k.co_name}")
    rec(code)

    # 反汇编到文件
    with open(os.path.join(OUT, "enable_telnet.dis.txt"), "w", encoding="utf-8") as f:
        dis.dis(code, file=f, depth=None)
    print("\n[+] disassembly -> py/enable_telnet.dis.txt")

    # marshal 结构导出（JSON 友好）
    dump = {}

    def node(c):
        return {
            "name": c.co_name,
            "qualname": getattr(c, "co_qualname", None),
            "filename": c.co_filename,
            "firstlineno": c.co_firstlineno,
            "names": list(c.co_names),
            "varnames": list(c.co_varnames),
            "consts": [repr(x) if not isinstance(x, types.CodeType) else f"<code {x.co_name}>"
                       for x in c.co_consts],
            "children": [node(k) for k in c.co_consts if isinstance(k, types.CodeType)],
        }

    dump["enable_telnet"] = node(code)
    with open(os.path.join(OUT, "enable_telnet.consts.json"), "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=1)

    # --- 2. PYZ ---
    pyz_path = os.path.join(EXT, "PYZ.pyz")
    print("\n[2] PYZ:", pyz_path)
    pyz = ZlibArchiveReader(pyz_path)
    mods = sorted(pyz.toc)
    print(f"  modules: {len(mods)}")
    with open(os.path.join(OUT, "pyz-toc.txt"), "w", encoding="utf-8") as f:
        for m in mods:
            f.write(m + "\n")
    for m in mods:
        print("   ", m)

    # 导出非标准库模块的源码结构
    interest = [m for m in mods if not m.startswith(
        ("encodings", "importlib", "collections", "email", "json", "logging",
         "xml", "http", "urllib", "concurrent", "asyncio", "ctypes", "unittest",
         "multiprocessing", "sqlite3", "decimal", "re.", "socket.", "ssl."))]
    print(f"\n  non-stdlib-ish modules ({len(interest)}): {interest}")
    report = {}
    for m in mods:
        try:
            code = pyz.extract(m)
        except Exception as e:  # noqa: BLE001
            report[m] = {"error": f"{type(e).__name__}: {e}"}
            continue
        if not isinstance(code, types.CodeType):
            report[m] = {"type": type(code).__name__}
            continue
        report[m] = {
            "names": list(code.co_names),
            "consts": [repr(x) if not isinstance(x, types.CodeType)
                       else f"<code {x.co_name}>" for x in code.co_consts],
            "filename": code.co_filename,
        }
    with open(os.path.join(OUT, "pyz-modules.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # PYZ 里是否有 AES/Crypto/加密相关模块
    print("\n[3] crypto-ish modules in PYZ:")
    for m in mods:
        if any(k in m.lower() for k in ("crypt", "aes", "cipher", "hash", "hmac", "rsa", "crypto")):
            print("   ", m)


if __name__ == "__main__":
    main()
