#!/usr/bin/env python3
"""Query subscription updatedAt timestamps."""
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
  subscriptions {
    id
    tag
    link
    updatedAt
    cronEnable
    status
    info
  }
}
"""
data = post({"query": q}, tok)
for s in data.get("subscriptions") or []:
    print(f"- {s['tag']!r} (id={s['id']}) updatedAt={s['updatedAt']} status={s['status']!r} info={s['info']!r}")
