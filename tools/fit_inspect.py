#!/usr/bin/env python3
"""Parse an OpenWrt FIT (.itb) image: sub-images, sysupgrade metadata, selected DTB props.

Usage: python tools/fit_inspect.py <image.itb> [--extract-dir DIR]
"""
import json
import os
import struct
import sys
import zlib

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


def parse_struct(blob, off, size, strings):
    """Yield (path, props) for each node."""
    pos = off
    end = off + size
    stack = []
    node_props = {}
    cur_path = "/"

    def path_join(p, n):
        if n in ("/", ""):
            return "/"
        return (p.rstrip("/") + "/" + n) if p != "/" else "/" + n

    while pos < end:
        tag, = struct.unpack_from(">I", blob, pos)
        pos += 4
        if tag == FDT_BEGIN_NODE:
            nul = blob.index(b"\x00", pos)
            name = blob[pos:nul].decode("utf-8", "replace")
            pos = nul + 1 + ((4 - ((nul + 1 - pos) % 4)) % 4)
            stack.append((cur_path, node_props))
            cur_path = path_join(cur_path, name)
            node_props = {}
        elif tag == FDT_END_NODE:
            yield cur_path, node_props
            cur_path, node_props = stack.pop()
        elif tag == FDT_PROP:
            length, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            raw = blob[pos:pos + length]
            pos += length + ((4 - (length % 4)) % 4)
            nul = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:nul].decode("utf-8", "replace")
            node_props[pname] = raw
        elif tag == FDT_NOP:
            continue
        elif tag == FDT_END:
            break


def u32(raw):
    return struct.unpack(">I", raw[:4])[0] if raw and len(raw) >= 4 else None


def cstr(raw):
    if raw is None:
        return None
    return raw.split(b"\x00")[0].decode("utf-8", "replace")


def main():
    path = sys.argv[1]
    extract = None
    if "--extract-dir" in sys.argv:
        extract = sys.argv[sys.argv.index("--extract-dir") + 1]
    blob = open(path, "rb").read()
    magic, totalsize, off_s, off_str, off_rsv, ver, last_comp, boot_cpu, size_str, size_s = struct.unpack_from(">10I", blob, 0)
    assert magic == FDT_MAGIC, "not a FIT image"
    strings = blob[off_str:off_str + size_str]
    print(f"== {os.path.basename(path)}  size={len(blob)}  FIT totalsize={totalsize} version={ver}")

    images = {}
    for p, props in parse_struct(blob, off_s, size_s, strings):
        if "data-position" in props or "data-offset" in props:
            images[p] = props

    for p, props in images.items():
        dp = u32(props.get("data-position"))
        ds = u32(props.get("data-size"))
        desc = cstr(props.get("description"))
        ctype = cstr(props.get("type"))
        comp = cstr(props.get("compression"))
        load = u32(props.get("load"))
        h1 = props.get("hash-1")
        crc = u32(h1) if h1 else None
        h2 = props.get("hash-2")
        # verify crc32 of payload when cheap (kernel/rootfs can be large but fine)
        verify = ""
        if dp is not None and ds:
            payload = blob[dp:dp + ds]
            if crc is not None:
                ok = (zlib.crc32(payload) & 0xFFFFFFFF) == crc
                verify = f" crc32={'OK' if ok else 'MISMATCH'}"
        print(f"  {p}: type={ctype} comp={comp} pos=0x{dp:08x} size={ds} load={('0x%08x' % load) if load else None}")
        print(f"      desc={desc!r}{verify}")
        images[p]["_payload"] = (dp, ds)

    # sysupgrade metadata tail (JSON) — look for metadata_version
    idx = blob.rfind(b'metadata_version')
    if idx >= 0:
        # walk backwards to the opening brace of that object
        start = blob.rfind(b"{", 0, idx)
        idx = start if start >= 0 else idx
    if idx >= 0:
        depth = 0
        for i in range(idx, min(idx + 4096, len(blob))):
            if blob[i:i + 1] == b"{":
                depth += 1
            elif blob[i:i + 1] == b"}":
                depth -= 1
                if depth == 0:
                    meta = blob[idx:i + 1]
                    try:
                        j = json.loads(meta)
                        print("  metadata:", json.dumps(j, ensure_ascii=False))
                    except Exception as e:
                        print("  metadata parse error:", e, meta[:200])
                    break
        # signature markers after metadata
        tail = blob[idx:idx + 800]
        for marker in (b"FWx0", b"untrusted comment", b"ucert", b"Local build key"):
            print(f"  marker {marker!r}: {tail.find(marker)}")
    else:
        print("  metadata: not found")

    # DTB summary: model, PHY compat, reset key gpios
    for p, props in images.items():
        if cstr(props.get("type") or "") not in ("flat_dt", "fdt"):
            continue
        dp, ds = props["_payload"]
        fdt = blob[dp:dp + ds]
        m, ts, os_, osr, orr, vv, ls, bc, ss, sst = struct.unpack_from(">10I", fdt, 0)
        fstrings = fdt[osr:osr + sst]
        print(f"  -- DTB {p} ({ds} B) --")
        want = {"/": ["model", "compatible"],
                "/soc/ethernet@1fb50000/ethernet@4": ["status", "phy-mode", "openwrt,netdev-name"],
                "/soc/switch@1fb58000/mdio/ethernet-phy@7": ["compatible", "reg", "reset-gpios", "reset-deassert-us"],
                "/soc/switch@1fb58000/mdio/ethernet-phy@9": ["compatible", "reg"],
                "/keys/reset": ["gpios", "linux,code", "label"]}
        for node, props_ in parse_struct(fdt, os_, ss, fstrings):
            if node in want:
                for k in want[node]:
                    raw = props_.get(k)
                    if raw is None:
                        continue
                    if k in ("model", "compatible", "status", "phy-mode", "openwrt,netdev-name", "label"):
                        print(f"     {node} {k} = {cstr(raw)}")
                    else:
                        print(f"     {node} {k} = {raw.hex()}")

    if extract:
        os.makedirs(extract, exist_ok=True)
        for p, props in images.items():
            dp, ds = props["_payload"]
            name = p.strip("/").replace("/", "_") + ".bin"
            out = os.path.join(extract, name)
            with open(out, "wb") as fh:
                fh.write(blob[dp:dp + ds])
            print(f"  extracted {p} -> {out} ({ds} B)")


if __name__ == "__main__":
    main()
