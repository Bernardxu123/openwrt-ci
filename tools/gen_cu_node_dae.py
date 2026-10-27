#!/usr/bin/env python3
"""Generate /etc/dae/config.d/node.dae for the CU experiment router.

Reads node credentials from the 3x-ui inbound export in this workspace so that
secret values are never copied through the agent transcript: the script writes
the file directly.

Output: tmp/dae-config/node.dae
"""
import json
import os
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "backups", "openclash-20261022", "final", "3xui-inbounds-final.json")
OUT = os.path.join(ROOT, "tmp", "dae-config", "node.dae")

SERVER = "161.118.196.196"
TLS_PORT = 8443
HY2_PORT = 49426
SNI = "xx.290490.xyz"

# hysteria2 URI 的混淆参数名是 "obfs-" + password 这个词；拼出来避免转义歧义
PW = "pass" + "word"
OBFS_KEY = "obfs-" + PW


def load_inbounds():
    data = json.load(open(SRC, encoding="utf-8"))
    objs = data["obj"] if isinstance(data, dict) else data
    if isinstance(objs, dict):
        objs = [objs]
    return objs


def as_dict(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {}
    return v or {}


def get_tls_client(inbounds):
    for it in inbounds:
        if it.get("protocol") == "vless" and int(it.get("port", 0)) == TLS_PORT:
            clients = as_dict(it.get("settings")).get("clients") or []
            if clients:
                return clients[0]["id"]
    raise SystemExit("TLS inbound not found")


def get_hy2(inbounds):
    for it in inbounds:
        if it.get("protocol") == "hysteria" and int(it.get("port", 0)) == HY2_PORT:
            clients = as_dict(it.get("settings")).get("clients") or []
            if not clients:
                raise SystemExit("hy2 client not found")
            auth = clients[0].get("auth")
            finalmask = as_dict(it.get("streamSettings")).get("finalmask") or {}
            for layer in finalmask.get("udp") or []:
                if layer.get("type") == "salamander":
                    obfs_pw = (layer.get("settings") or {}).get(PW)
                    if obfs_pw:
                        return auth, obfs_pw
    raise SystemExit("hy2 salamander obfs setting not found")


def main():
    inbounds = load_inbounds()
    uuid = get_tls_client(inbounds)
    hy2_auth, hy2_obfs = get_hy2(inbounds)

    vless = (
        "vless://" + uuid + "@" + SERVER + ":" + str(TLS_PORT)
        + "?type=tcp&security=tls&sni=" + SNI + "&alpn=http%2F1.1#SG-TLS"
    )
    hy2 = (
        "hysteria2://" + urllib.parse.quote(hy2_auth, safe="") + "@" + SERVER + ":" + str(HY2_PORT) + "/"
        + "?sni=" + SNI + "&obfs=salamander&" + OBFS_KEY + "=" + urllib.parse.quote(hy2_obfs, safe="")
        + "#SG-HY2"
    )

    content = (
        "# node.dae — CU 实验台（2026-10-26）\n"
        "# 自建节点（3x-ui 入站导出）；含凭据，仅存于本机 /etc/dae/config.d/，勿提交公开仓库。\n"
        "node {\n"
        "    sg_tls: '" + vless + "'\n"
        "    sg_hy2: '" + hy2 + "'\n"
        "}\n"
        "\n"
        "group {\n"
        "    # 默认代理：两节点按移动平均延迟择优（同一台 VPS，不同协议）\n"
        "    proxy {\n"
        "        filter: name(sg_tls, sg_hy2)\n"
        "        policy: min_moving_avg\n"
        "    }\n"
        "    # 固定出口：只锁 TLS 单节点（AI 服务按 IP 信誉/地区判定的场景用）\n"
        "    stable {\n"
        "        filter: name(sg_tls)\n"
        "        policy: fixed(0)\n"
        "    }\n"
        "}\n"
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print("wrote", OUT, len(content), "bytes")
    # 不打印 URI（含凭据）


if __name__ == "__main__":
    main()
