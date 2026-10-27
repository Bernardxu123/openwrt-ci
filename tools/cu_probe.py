#!/usr/bin/env python3
"""Probe which ubus objects/methods the CU LuCI session can use."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cu_web  # noqa: E402

tries = [
    ("luci", "getInitList", {}),
    ("luci", "getInitAction", {"name": "dropbear"}),
    ("luci", "setInitAction", {"name": "dropbear", "action": "restart"}),
    ("uci", "get", {"config": "dropbear"}),
    ("file", "read", {"path": "/etc/config/network"}),
    ("network.interface", "dump", {}),
    ("system", "info", {}),
]

s = cu_web.CuWeb()
for obj, method, args in tries:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "call",
               "params": [s.sid, obj, method, args]}
    r = s.s.post(cu_web.BASE + "/ubus", json=payload, timeout=30)
    out = r.text[:600]
    print(f"== {obj}.{method} -> {out}")
