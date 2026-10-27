#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HG5585F-CT 专用 /fh_tool/api 小工具（只读优先，可审计版）。

用途
----
1) 探测烽火私有维护接口（默认按 8080 → 80 顺序试；CT V2 的 Web/API 默认在 8080）
2) 读 GetDevInfo / GetTelnetInfo
3) 可选：开运行时 Telnet（不持久化、不重启）
4) 不给 MAC 时，自动从设备的 `web_get_brmad` 接口读取（只读，无鉴权）

用法
----
    python fhtool-ct.py 192.168.1.1                       # 自动读 MAC + 只读探测
    python fhtool-ct.py 192.168.1.1 --telnet-on           # 自动读 MAC + 开运行时 Telnet
    python fhtool-ct.py 192.168.1.1 A1B2C3D4E5F6          # 手动给 MAC
    python fhtool-ct.py 192.168.1.1 A1B2C3D4E5F6 --port 80

依赖：requests、pycryptodome
说明：AES 密钥由 MAC 派生，只是报文编码，不是身份认证；仅限自家 LAN 使用。
安全：本脚本只做 GetTelnetInfo / GetDevInfo / TelnetEnable(运行时)；
      不做 cfg_cmd 持久化、不下载、不扫描。持久化需求见 分析/共享资料评估.md。
"""
import argparse
import base64
import hashlib
import json
import re
import socket
import sys
import time

try:
    import requests
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    print("缺少依赖：pip install requests pycryptodome", file=sys.stderr)
    raise SystemExit(2)


def derive(mac12: str):
    """与既有 CU 工具相同算法：sha256(12位HEX) → key/iv 各取 16 个 ASCII 字符。"""
    h = hashlib.sha256(mac12.encode("ascii")).hexdigest()
    key = "".join(h[2 * i + 2] for i in range(16)).encode("ascii")
    iv = "".join(h[3 * i + 3] for i in range(16)).encode("ascii")
    return key, iv


def call(ip: str, port: int, key: bytes, iv: bytes, func: str, extra: dict | None = None):
    payload = {"index": "1", "func": func}
    if extra:
        payload.update(extra)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body = base64.b64encode(AES.new(key, AES.MODE_CBC, iv).encrypt(pad(raw, 16))).decode()
    url = f"http://{ip}:{port}/fh_tool/api"
    r = requests.post(url, data=body.encode(), headers={"Content-Type": "text/plain"}, timeout=8)
    if r.status_code != 200 or not r.content:
        raise RuntimeError(f"HTTP {r.status_code} body={r.text[:120]!r}")
    dec = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(base64.b64decode(r.text)), 16)
    return json.loads(dec.decode("utf-8", "replace"))


def port23_open(ip: str, timeout: float = 3.0):
    try:
        with socket.create_connection((ip, 23), timeout=timeout):
            return True
    except OSError:
        return False


def read_mac_from_web(ip: str, ports):
    """只读：从设备的 web_get_brmad 接口取 MAC（CT V2 工具同款做法）。

    该接口无鉴权，返回 JSON，字段 .brmad 为 12 位 HEX MAC。
    """
    last_err = None
    for port in ports:
        url = f"http://{ip}:{port}/cgi-bin/ajax?ajaxmethod=web_get_brmad"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code != 200:
                last_err = f":{port} HTTP {r.status_code}"
                continue
            data = r.json()
            mac = str(data.get("brmad", "")).upper().replace(":", "").replace("-", "")
            if re.fullmatch(r"[0-9A-F]{12}", mac):
                print(f"MAC    : {mac}  （自动读取 @ :{port}/web_get_brmad）")
                return mac, port
            last_err = f":{port} 返回的 brmad 不是 12 位 HEX：{data!r}"
        except Exception as e:
            last_err = f":{port} {type(e).__name__}: {e}"
    print(f"[警告] 自动读 MAC 失败（{last_err}）；请手动传 MAC 参数", file=sys.stderr)
    return None, None


def main():
    ap = argparse.ArgumentParser(description="HG5585F-CT /fh_tool/api 工具（可审计版）")
    ap.add_argument("ip", nargs="?", default="192.168.1.1")
    ap.add_argument("mac", nargs="?", help="MAC 12 位 HEX（可含 : 或 -）；省略则自动从 web_get_brmad 读")
    ap.add_argument("--port", type=int, choices=[80, 8080], help="固定端口；默认 8080→80 自动探测")
    ap.add_argument("--telnet-on", action="store_true", help="写操作：开启运行时 Telnet")
    a = ap.parse_args()

    ports = [a.port] if a.port else [8080, 80]
    mac = None
    if a.mac:
        mac = a.mac.upper().replace(":", "").replace("-", "").replace(" ", "")
        if len(mac) != 12 or any(c not in "0123456789ABCDEF" for c in mac):
            print(f"[错误] MAC 必须是 12 位 HEX，收到 {a.mac!r}", file=sys.stderr)
            return 2
    else:
        mac, web_port = read_mac_from_web(a.ip, ports)
        if not mac:
            print("[错误] 无法自动获取 MAC；请手动传 MAC（贴纸/后台设备信息）", file=sys.stderr)
            return 2
        if web_port and not a.port:
            ports = [web_port]

    key, iv = derive(mac)
    print(f"目标   : {a.ip}")
    print(f"MAC    : {mac}")
    print(f"key/iv : {key.decode()} / {iv.decode()}")

    working = None
    dev = None
    for port in ports:
        print(f"\n--- 探测 {a.ip}:{port} ---")
        try:
            dev = call(a.ip, port, key, iv, "GetDevInfo")
            working = port
            break
        except Exception as e:
            print(f"  GetDevInfo 失败：{type(e).__name__}: {e}")

    if working is None:
        print("\n[结论] 8080/80 都没有可用响应。先确认 Web 后台能打开、MAC 正确。", file=sys.stderr)
        return 1

    print(f"\n--- GetDevInfo @ {working} ---")
    print(json.dumps(dev, ensure_ascii=False, indent=2))

    # GetTelnetInfo 不是所有固件都有（CT V2 的共享工具就不调它），失败不影响主流程
    print(f"\n--- GetTelnetInfo @ {working}（可选）---")
    try:
        info = call(a.ip, working, key, iv, "GetTelnetInfo")
        print(json.dumps(info, ensure_ascii=False))
    except Exception as e:
        print(f"  不可用（可忽略）：{type(e).__name__}: {e}")

    if a.telnet_on:
        print(f"\n--- TelnetEnable @ {working} ---")
        try:
            res = call(a.ip, working, key, iv, "TelnetEnable", {"telnet": "1"})
            print("  TelnetEnable:", json.dumps(res, ensure_ascii=False))
        except Exception as e:
            print(f"  写调用失败：{type(e).__name__}: {e}")
            return 1
        time.sleep(1.0)
        print("  TCP 23 可连：", "是" if port23_open(a.ip) else "否")
        print("  登录候选（CT V2 默认）：telnetadmin / 'FH-nE7jA%5m' + MAC 后六位")
        print("  登录候选（CU/旧固件）：admin / 'Fh@' + MAC 后六位（末位 0/无效时试 +1）")
        print("  只开了运行时 Telnet；需要重启后保持，见 分析/共享资料评估.md 的 cfg_cmd 两路径")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        import os
        os.system("chcp 65001 > nul")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
