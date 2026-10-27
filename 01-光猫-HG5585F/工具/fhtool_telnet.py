#!/usr/bin/env python3
"""
开启烽火 HG5585F 的 Telnet（运行时），并回读 TelnetInfo 取口令。

只做两件事：
  1) POST /fh_tool/api  {"index":"1","func":"TelnetEnable","telnet":"1"}
  2) 只读 GetTelnetInfo 回读
不重启、不写 cfg_cmd 持久化开关、不碰 MTD 分区。

用法: python tools/fhtool_telnet.py [ip] [mac]
"""
import base64
import hashlib
import json
import socket
import sys
import time

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.1"
MAC = (sys.argv[2] if len(sys.argv) > 2 else "D069FF163280").upper().replace(":", "").replace("-", "")


def derive(mac):
    h = hashlib.sha256(mac.encode("ascii")).hexdigest()
    return ("".join(h[2 * i + 2] for i in range(16)).encode("ascii"),
            "".join(h[3 * i + 3] for i in range(16)).encode("ascii"))


KEY, IV = derive(MAC)
URL = f"http://{IP}/fh_tool/api"


def call(func, extra=None, quiet=False):
    payload = {"index": "1", "func": func}
    if extra:
        payload.update(extra)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body = base64.b64encode(AES.new(KEY, AES.MODE_CBC, IV).encrypt(pad(raw, 16))).decode()
    r = requests.post(URL, data=body.encode(),
                      headers={"Content-Type": "text/plain"}, timeout=8)
    if r.status_code != 200 or not r.content:
        return None, f"HTTP {r.status_code} {r.text[:120]!r}"
    try:
        dec = unpad(AES.new(KEY, AES.MODE_CBC, IV).decrypt(base64.b64decode(r.text)), 16)
        return json.loads(dec.decode("utf-8", "replace")), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}  raw={r.text[:120]!r}"


def port23_open(host, timeout=3):
    try:
        with socket.create_connection((host, 23), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                return True, s.recv(256)
            except socket.timeout:
                return True, b"(connected, no banner)"
    except Exception as e:
        return False, str(e)


print(f"目标 {IP}   MAC {MAC}")
print(f"key  {KEY.decode()}")
print(f"iv   {IV.decode()}\n")

print("=== 0) 开启前状态 ===")
o, e = port23_open(IP)
print(f"  TCP/23 {'OPEN' if o else 'closed'}  {e!r}")
d, e = call("GetTelnetInfo")
print(f"  GetTelnetInfo => {d if d else e}\n")

print("=== 1) TelnetEnable(telnet=1)  ===")
print("    请求明文: {\"index\":\"1\",\"func\":\"TelnetEnable\",\"telnet\":\"1\"}")
d, e = call("TelnetEnable", {"telnet": "1"})
if d is None:
    print(f"  失败: {e}")
    sys.exit(1)
print(f"  返回 => {d}")
if d.get("result") != 0:
    print("  result != 0，停止（按帖子：成功码不足以证明端口已开）")
    sys.exit(2)

print("\n=== 2) TCP/23 握手验证（最多重试 12 次）===")
opened = False
for i in range(12):
    time.sleep(1.5)
    o, banner = port23_open(IP)
    print(f"  [{i+1:2d}] {'OPEN' if o else 'closed'}  {banner!r}")
    if o:
        opened = True
        break

print("\n=== 3) 开启后 GetTelnetInfo 回读 ===")
d, e = call("GetTelnetInfo")
if d is None:
    print(f"  {e}")
else:
    for k, v in d.items():
        if k.startswith("info"):
            print(f"  {k} = {v!r}")
    print(f"  result = {d.get('result')}")
    print("\n  完整响应: " + json.dumps(d, ensure_ascii=False))

print("\n结论: " + ("Telnet 已开启" if opened else "API 返回成功但 TCP/23 未开 —— 按帖子这不算成功"))