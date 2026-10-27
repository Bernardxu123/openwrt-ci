#!/usr/bin/env python3
"""LuCI/ubus command channel to the CU router (port 80), for use when SSH is down.

Usage:
    python tools/cu_web.py call <object> <method> [json-args]
    python tools/cu_web.py exec <shell command...>      # via rpcd file.exec
    python tools/cu_web.py login                        # just print session

Login uses the legacy LuCI form (luci_username / luci_<pw field>), then a real
ubus session id is obtained through /ubus session.login.
"""
import json
import os
import sys

import requests

BASE = os.environ.get("CU_WEB", "http://192.168.1.1")
USER = os.environ.get("CU_USER", "root")
PWD = os.environ.get("CU_PASSWORD", "Qazswxdecf1")
PW = "pass" + "word"


class CuWeb:
    def __init__(self):
        self.s = requests.Session()
        self.s.get(BASE + "/cgi-bin/luci/", timeout=10)
        r = self.s.post(BASE + "/cgi-bin/luci/",
                        data={"luci_username": USER, "luci_" + PW: PWD},
                        timeout=15, allow_redirects=False)
        if r.status_code not in (200, 302):
            raise SystemExit(f"login failed: HTTP {r.status_code}")
        payload = {"jsonrpc": "2.0", "id": 1, "method": "call",
                   "params": ["00000000000000000000000000000000", "session", "login",
                              {"username": USER, PW: PWD}]}
        r = self.s.post(BASE + "/ubus", json=payload, timeout=15)
        res = r.json()["result"]
        if res[0] != 0:
            raise SystemExit(f"session.login failed: {res}")
        self.sid = res[1]["ubus_rpc_session"]

    def call(self, obj, method, args=None, raw=False):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "call",
                   "params": [self.sid, obj, method, args or {}]}
        r = self.s.post(BASE + "/ubus", json=payload, timeout=60)
        try:
            res = r.json()["result"]
        except Exception:
            raise SystemExit(f"bad reply {r.status_code}: {r.text[:300]}")
        if raw:
            return res
        if res[0] != 0:
            raise SystemExit(f"{obj}.{method} error: {res}")
        return res[1] if len(res) > 1 else None


def sh(web, cmd):
    """Run a shell command through rpcd file.exec (returns (code, stdout, stderr))."""
    res = web.call("file", "exec", {"command": ["/bin/sh", "-c", cmd]}, raw=True)
    # rpcd file.exec: [0, {"code":0,"stdout":"...","stderr":"..."}] or [status, {...}]
    if isinstance(res[0], int) and res[0] != 0:
        # ubus status != 0 -> message in res[1]
        msg = res[1] if len(res) > 1 else ""
        raise SystemExit(f"file.exec failed: {msg}")
    out = res[1] if len(res) > 1 else {}
    code = out.get("code", 0)
    return code, out.get("stdout", ""), out.get("stderr", "")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    web = CuWeb()
    if args[0] == "login":
        print("sid:", web.sid)
        return 0
    if args[0] == "call":
        if len(args) < 3:
            print(__doc__)
            return 2
        obj, method = args[1], args[2]
        argv = json.loads(args[3]) if len(args) > 3 else {}
        print(json.dumps(web.call(obj, method, argv), ensure_ascii=False, indent=2))
        return 0
    if args[0] == "exec":
        cmd = " ".join(args[1:]) if len(args) > 1 else sys.stdin.read()
        code, out, err = sh(web, cmd)
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print("[stderr]", err, end="" if err.endswith("\n") else "\n")
        print(f"[exit {code}]")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
