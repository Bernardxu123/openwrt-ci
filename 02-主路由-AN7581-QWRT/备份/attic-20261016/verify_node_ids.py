#!/usr/bin/env python3
"""Verify node IDs in AI group match cfnew subscription nodes."""
import json
import sys
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://192.168.31.1:2023/graphql"


def post(body, tok=None):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = tok
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=headers)
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if r.get("errors"):
        print("ERRORS:", r["errors"])
    return r.get("data")


tok = post({"query": '{ token(username:"root", password:"Qazswxdecf1") }'})["token"]

q = """
{
  groups {
    name
    nodes { id name }
  }
}
"""
data = post({"query": q}, tok)
cfnew_ids = {"Y3Vyc29yMTk3OA", "Y3Vyc29yMTk3OQ", "Y3Vyc29yMTk0MA", "Y3Vyc29yMTk0MQ"}
for g in data.get("groups") or []:
    hits = [n for n in (g.get("nodes") or []) if n["id"] in cfnew_ids]
    if hits:
        print(f"group {g['name']}: " + ", ".join(f"{n['name']}(id={n['id']})" for n in hits))
    else:
        print(f"group {g['name']}: (no cfnew-origin nodes)")
