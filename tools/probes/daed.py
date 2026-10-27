#!/usr/bin/env python3
"""Minimal daed GraphQL helper for the router."""
import json
import sys
import urllib.request

BASE = "http://192.168.31.1:2023/graphql"
USER = "root"
PASS = "Qazswxdecf1"

_token = None


def gql(query, token=None, timeout=90, variables=None):
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def token():
    global _token
    if _token is None:
        res = gql('{ token(username: "%s", password: "%s") }' % (USER, PASS))
        _token = res["data"]["token"]
    return _token


def call(query, label=""):
    """Run an authenticated query/mutation; print and return the parsed result."""
    res = gql(query, token())
    tag = ("[%s] " % label) if label else ""
    if "errors" in res:
        print(tag + "ERRORS: " + json.dumps(res["errors"], ensure_ascii=False))
    elif "data" in res:
        print(tag + json.dumps(res["data"], ensure_ascii=False)[:3000])
    else:
        print(tag + json.dumps(res, ensure_ascii=False)[:3000])
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(call(sys.argv[1] if len(sys.argv) > 1 else "{ general { dae { version } } }"),
                     ensure_ascii=False, indent=2))
