#!/usr/bin/env python3
"""Write a file on the CU router through rpcd file.write (base64 payload).

Usage: python tools/cu_write.py <remote_path> <local_content_file>
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cu_web  # noqa: E402


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    remote, local = sys.argv[1], sys.argv[2]
    with open(local, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    w = cu_web.CuWeb()
    res = w.call("file", "write", {"path": remote, "data": data}, raw=True)
    print("write result:", res)
    # read back and compare
    back = w.call("file", "read", {"path": remote}, raw=True)
    print("read back:", str(back)[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())
