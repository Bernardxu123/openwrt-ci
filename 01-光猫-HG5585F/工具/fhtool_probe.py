#!/usr/bin/env python3
"""
只读探测：验证烽火 /fh_tool/api 私有接口在 HG5585F(CU, WKE2.094.906/V03.00.M0000) 上是否存在且报文格式正确。

严格只读：只调用 GetTelnetInfo / GetDevInfo，不发送任何写方法（TelnetEnable 等）。
用法: python tools/fhtool_probe.py [ip] [mac]
"""
import base64
import hashlib
import json
import sys

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.1"
MAC = (sys.argv[2] if len(sys.argv) > 2 else "D069FF163280").upper().replace(":", "").replace("-", "")


def derive(mac: str):
    h = hashlib.sha256(mac.encode("ascii")).hexdigest()  # 64 个小写 hex
    key = "".join(h[2 * i + 2] for i in range(16)).encode("ascii")
    iv = "".join(h[3 * i + 3] for i in range(16)).encode("ascii")
    return key, iv


KEY, IV = derive(MAC)


def call(func: str, extra: dict | None = None, ports=(80, 8080)):
    payload = {"index": "1", "func": func}
    if extra:
        payload.update(extra)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body = base64.b64encode(AES.new(KEY, AES.MODE_CBC, IV).encrypt(pad(raw, 16))).decode()
    print(f"\n--- {func} @ {IP} ---")
    print(f"  key  = {KEY.decode()}")
    print(f"  iv   = {IV.decode()}")
    print(f"  明文 = {raw.decode()}")
    print(f"  b64  = {body}")
    for port in ports:
        url = f"http://{IP}:{port}/fh_tool/api"
        try:
            r = requests.post(url, data=body.encode(),
                              headers={"Content-Type": "text/plain"}, timeout=8)
        except Exception as e:
            print(f"  :{port}  连接失败 -> {type(e).__name__}")
            continue
        print(f"  :{port}  HTTP {r.status_code}  len={len(r.content)}  ct={r.headers.get('Content-Type')}")
        if r.status_code != 200 or not r.content:
            print(f"        body={r.text[:200]!r}")
            continue
        try:
            dec = unpad(AES.new(KEY, AES.MODE_CBC, IV).decrypt(base64.b64decode(r.text)), 16)
            print(f"        解密 => {dec.decode('utf-8', 'replace')}")
        except Exception as e:
            print(f"        解密失败 {type(e).__name__}: {e}  raw={r.text[:120]!r}")


print(f"MAC      = {MAC}")
print(f"key      = {KEY.decode()}")
print(f"iv       = {IV.decode()}")
print(f"(校验: AES key/iv 各 16 个 ASCII 字节, AES-128-CBC + PKCS#7)")

call("GetTelnetInfo")
call("GetDevInfo")