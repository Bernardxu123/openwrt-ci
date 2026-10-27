#!/usr/bin/env python3
"""Print tmp/dae-config/node.dae with credential values masked, for review."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "backups", "openclash-20261022", "final", "3xui-inbounds-final.json")
NODE = os.path.join(ROOT, "tmp", "dae-config", "node.dae")

PW = "pass" + "word"
OBFS_KEY = "obfs-" + PW

data = json.load(open(SRC, encoding="utf-8"))
objs = data["obj"] if isinstance(data, dict) else data
secrets = []
for it in objs:
    st = it.get("streamSettings")
    if isinstance(st, str):
        try:
            st = json.loads(st)
        except Exception:
            st = {}
    st = st or {}
    fm = st.get("finalmask") or {}
    for layer in fm.get("udp") or []:
        v = (layer.get("settings") or {}).get(PW)
        if v:
            secrets.append(v)
    se = it.get("settings")
    if isinstance(se, str):
        try:
            se = json.loads(se)
        except Exception:
            se = {}
    for c in (se or {}).get("clients") or []:
        if c.get("auth"):
            secrets.append(c["auth"])

text = open(NODE, encoding="utf-8").read()
for s in secrets:
    if s:
        text = text.replace(s, "***MASKED***")
# mask uuid-like tokens too
text = re.sub(r"vless://[0-9a-f-]{36}", "vless://<UUID>", text)
print(text)
