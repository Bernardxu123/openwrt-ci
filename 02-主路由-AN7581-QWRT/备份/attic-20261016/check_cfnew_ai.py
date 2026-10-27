#!/usr/bin/env python3
"""Query daed GraphQL: list all subscriptions and groups (with subs + nodes)."""
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
    cronExp
    cronEnable
    status
    info
  }
  groups {
    id
    name
    policy
    subscriptions {
      nameFilterRegex
      matchedCount
      subscription {
        id
        tag
        link
      }
    }
    nodes {
      id
      name
    }
  }
}
"""
data = post({"query": q}, tok)

print("===== SUBSCRIPTIONS =====")
for s in data.get("subscriptions") or []:
    print(f"- id={s['id']} tag={s['tag']!r} cron={s.get('cronEnable')}({s.get('cronExp')}) status={s.get('status')!r} info={s.get('info')!r}")
    print(f"    link={s.get('link')!r}")

print()
print("===== GROUPS =====")
for g in data.get("groups") or []:
    subs = g.get("subscriptions") or []
    nodes = g.get("nodes") or []
    print(f"* {g['name']} (id={g['id']}, policy={g.get('policy')})")
    print(f"    subs({len(subs)}):")
    for s in subs:
        sub = s.get("subscription") or {}
        print(f"      - sub={sub.get('tag')!r} (id={sub.get('id')}) filter={s.get('nameFilterRegex')!r} matched={s.get('matchedCount')}")
        print(f"        link={sub.get('link')!r}")
    print(f"    nodes({len(nodes)}):")
    for n in nodes:
        print(f"      - {n['name']}")
