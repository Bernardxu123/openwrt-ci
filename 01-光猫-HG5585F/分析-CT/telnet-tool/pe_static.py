#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PE 静态取证：导入表、资源、版本信息、manifest、签名、节表、时间戳。
只读文件字节，不执行。"""
import hashlib
import json
import os
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "pe")
os.makedirs(OUT, exist_ok=True)


def analyze(path, tag):
    lines = []

    def w(s=""):
        lines.append(str(s))

    raw = open(path, "rb").read()
    w(f"# {tag}")
    w(f"path      : {path}")
    w(f"size      : {len(raw)}")
    w(f"sha256    : {hashlib.sha256(raw).hexdigest()}")
    w(f"sha1      : {hashlib.sha1(raw).hexdigest()}")
    w(f"md5       : {hashlib.md5(raw).hexdigest()}")
    try:
        w(f"imphash   : {pefile.PE(data=raw, fast_load=True).get_imphash()}")
    except Exception as e:  # noqa: BLE001
        w(f"imphash   : <{type(e).__name__}>")

    pe = pefile.PE(data=raw, fast_load=False)
    fh = pe.FILE_HEADER
    oh = pe.OPTIONAL_HEADER
    w(f"\n## PE 头")
    w(f"machine            : 0x{fh.Machine:04x} ({pefile.MACHINE_TYPE.get(fh.Machine)})")
    w(f"NumberOfSections   : {fh.NumberOfSections}")
    w(f"TimeDateStamp      : {fh.TimeDateStamp} ({pe.get_string_at_rva if False else ''}"
      f"{fh.TimeDateStamp})")
    import datetime
    try:
        w(f"   -> UTC          : {datetime.datetime.utcfromtimestamp(fh.TimeDateStamp).isoformat()}Z")
    except Exception:  # noqa: BLE001
        pass
    w(f"Characteristics    : 0x{fh.Characteristics:04x}")
    w(f"Subsystem          : {oh.Subsystem} ({pefile.SUBSYSTEM_TYPE.get(oh.Subsystem)})")
    w(f"ImageBase          : 0x{oh.ImageBase:x}")
    w(f"AddressOfEntryPoint: 0x{oh.AddressOfEntryPoint:x}")
    w(f"SizeOfImage        : 0x{oh.SizeOfImage:x}")
    w(f"DllCharacteristics : 0x{oh.DllCharacteristics:04x}"
      f"  [ASLR={bool(oh.DllCharacteristics & 0x40)}"
      f" DEP={bool(oh.DllCharacteristics & 0x100)}"
      f" CFG={bool(oh.DllCharacteristics & 0x4000)}"
      f" HighEntropyVA={bool(oh.DllCharacteristics & 0x20)}]")

    w(f"\n## 节表")
    for s in pe.sections:
        nm = s.Name.rstrip(b"\x00").decode("latin-1")
        w(f"  {nm:<10} VA=0x{s.VirtualAddress:08x} VSize=0x{s.Misc_VirtualSize:08x}"
          f" RawPtr=0x{s.PointerToRawData:08x} RawSize=0x{s.SizeOfRawData:08x}"
          f" Entropy={s.get_entropy():.3f} Chars=0x{s.Characteristics:08x}")

    w(f"\n## 导入 DLL / 函数")
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            names = []
            for imp in d.imports:
                names.append(imp.name.decode() if imp.name else f"ord#{imp.ordinal}")
            w(f"  {d.dll.decode()}: {', '.join(names)}")
    else:
        w("  (无导入表)")

    w(f"\n## 延迟导入")
    if hasattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for d in pe.DIRECTORY_ENTRY_DELAY_IMPORT:
            w(f"  {d.dll.decode()}: {[i.name.decode() if i.name else i.ordinal for i in d.imports]}")
    else:
        w("  (无)")

    w(f"\n## 资源")
    if hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
        def walk(entries, depth=0, pathacc=""):
            for e in entries:
                if e.id is not None and e.name is not None:
                    nm = e.name.string.decode("latin-1", "replace")
                elif e.name is not None:
                    nm = e.name.string.decode("latin-1", "replace")
                else:
                    nm = pefile.RESOURCE_TYPE.get(e.id, str(e.id)) if depth == 0 else str(e.id)
                p = f"{pathacc}/{nm}"
                if hasattr(e, "directory"):
                    walk(e.directory.entries, depth + 1, p)
                else:
                    d = e.data.struct
                    w(f"  {p}  RVA=0x{d.OffsetToData:x} Size={d.Size}")
        walk(pe.DIRECTORY_ENTRY_RESOURCE.entries)
    else:
        w("  (无资源)")

    w(f"\n## 版本信息 (VS_VERSIONINFO)")
    if hasattr(pe, "VS_VERSIONINFO"):
        for fi in pe.FileInfo or []:
            for entry in fi:
                if getattr(entry, "Key", b"") == b"StringFileInfo":
                    for st in entry.StringTable:
                        for k, v in st.entries.items():
                            w(f"  {k.decode(errors='replace')} = {v.decode(errors='replace')}")
                elif getattr(entry, "Key", b"") == b"VarFileInfo":
                    for var in getattr(entry, "Var", []):
                        try:
                            w(f"  Var {var.Key}: {var.Values}")
                        except AttributeError:
                            w(f"  Var(raw): {var}")
    else:
        w("  (无版本信息)")

    w(f"\n## 嵌入 manifest")
    if hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
        for rt in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if rt.id == pefile.RESOURCE_TYPE["RT_MANIFEST"]:
                for e in rt.directory.entries:
                    for l in e.directory.entries:
                        data = pe.get_data(l.data.struct.OffsetToData, l.data.struct.Size)
                        try:
                            w(data.decode("utf-8", "replace"))
                        except Exception:  # noqa: BLE001
                            w(repr(data[:400]))

    w(f"\n## 签名 (Security Directory / Authenticode)")
    sec = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]  # IMAGE_DIRECTORY_ENTRY_SECURITY
    w(f"  VirtualAddress=0x{sec.VirtualAddress:x} Size={sec.Size}")
    w(f"  -> {'无 Authenticode 签名' if sec.Size == 0 else '存在签名数据'}")

    w(f"\n## 调试目录 / PDB")
    if hasattr(pe, "DIRECTORY_ENTRY_DEBUG"):
        for d in pe.DIRECTORY_ENTRY_DEBUG:
            try:
                w(f"  {d.entry.PdbFileName.decode(errors='replace')}")
            except Exception:  # noqa: BLE001
                w(f"  type={d.struct.Type}")
    else:
        w("  (无)")

    # overlay / 尾部数据
    last = max(s.PointerToRawData + s.SizeOfRawData for s in pe.sections)
    w(f"\n## 尾部/overlay")
    w(f"  最后节末尾 = 0x{last:x} ({last}); 文件 {len(raw)} -> overlay {len(raw) - last} B")

    dst = os.path.join(OUT, f"{tag}.txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[+] {dst}")
    return "\n".join(lines)


if __name__ == "__main__":
    base = os.path.abspath(os.path.join(HERE, "..", "..", "下载资料"))
    targets = [
        (os.path.join(base, "HG5585F-CT-V2一键开Telnet", "HG5585F-CT-V2一键开Telnet.exe"), "telnet-tool-exe"),
        (os.path.join(base, "ftp", "tftpd64.exe"), "tftpd64-exe"),
    ]
    for p, tag in targets:
        print(analyze(p, tag))
        print("\n" + "=" * 100 + "\n")
