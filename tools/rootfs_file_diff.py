#!/usr/bin/env python3
"""Extract & compare specific files from two squashfs rootfs images (QWRT upgrade safety check).

Usage: python tools/rootfs_file_diff.py old_rootfs.bin new_rootfs.bin path1 [path2 ...]
Prints sha256 + size for each file in both images, plus a short snippet if they differ.
"""
import hashlib
import os
import subprocess
import sys
import tempfile

SEVENZIP = "7z"


def extract(rootfs, member, workdir):
    out = os.path.join(workdir, "f")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([SEVENZIP, "e", "-y", "-o" + workdir, rootfs, member],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cand = os.path.join(workdir, os.path.basename(member))
    if os.path.exists(cand):
        return open(cand, "rb").read()
    return None


def main():
    old, new = sys.argv[1], sys.argv[2]
    members = sys.argv[3:]
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        for m in members:
            a = extract(old, m, t1)
            b = extract(new, m, t2)
            ha = hashlib.sha256(a).hexdigest()[:16] if a else "-"
            hb = hashlib.sha256(b).hexdigest()[:16] if b else "-"
            same = "SAME" if (a is not None and a == b) else "DIFF"
            print(f"{m}: old={len(a) if a else 0}B/{ha} new={len(b) if b else 0}B/{hb} {same}")
            if same == "DIFF" and a and b:
                # show differing lines (text only, small files)
                if len(a) < 40000 and len(b) < 40000:
                    al = a.decode("utf-8", "replace").splitlines()
                    bl = b.decode("utf-8", "replace").splitlines()
                    import difflib
                    diff = list(difflib.unified_diff(al, bl, "old", "new", lineterm="", n=1))
                    for line in diff[:60]:
                        print("   ", line)
                else:
                    print("    (binary/size differs, snippet omitted)")


if __name__ == "__main__":
    main()
