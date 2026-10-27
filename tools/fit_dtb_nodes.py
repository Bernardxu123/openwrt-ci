#!/usr/bin/env python3
"""Dump selected DTB nodes (paths + a few props) from a FIT image, for QWRT/ponwrt comparison."""
import struct
import sys

FDT_MAGIC = 0xD00DFEED


def parse(fdt):
    m, ts, off_s, off_str, off_rsv, ver, lc, bc, size_s, size_str = struct.unpack_from(">10I", fdt, 0)
    assert m == FDT_MAGIC
    strings = fdt[off_str:off_str + size_str]
    pos, end = off_s, off_s + size_s
    stack, props, path = [], {}, "/"
    while pos < end:
        tag, = struct.unpack_from(">I", fdt, pos)
        pos += 4
        if tag == 1:
            nul = fdt.index(b"\x00", pos)
            name = fdt[pos:nul].decode("utf-8", "replace")
            pos = nul + 1 + ((4 - ((nul + 1 - pos) % 4)) % 4)
            stack.append((path, props))
            path = ("/" + name) if path == "/" else (path + "/" + name)
            props = {}
        elif tag == 2:
            yield path, props
            path, props = stack.pop()
        elif tag == 3:
            length, nameoff = struct.unpack_from(">II", fdt, pos)
            pos += 8
            raw = fdt[pos:pos + length]
            pos += length + ((4 - (length % 4)) % 4)
            nul = strings.index(b"\x00", nameoff)
            props[strings[nameoff:nul].decode()] = raw
        elif tag == 4:
            continue
        elif tag == 9:
            break


def cstr(raw):
    return raw.split(b"\x00")[0].decode("utf-8", "replace") if raw else None


def show(fdt, patterns):
    for path, props in parse(fdt):
        if not any(pat in path for pat in patterns):
            continue
        bits = []
        for k in ("compatible", "status", "phy-mode", "reg", "openwrt,netdev-name", "reset-gpios",
                  "reset-deassert-us", "reset-assert-us", "gpios", "linux,code", "label", "model"):
            if k in props:
                v = props[k]
                bits.append(f"{k}={cstr(v) if k in ('compatible','status','phy-mode','openwrt,netdev-name','label','model') else v.hex()}")
        print(f"{path}  {' '.join(bits)}")


if __name__ == "__main__":
    # usage: fit_dtb_nodes.py <fdt.bin> [pattern...]
    path = sys.argv[1]
    pats = sys.argv[2:] or ["ethernet", "mdio", "keys", "pcs@", "switch", "/"]
    show(open(path, "rb").read(), pats)
