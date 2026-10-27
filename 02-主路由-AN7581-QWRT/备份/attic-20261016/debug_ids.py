#!/usr/bin/env python3
"""Debug: print repr of AI group SG node IDs vs cfnew sub SG node IDs."""
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
  groups { name nodes { id name } }
  subscriptions { tag nodes { edges { id name } } }
}
"""
data = post({"query": q}, tok)

print("== AI group SG/HK nodes (repr) ==")
for g in data["groups"]:
    if g["name"] == "AI":
        for n in g["nodes"]:
            if "SG" in n["name"] or "HK" in n["name"]:
                print(f"  {n['name']!r} id={n['id']!r}")

print("== cfnew sub nodes (repr) ==")
for s in data["subscriptions"]:
    if s["tag"] == "cfnew":
        for e in s["nodes"]["edges"]:
            print(f"  {e['name']!r} id={e['id']!r}")
