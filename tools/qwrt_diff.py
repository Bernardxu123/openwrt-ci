#!/usr/bin/env python3
"""Compare two QWRT itb images: revision, signing key, sub-image sizes, package diff.

Usage: python tools/qwrt_diff.py old.itb new.itb
"""
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

FDT_MAGIC = 0xD00DFEED
SEVENZIP = "7z"


def fit_images(blob):
    magic, totalsize, off_s, off_str, off_rsv, ver, lc, bc, size_s, size_str = struct.unpack_from(">10I", blob, 0)
    assert magic == FDT_MAGIC
    strings = blob[off_str:off_str + size_str]
    images = {}
    pos, end = off_s, off_s + size_s
    stack, props, path = [], {}, "/"
    while pos < end:
        tag, = struct.unpack_from(">I", blob, pos)
        pos += 4
        if tag == 1:
            nul = blob.index(b"\x00", pos)
            name = blob[pos:nul].decode("utf-8", "replace")
            pos = nul + 1
            while (pos - off_s) % 4:
                pos += 1
            stack.append((path, props))
            path = ("/" + name) if path == "/" else (path + "/" + name)
            props = {}
        elif tag == 2:
            if "data-position" in props:
                images[path] = props
            path, props = stack.pop()
        elif tag == 3:
            length, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            raw = blob[pos:pos + length]
            pos += length + ((4 - (length % 4)) % 4)
            nul = strings.index(b"\x00", nameoff)
            props[strings[nameoff:nul].decode()] = raw
        elif tag == 9:
            break
    return images


def info(blob):
    images = fit_images(blob)
    out = {"images": {}}
    for p, props in images.items():
        dp = struct.unpack(">I", props["data-position"][:4])[0]
        ds = struct.unpack(">I", props["data-size"][:4])[0]
        out["images"][p] = {"pos": dp, "size": ds,
                            "desc": props.get("description", b"").split(b"\x00")[0].decode("utf-8", "replace")}
    m = re.search(rb'\{"metadata_version".{0,600}?\}\}', blob)
    if m:
        try:
            out["meta"] = json.loads(m.group(0))
        except Exception:
            out["meta"] = None
    k = re.search(rb"signed by key ([0-9a-f]+)", blob)
    out["sign_key"] = k.group(1).decode() if k else None
    return out


def pkg_status(blob, info_, workdir):
    """Extract usr/lib/opkg/status from squashfs rootfs and return dict name->version."""
    rootfs = info_["images"].get("/images/rootfs-1")
    if not rootfs:
        return {}
    with open(os.path.join(workdir, "rootfs.bin"), "wb") as fh:
        fh.write(blob[rootfs["pos"]:rootfs["pos"] + rootfs["size"]])
    status_path = os.path.join(workdir, "status")
    try:
        subprocess.run([SEVENZIP, "e", "-so", os.path.join(workdir, "rootfs.bin"), "usr/lib/opkg/status"],
                       stdout=open(status_path, "wb"), stderr=subprocess.DEVNULL, check=False)
    except Exception:
        return {}
    pkgs = {}
    if not os.path.exists(status_path):
        return pkgs
    name = ver = None
    for line in open(status_path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("Package: "):
            name = line[9:].strip()
        elif line.startswith("Version: "):
            ver = line[9:].strip()
            if name:
                pkgs[name] = ver
        elif not line.strip():
            name = ver = None
    return pkgs


def main():
    old_path, new_path = sys.argv[1], sys.argv[2]
    old, new = open(old_path, "rb").read(), open(new_path, "rb").read()
    io, inew = info(old), info(new)
    print(f"== size: old={len(old)} new={len(new)} (delta {len(new)-len(old):+d})")
    print(f"== revision: old={io['meta']['version']['revision'] if io.get('meta') else '?'} "
          f"new={inew['meta']['version']['revision'] if inew.get('meta') else '?'}")
    print(f"== sign key: old={io['sign_key']} new={inew['sign_key']}")
    print("== sub-images:")
    for key in sorted(set(io["images"]) | set(inew["images"])):
        a = io["images"].get(key, {})
        b = inew["images"].get(key, {})
        print(f"   {key}: old={a.get('size')} new={b.get('size')} delta={ (b.get('size') or 0) - (a.get('size') or 0):+d}")
        if a.get("desc") != b.get("desc"):
            print(f"      desc old={a.get('desc')!r}")
            print(f"      desc new={b.get('desc')!r}")

    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        po = pkg_status(old, io, t1)
        pn = pkg_status(new, inew, t2)
    if po and pn:
        added = sorted(set(pn) - set(po))
        removed = sorted(set(po) - set(pn))
        changed = sorted(k for k in set(po) & set(pn) if po[k] != pn[k])
        print(f"== packages: old={len(po)} new={len(pn)}  added={len(added)} removed={len(removed)} changed={len(changed)}")
        if added:
            print("   + added:", ", ".join(added[:60]))
        if removed:
            print("   - removed:", ", ".join(removed[:60]))
        if changed:
            print("   ~ changed:")
            for k in changed[:40]:
                print(f"      {k}: {po[k]} -> {pn[k]}")
    else:
        print("== packages: status db not parsed")


if __name__ == "__main__":
    main()
