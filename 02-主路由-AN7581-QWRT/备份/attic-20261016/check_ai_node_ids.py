#!/usr/bin/env python3
"""Find all nodes named SG-* / HK-* with their IDs, and AI group node IDs."""
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
for g in data.get("groups") or []:
    if g["name"] != "AI":
        continue
    print("== AI group nodes ==")
    for n in g.get("nodes") or []:
        print(f"   - {n['name']} (id={n['id']})")
