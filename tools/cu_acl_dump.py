#!/usr/bin/env python3
"""Dump the full ubus session ACL to a local file for inspection."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cu_web  # noqa: E402

web = cu_web.CuWeb()
payload = {"jsonrpc": "2.0", "id": 1, "method": "call",
           "params": ["00000000000000000000000000000000", "session", "login",
                      {"username": cu_web.USER, cu_web.PW: cu_web.PWD}]}
r = web.s.post(cu_web.BASE + "/ubus", json=payload)
res = r.json()["result"]
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "tmp", "cu-acl.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(res[1].get("acls", {}), fh, ensure_ascii=False, indent=1)
print("wrote", out)
