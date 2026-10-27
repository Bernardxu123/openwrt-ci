#!/usr/bin/env python3
"""Probe rpcd file.exec argument formats on the CU router using an ACL-allowed command."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cu_web  # noqa: E402

variants = [
    ("str+args", {"command": "/etc/init.d/cron", "args": ["reload"]}),
    ("array", {"command": ["/etc/init.d/cron", "reload"]}),
    ("str-space", {"command": "/etc/init.d/cron reload"}),
    ("str+params", {"command": "/etc/init.d/cron", "params": {"args": ["reload"]}}),
    ("syslog-str", {"command": "/usr/libexec/syslog-wrapper"}),
]

w = cu_web.CuWeb()
for name, args in variants:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "call",
               "params": [w.sid, "file", "exec", args]}
    r = w.s.post(cu_web.BASE + "/ubus", json=payload, timeout=30)
    print(f"== {name}: {r.text[:300]}")
