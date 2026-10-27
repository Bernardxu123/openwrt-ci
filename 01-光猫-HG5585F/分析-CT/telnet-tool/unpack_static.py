#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯静态解包 HG5585F-CT-V2一键开Telnet.exe（PyInstaller）。
绝不执行目标程序：只用 PyInstaller 自带的 CArchiveReader/ZlibArchiveReader 读字节。
产物统一写到 分析/telnet-tool/extract/。
"""
import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "..", "..", "下载资料",
                   "HG5585F-CT-V2一键开Telnet", "HG5585F-CT-V2一键开Telnet.exe")
OUT = os.path.join(HERE, "extract")

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader  # noqa: E402
from PyInstaller.archive.readers import NotAnArchiveError  # noqa: E402


def main():
    exe = os.path.abspath(EXE)
    print(f"[+] target: {exe}")
    print(f"[+] size  : {os.path.getsize(exe)}")
    os.makedirs(OUT, exist_ok=True)

    arch = CArchiveReader(exe)
    # 内部字段（不同版本命名略有差异，逐个取）
    info = {}
    for name in ("_start_offset", "_end_offset", "_toc_offset", "_toc_length",
                 "_archive_length", "_pyvers", "_pylib_name"):
        if hasattr(arch, name):
            info[name] = getattr(arch, name)
    print("[+] archive internals:", json.dumps(info, default=str, ensure_ascii=False))

    toc = arch.toc
    print(f"[+] TOC entries: {len(toc)}")
    rows = []
    for name, entry in toc.items():
        # entry = (typecode, position, length, uncompressed_length)
        rows.append({"name": name, "typecode": entry[0], "pos": entry[1],
                     "clen": entry[2], "ulen": entry[3]})
    with open(os.path.join(OUT, "toc.json"), "w", encoding="utf-8") as f:
        json.dump({"internals": {k: str(v) for k, v in info.items()},
                   "count": len(rows), "entries": rows}, f, ensure_ascii=False, indent=1)

    # 打印 TOC（按类型归类）
    for r in rows:
        print(f"  {r['typecode']} {r['ulen']:>10} {r['name']}")

    # 提取所有非 PYZ 条目（按 PyInstaller 自身的命名约定落盘）
    for name, entry in toc.items():
        typecode = entry[0]
        try:
            data = arch.extract(name)
        except Exception as e:  # noqa: BLE001
            print(f"  !! extract fail {name}: {type(e).__name__}: {e}")
            continue
        if typecode == "z":  # PYZ
            pyz_path = os.path.join(OUT, name.replace("/", "_"))
            with open(pyz_path, "wb") as f:
                f.write(data)
            print(f"[+] PYZ saved -> {pyz_path} ({len(data)} B)")
            continue
        safe = name.replace("/", os.sep).replace("\\", os.sep)
        dst = os.path.join(OUT, safe)
        os.makedirs(os.path.dirname(dst), exist_ok=True) if os.path.dirname(dst) else None
        with open(dst, "wb") as f:
            f.write(data)
        print(f"  -> {safe} ({len(data)} B, type={typecode})")

    print("\n[done] TOC + payloads written to", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
