#!/usr/bin/env python3
"""Dump LuCI/ubus session ACLs on the CU router."""
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
print(json.dumps(res[1].get("acls", {}), ensure_ascii=False, indent=1)[:4000])
