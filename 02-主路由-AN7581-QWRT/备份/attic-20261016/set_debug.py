#!/usr/bin/env python3
"""临时把 daed logLevel 改为 debug（排查 YouTube 播放中断用），用完立即调回 info。"""
import json
import urllib.request

BASE = "http://192.168.31.1:2023/graphql"


def post(body, tok=None):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = tok
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=headers)
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if r.get("errors"):
        raise SystemExit(json.dumps(r["errors"], ensure_ascii=False)[:300])
    return r.get("data")


tok = post({"query": '{ token(username:"root", password:"Qazswxdecf1") }'})["token"]
c = post({"query": "{ configs(selected: true) { id global { logLevel } } }"}, tok)["configs"][0]
print("当前 logLevel =", c["global"]["logLevel"])

full = post({"query": "{ configs(selected: true) { global { logLevel tcpCheckUrl udpCheckDns checkInterval } } }"}, tok)["configs"][0]["global"]
full["logLevel"] = "debug"
res = post({"query": "mutation($id: ID!, $g: globalInput!) { updateConfig(id: $id, global: $g) { id } }",
            "variables": {"id": c["id"], "g": full}}, tok)
print("updateConfig =>", json.dumps(res, ensure_ascii=False)[:120])
print("run =>", post({"query": "mutation { run(dry: false) }"}, tok))
print("核对 =>", post({"query": "{ configs(selected: true) { global { logLevel } } }"}, tok))
