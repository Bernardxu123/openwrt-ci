#!/usr/bin/env python3
"""Introspect daed GraphQL types: Subscription, Group, GroupSubscription."""
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
  gs: __type(name: "GroupSubscription") {
    fields { name type { name kind ofType { name kind } } }
  }
}
"""
data = post({"query": q}, tok)
print(json.dumps(data, indent=1, ensure_ascii=False))
