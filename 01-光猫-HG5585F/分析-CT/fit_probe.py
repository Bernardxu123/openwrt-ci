#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIT (Flattened Image Tree) / FDT (device tree blob) forensics probe.

Pure Python 3, no external dependency: dtc / libfdt are NOT required.
Only the Python standard library is used (struct, json, hashlib, zlib,
gzip, lzma, os, sys, binascii).

Capabilities
  scan <image.itb> <out.json> [out.txt]
      * parse the FIT header (magic d00dfeed, totalsize, struct/strings
        block offsets, version, timestamp)
      * walk every /images/* and /configurations/* node and print every
        property (data-size, data-offset / data-position, description,
        type, arch, os, compression, load, entry, hash-1/hash-2 values)
      * extract each sub-image to disk (kernel/fdt/rootfs)
      * verify the DT-style hash nodes (crc32 / sha1) against the actual
        extracted bytes
      * locate and parse the appended sysupgrade metadata (JSON) and any
        ucert (signed metadata) record
  dtb <file.dtb> [out.dts]
      * parse the FDT and dump the whole tree as DTS-like text, with
        phandle references resolved when the phandle property is known

Exit code 0 on success, 2 on argument error, 3 on parse failure.

LIMITATION (recorded on purpose): this is a structural parse of the
on-disk bytes, not the output of dtc. Byte order, cell sizes and property
semantics are printed exactly as stored; labels such as gpy211 from the
original .dts source are not recoverable and are printed as node paths.
"""

import binascii
import gzip
import hashlib
import json
import lzma
import os
import struct
import sys

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

# properties whose payload is a sequence of big-endian 32-bit cells
CELL_PROPS = {
    "reg", "interrupts", "interrupts-extended", "clocks", "resets", "phys",
    "dma-ranges", "ranges", "memory-region", "nvmem-cells", "power-domains",
    "assigned-clocks", "assigned-clock-parents", "assigned-clock-rates",
    "reset-gpios", "gpios", "cs-gpios", "clock-frequency", "#address-cells",
    "#size-cells", "#gpio-cells", "#clock-cells", "#phy-cells",
    "#interrupt-cells", "#reset-cells", "#power-domain-cells",
    "#pwm-cells", "#dma-cells", "led-sources", "linux,default-trigger",
}


def align4(n):
    return (n + 3) & ~3


def read_u32(data, off):
    return struct.unpack_from(">I", data, off)[0]


def parse_fdt(data):
    """Parse a flattened device tree. Returns (root, header_dict)."""
    if len(data) < 40:
        raise ValueError("file too small for an FDT header (%d bytes)" % len(data))
    magic = read_u32(data, 0)
    if magic != 0xD00DFEED:
        raise ValueError("bad FDT magic 0x%08x (expected 0xd00dfeed)" % magic)
    (magic, totalsize, off_struct, off_strings, off_rsvmap, version,
     last_comp, boot_cpuid, size_strings, size_struct) = struct.unpack_from(">10I", data, 0)
    if off_struct + size_struct > len(data) or off_strings + size_strings > len(data):
        raise ValueError("struct/strings block runs past end of file")
    strings = data[off_strings:off_strings + size_strings]
    pos = off_struct
    end = off_struct + size_struct
    root = {"name": "", "props": {}, "children": []}
    stack = [root]
    root_seen = False
    while pos < end:
        tok = read_u32(data, pos)
        pos += 4
        if tok == FDT_BEGIN_NODE:
            nend = data.index(b"\x00", pos)
            name = data[pos:nend].decode("latin1")
            pos = align4(nend + 1)
            if not root_seen and len(stack) == 1:
                # the first FDT_BEGIN_NODE describes the root node itself
                root["name"] = name
                root_seen = True
                continue
            node = {"name": name, "props": {}, "children": []}
            stack[-1]["children"].append(node)
            stack.append(node)
        elif tok == FDT_END_NODE:
            if len(stack) == 1:
                # the FDT_END_NODE that closes the root node
                if root_seen:
                    break
                raise ValueError("unbalanced FDT_END_NODE")
            stack.pop()
        elif tok == FDT_PROP:
            plen, nameoff = struct.unpack_from(">II", data, pos)
            pos += 8
            val = data[pos:pos + plen]
            pos = align4(pos + plen)
            nend = strings.index(b"\x00", nameoff)
            pname = strings[nameoff:nend].decode("latin1")
            stack[-1]["props"][pname] = val
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
        else:
            raise ValueError("bad FDT token %d at offset %d" % (tok, pos - 4))
    header = {
        "magic": "0x%08x" % magic,
        "totalsize": totalsize,
        "off_dt_struct": off_struct,
        "off_dt_strings": off_strings,
        "off_mem_rsvmap": off_rsvmap,
        "version": version,
        "last_comp_version": last_comp,
        "boot_cpuid_phys": boot_cpuid,
        "size_dt_strings": size_strings,
        "size_dt_struct": size_struct,
    }
    return root, header


def iter_nodes(root, path=""):
    """Yield (path, node) depth-first; root path is '' and children '/x'."""
    name = root["name"]
    if name:
        p = (path if path != "/" else "") + "/" + name
    else:
        p = path
    yield p, root
    for child in root["children"]:
        yield from iter_nodes(child, p)


def prop_str(val):
    return val.rstrip(b"\x00").decode("latin1")


def prop_u32(val):
    if len(val) % 4:
        return None
    return list(struct.unpack(">%dI" % (len(val) // 4), val))


def find_prop(node, *names):
    for n in names:
        if n in node["props"]:
            return node["props"][n]
    return None


# ---------------------------------------------------------------- FIT scan

def scan_fit(path, out_json=None, out_txt=None, extract_dir=None, extract_max=4194304):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        data = fh.read()
    file_sha256 = hashlib.sha256(data).hexdigest()
    root, header = parse_fdt(data)

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit("=" * 78)
    emit("FILE      %s" % path)
    emit("SIZE      %d bytes (0x%x)" % (size, size))
    emit("SHA256    %s" % file_sha256)
    emit("FIT magic %s  totalsize %d (0x%x)" % (header["magic"], header["totalsize"], header["totalsize"]))
    emit("  off_dt_struct=%#x size=%#x  off_dt_strings=%#x size=%#x  version=%d"
         % (header["off_dt_struct"], header["size_dt_struct"],
            header["off_dt_strings"], header["size_dt_strings"], header["version"]))
    emit("  NOTE: FIT totalsize covers the FIT structure block only when the")
    emit("        sub-images use absolute data-position offsets and are")
    emit("        concatenated after it (size on disk is much larger).")

    images = []
    configs = []

    for node_path, node in iter_nodes(root):
        if node_path.startswith("/images/"):
            depth = node_path.count("/")
            if depth != 2:
                continue  # only direct children of /images
            props = node["props"]
            name = node_path.rsplit("/", 1)[-1]
            rec = {
                "node": name,
                "description": prop_str(props.get("description", b"")),
                "type": prop_str(props.get("type", b"")),
                "arch": prop_str(props.get("arch", b"")),
                "os": prop_str(props.get("os", b"")),
                "compression": prop_str(props.get("compression", b"none")),
            }
            for key, alt in (("data-position", "data-offset"), ("data-size", None),
                             ("load", None), ("entry", None), ("data", None)):
                val = find_prop(node, key) if alt is None else find_prop(node, *[(key, alt)[0], alt])
                if alt is not None:
                    val = find_prop(node, key, alt)
                if val is None:
                    continue
                if key == "data":
                    rec["inline_data_bytes"] = len(val)
                else:
                    u = prop_u32(val)
                    rec[key] = u[0] if u and len(u) == 1 else val.hex()
            # hash subnodes: hash@1 { value=<..> algo="crc32" }, hash@2 {... sha1}
            rec["hashes"] = []
            for hn in node["children"]:
                hp = hn["props"]
                rec["hashes"].append({
                    "node": hn["name"],
                    "algo": prop_str(hp.get("algo", b"")),
                    "value_hex": hp.get("value", b"").hex(),
                })
            images.append(rec)
        elif node_path.startswith("/configurations/"):
            depth = node_path.count("/")
            if depth != 2:
                continue
            props = node["props"]
            frec = {"node": node_path.rsplit("/", 1)[-1],
                    "description": prop_str(props.get("description", b"")),
                    "kernel": prop_str(props.get("kernel", b"")),
                    "fdt": prop_str(props.get("fdt", b"")),
                    "loadables": prop_str(props.get("loadables", b""))}
            configs.append(frec)

    emit("")
    emit("IMAGES (%d)" % len(images))
    for rec in images:
        pos = rec.get("data-position", rec.get("data-offset"))
        size_ = rec.get("data-size")
        pos_i = int(pos) if isinstance(pos, str) is False else int(pos, 16)
        emit("  %-10s type=%-10s comp=%-6s pos=0x%08x size=%d desc=%r"
             % (rec["node"], rec["type"], rec["compression"], pos_i, size_, rec["description"]))
        if "load" in rec:
            emit("             load=0x%08x entry=0x%08x"
                 % (rec["load"], rec.get("entry", rec["load"])))
        for h in rec["hashes"]:
            emit("             %s algo=%-6s value=%s" % (h["node"], h["algo"], h["value_hex"]))
        rec["data_position_resolved"] = pos_i

    emit("")
    emit("CONFIGURATIONS (%d)" % len(configs))
    for frec in configs:
        emit("  %s kernel=%s fdt=%s loadables=%s desc=%r"
             % (frec["node"], frec["kernel"], frec["fdt"], frec["loadables"], frec["description"]))

    # ---- extract sub-images + verify hashes
    emit("")
    emit("EXTRACT / HASH VERIFY")
    extracted = []
    if extract_dir:
        os.makedirs(extract_dir, exist_ok=True)
    for rec in images:
        pos = rec.get("data-position", rec.get("data-offset"))
        pos_i = int(pos) if not isinstance(pos, str) else int(pos, 16)
        size_i = rec.get("data-size")
        blob = data[pos_i:pos_i + size_i]
        if len(blob) != size_i:
            emit("  WARN %s: short read %d/%d" % (rec["node"], len(blob), size_i))
        rec["actual_bytes"] = len(blob)
        rec["sha256"] = hashlib.sha256(blob).hexdigest()
        rec["crc32"] = "%08x" % (binascii.crc32(blob) & 0xFFFFFFFF)
        for h in rec["hashes"]:
            if h["algo"] == "crc32":
                h["computed"] = rec["crc32"]
                h["match"] = (rec["crc32"].lower() == h["value_hex"].lower())
            elif h["algo"] == "sha1":
                h["computed"] = hashlib.sha1(blob).hexdigest()
                h["match"] = (h["computed"].lower() == h["value_hex"].lower())
        if extract_dir and size_i <= extract_max:
            ext = os.path.join(extract_dir, rec["node"] + ".bin")
            with open(ext, "wb") as fh:
                fh.write(blob)
            rec["extracted_to"] = ext
            emit("  %-10s -> %s  %d bytes  sha256=%s" % (rec["node"], ext, len(blob), rec["sha256"][:16] + "..."))
            for h in rec["hashes"]:
                emit("      %-6s %s %s" % (h["algo"], "OK  " if h.get("match") else "FAIL", h.get("computed", "")))
            if rec["compression"] in ("gzip", "gz"):
                try:
                    dec = gzip.decompress(blob)
                    ext2 = os.path.join(extract_dir, rec["node"] + ".gunzipped")
                    with open(ext2, "wb") as fh:
                        fh.write(dec)
                    rec["gunzipped"] = {"path": ext2, "size": len(dec)}
                    emit("      gzip    OK -> %s (%d bytes)" % (ext2, len(dec)))
                except Exception as exc:  # noqa: BLE001
                    emit("      gzip    FAIL %s" % exc)
            elif rec["compression"] in ("lzma", "xz"):
                try:
                    dec = lzma.decompress(blob)
                    ext2 = os.path.join(extract_dir, rec["node"] + ".unlzma")
                    with open(ext2, "wb") as fh:
                        fh.write(dec)
                    rec["unlzma"] = {"path": ext2, "size": len(dec)}
                    emit("      lzma    OK -> %s (%d bytes)" % (ext2, len(dec)))
                except Exception as exc:  # noqa: BLE001
                    emit("      lzma    FAIL %s" % exc)
        extracted.append(rec)

    # ---- appended sysupgrade metadata (JSON) + ucert
    emit("")
    emit("APPENDED SYSUPGRADE METADATA SCAN")
    meta = {}
    meta_off = None
    marker = b'{"metadata_version"'
    idx = data.find(marker)
    if idx < 0:
        idx = data.find(b"metadata_version")
    if idx >= 0:
        # step back to the opening brace of the JSON object (the marker may be
        # found on the key rather than on the opening brace)
        brace = data.rfind(b"{", max(0, idx - 16), idx + 1)
        if brace >= 0:
            idx = brace
        meta_off = idx
        # JSON is followed by a 4-byte big-endian length (ucert/sysupgrade
        # convention: `ucert -A` appends length-prefixed payload) or by the
        # ucert magic; parse a greedy balanced JSON object instead.
        depth = 0
        end = None
        in_str = False
        esc = False
        for i in range(idx, min(len(data), idx + 65536)):
            ch = data[i:i + 1]
            if in_str:
                if esc:
                    esc = False
                elif ch == b"\\":
                    esc = True
                elif ch == b'"':
                    in_str = False
                continue
            if ch == b'"':
                in_str = True
            elif ch == b"{":
                depth += 1
            elif ch == b"}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        raw = data[idx:end]
        emit("  found JSON at file offset 0x%x (tail %d bytes from end)" % (idx, size - idx))
        try:
            meta = json.loads(raw.decode("utf-8"))
            emit("  JSON parsed OK, %d bytes" % len(raw))
        except Exception as exc:  # noqa: BLE001
            emit("  JSON parse FAILED: %s" % exc)
            meta = {"_raw_len": len(raw), "_error": str(exc)}
        meta["_file_offset"] = idx
        meta["_tail_bytes"] = size - idx
        # ucert detection
        tail = data[end:] if end else b""
        ucert = {}
        for sig in (b"ucert", b"USIG"):
            k = tail.find(sig)
            if k >= 0:
                ucert["marker"] = sig.decode()
                ucert["marker_tail_offset"] = k
        if ucert:
            emit("  ucert-ish marker after JSON: %s (+%d)" % (ucert["marker"], ucert["marker_tail_offset"]))
        ucert["tail_bytes_after_json"] = len(tail)
        ucert["tail_sha256"] = hashlib.sha256(tail).hexdigest()
        meta["_ucert"] = ucert
    else:
        emit("  no sysupgrade metadata JSON marker found")

    if meta:
        emit("")
        emit("  metadata_version : %s" % meta.get("metadata_version"))
        emit("  compat_version   : %s" % meta.get("compat_version"))
        emit("  supported_devices: %s" % json.dumps(meta.get("supported_devices")))
        ver = meta.get("version", {})
        emit("  version          : dist=%s ver=%s rev=%s target=%s board=%s"
             % (ver.get("dist"), ver.get("version"), ver.get("revision"),
                ver.get("target"), ver.get("board")))

    result = {
        "path": os.path.abspath(path),
        "file_size": size,
        "file_sha256": file_sha256,
        "fit_header": header,
        "images": images,
        "configurations": configs,
        "sysupgrade_metadata": meta,
    }
    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False, sort_keys=False)
        emit("")
        emit("WROTE JSON %s" % out_json)
    if out_txt:
        with open(out_txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print("WROTE TEXT %s" % out_txt)
    return result


# ---------------------------------------------------------------- DTB dump

def fmt_cells(vals):
    return " ".join("%#x" % v for v in vals)


def dtb_to_dts(root):
    # collect phandle -> path/name map first
    phandles = {}
    all_nodes = list(iter_nodes(root))
    for p, node in all_nodes:
        for k in ("phandle", "linux,phandle"):
            if k in node["props"]:
                u = prop_u32(node["props"][k])
                if u:
                    phandles[u[0]] = p

    def resolve_cells(name, val):
        """Turn cell arrays into <&target n n> form when possible."""
        if len(val) % 4:
            return None
        vals = list(struct.unpack(">%dI" % (len(val) // 4), val))
        if not vals:
            return "<>"
        out = []
        i = 0
        while i < len(vals):
            v = vals[i]
            if v in phandles and name not in ("reg", "interrupts", "ranges", "dma-ranges"):
                out.append("&{" + phandles[v] + "}")
                i += 1
                # swallow following cell values as-is (best effort)
                while i < len(vals):
                    out.append("%#x" % vals[i])
                    i += 1
                break
            out.append("%#x" % v)
            i += 1
        return "< " + " ".join(out) + " >"

    out = []
    out.append("/dts-v1/;")
    out.append("")

    def walk(node, path, indent):
        pad = "    " * indent
        name = node["name"] if node["name"] else "/"
        label = ""
        for k in ("phandle", "linux,phandle"):
            if k in node["props"]:
                u = prop_u32(node["props"][k])
                if u:
                    label = "  /* phandle 0x%x */" % u[0]
        out.append("%s%s {%s" % (pad, name if name != "/" else "/", label))
        for pname in sorted(node["props"]):
            val = node["props"][pname]
            if pname in ("phandle", "linux,phandle"):
                continue
            txt = None
            if pname == "compatible":
                parts = [prop_str(x) for x in val.split(b"\x00") if x]
                txt = ", ".join('"%s"' % x for x in parts)
            elif pname == "model" or pname == "status" or pname == "label" \
                    or pname == "description" or pname == "phy-mode" \
                    or pname == "openwrt,netdev-name" or pname == "device_type" \
                    or pname == "bootargs" or pname == "firmware-name":
                txt = '"%s"' % prop_str(val)
            elif pname in CELL_PROPS:
                txt = resolve_cells(pname, val) or ("[" + val.hex() + "]")
            else:
                u = prop_u32(val) if len(val) == 4 else None
                if u is not None:
                    txt = "<%#x>" % u[0]
                elif len(val) == 0:
                    txt = "<>"
                else:
                    s = prop_str(val)
                    printable = s and all(32 <= ord(c) < 127 for c in s)
                    if printable:
                        txt = '"%s"' % s
                    else:
                        txt = "[" + val.hex() + "]"
            out.append("%s    %s = %s;" % (pad, pname, txt))
        for child in node["children"]:
            out.append("")
            walk(child, path + "/" + name, indent + 1)
        out.append("%s};" % pad)

    walk(root, "", 0)
    return "\n".join(out) + "\n"


def dump_dtb(path, out_dts=None):
    with open(path, "rb") as fh:
        data = fh.read()
    root, header = parse_fdt(data)
    text = dtb_to_dts(root)
    if out_dts:
        with open(out_dts, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("WROTE DTS %s (%d bytes)" % (out_dts, len(text)))
    return root, header, text


def find_in_dtb(root, needles):
    """Search property values (string form) for literal substrings."""
    hits = []
    for p, node in iter_nodes(root):
        for k, v in node["props"].items():
            try:
                s = prop_str(v)
            except Exception:  # noqa: BLE001
                continue
            for n in needles:
                if n.lower() in s.lower():
                    hits.append({"path": p, "property": k, "value": s, "needle": n})
    return hits


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "scan":
        out_json = argv[3] if len(argv) > 3 else None
        out_txt = argv[4] if len(argv) > 4 else None
        extract_dir = argv[5] if len(argv) > 5 else None
        extract_max = int(argv[6]) if len(argv) > 6 else 4194304
        scan_fit(argv[2], out_json, out_txt, extract_dir, extract_max)
        return 0
    if cmd == "dtb":
        root, header, _ = dump_dtb(argv[2], argv[3] if len(argv) > 3 else None)
        print("FDT totalsize=%d version=%d nodes=%d"
              % (header["totalsize"], header["version"], len(list(iter_nodes(root)))))
        return 0
    if cmd == "grep":
        root, _h, _t = dump_dtb(argv[2])
        needles = argv[3:]
        for hit in find_in_dtb(root, needles):
            print("%s %s = %r" % (hit["path"], hit["property"], hit["value"]))
        return 0
    print("unknown command %r" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
