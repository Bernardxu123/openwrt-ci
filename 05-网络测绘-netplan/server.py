#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — 本地服务：把路由器实时信号喂给网页

为什么需要它
------------
浏览器读不到 WiFi 的 RSSI（W3C Network Information API 至今没有实现
signalStrength）。所以「点房间测当前信号」必须由服务端去问路由器：

    手机浏览器 --POST /api/measure?room=客厅--> 本服务
                                              |
                                              +--> 路由器 SSH: iw station dump
                                              +--> 小米 AP telnet: iwinfo assoclist
    手机浏览器 <---- {rssi:-58, ap:"ONT-5G", ch:149} ----+

服务端用请求的源 IP 反查 DHCP 租约，就能知道「是哪台设备在测」，
从而返回**你手里这台手机**的真实 RSSI。

用法
----
    cd netplan
    python server.py                 # 默认 http://0.0.0.0:8787
    python server.py --port 9000
    python server.py --no-ap         # 只读主路由，不连小米 AP（更快）

然后用手机浏览器打开 http://<本机局域网IP>:8787/
（手机和电脑要在同一个 WiFi 下）
"""
import argparse
import datetime as dt
import json
import os
import re
import socket
import socketserver
import statistics
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paramiko

ROUTER = dict(host="192.168.31.1", user="root", pwd="Qazswxdecf1")
AP = dict(host="192.168.31.158", user="root", pwd="admin")

ROUTER_IFACES = {"phy0-ap0": ("ONT-2.4G", "2.4"), "phy1-ap0": ("ONT-5G", "5")}
AP_IFACES = {"wl1": ("AP-2.4G", "2.4"), "wl0": ("AP-5G", "5")}

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_TTL = 1.6          # 秒，避免连点把路由器打爆
_cache = {"ts": 0, "data": None}
_lock = threading.Lock()


# ---------------------------------------------------------------- 路由器
def router_snapshot():
    """返回 {mac: {iface, ap, band, ssid, ch, width, rssi, snr, tx, rx}}"""
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ROUTER["host"], username=ROUTER["user"], password=ROUTER["pwd"],
              look_for_keys=False, allow_agent=False, timeout=8)
    try:
        # 接口信息
        out = c.exec_command("iw dev", timeout=15)[1].read().decode("utf-8", "replace")
        aps, cur = {}, None
        for line in out.splitlines():
            m = re.match(r"\s*Interface (\S+)", line)
            if m:
                cur = {"iface": m.group(1)}
                continue
            if not cur:
                continue
            m = re.match(r"\s*ssid (\S+)", line)
            if m:
                cur["ssid"] = m.group(1)
                continue
            m = re.match(r"\s*channel (\d+) \((\d+) MHz\), width: (\d+) MHz", line)
            if m:
                cur.update(ch=int(m.group(1)), width=int(m.group(3)))
                aps[cur["iface"]] = cur
                cur = None

        devs = {}
        for iface, (name, band) in ROUTER_IFACES.items():
            o = c.exec_command("iw dev %s station dump" % iface, timeout=15)[1].read().decode("utf-8", "replace")
            mac, cur = None, None
            for line in o.splitlines():
                m = re.match(r"Station ([0-9a-f:]{17})", line)
                if m:
                    mac = m.group(1).upper()
                    cur = {"mac": mac, "iface": iface, "ap": name, "band": band,
                           "ssid": aps.get(iface, {}).get("ssid", ""),
                           "ch": aps.get(iface, {}).get("ch"),
                           "width": aps.get(iface, {}).get("width")}
                    devs.setdefault(mac, []).append(cur)
                    continue
                if not cur:
                    continue
                s = line.strip()
                if s.startswith("signal:"):
                    mm = re.search(r"(-?\d+)\s*(\[|dBm)", s)
                    if mm:
                        cur["rssi"] = int(mm.group(1))
                elif s.startswith("tx bitrate:"):
                    mm = re.search(r"([\d.]+)\s*MBit/s", s)
                    if mm:
                        cur["tx"] = float(mm.group(1))
                elif s.startswith("rx bitrate:"):
                    mm = re.search(r"([\d.]+)\s*MBit/s", s)
                    if mm:
                        cur["rx"] = float(mm.group(1))
        return devs
    finally:
        c.close()


def router_leases():
    """{ip: mac}, {mac: hostname}"""
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ROUTER["host"], username=ROUTER["user"], password=ROUTER["pwd"],
              look_for_keys=False, allow_agent=False, timeout=8)
    try:
        o = c.exec_command("cat /tmp/dhcp.leases", timeout=10)[1].read().decode("utf-8", "replace")
        ip2mac, mac2name = {}, {}
        for line in o.splitlines():
            p = line.split()
            if len(p) >= 4:
                mac2name[p[1].upper()] = "" if p[3] == "*" else p[3]
                ip2mac[p[2]] = p[1].upper()
        return ip2mac, mac2name
    finally:
        c.close()


# ---------------------------------------------------------------- 小米 AP
class TelnetShell:
    def __init__(self, host, user, pwd, timeout=8):
        self.sock = socket.socket()
        self.sock.settimeout(timeout)
        self.sock.connect((host, 23))
        time.sleep(1.2)
        self._drain()
        self.sock.sendall(user.encode() + b"\r\n")
        time.sleep(0.5)
        self._drain()
        self.sock.sendall(pwd.encode() + b"\r\n")
        time.sleep(1.2)
        self._drain()

    def _drain(self, quiet=0.25, maxt=1.5):
        """读到「安静 quiet 秒」为止，而不是等到 socket 超时"""
        self.sock.settimeout(quiet)
        t0 = time.time()
        while time.time() - t0 < maxt:
            try:
                if not self.sock.recv(65536):
                    break
            except socket.timeout:
                break
            except Exception:
                break

    def cmd(self, c, wait=2.0):
        """发命令 + 读回显，用哨兵标记判断读完，避免干等超时"""
        self._drain()
        marker = "__DONE_%d__" % (time.time_ns() % 1000000)
        self.sock.settimeout(wait)
        self.sock.sendall((c + "; echo " + marker + "\r\n").encode())
        buf = b""
        t0 = time.time()
        while time.time() - t0 < wait + 1.0:
            try:
                d = self.sock.recv(65536)
                if not d:
                    break
                buf += d
                if marker.encode() in buf:
                    break
            except socket.timeout:
                break
            except Exception:
                break
        self.sock.settimeout(8)
        return buf.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def ap_snapshot():
    out = {}
    sh = None
    try:
        sh = TelnetShell(AP["host"], AP["user"], AP["pwd"])
        for iface, (name, band) in AP_IFACES.items():
            o = sh.cmd("iwinfo %s assoclist" % iface, wait=3.0)
            ch = None
            mm = re.search(r"channel:\s*(\d+)", o)
            if mm:
                ch = int(mm.group(1))
            for line in o.splitlines():
                m = re.match(r"\s*([0-9A-Fa-f:]{17})\s+\S+\s+\S+\s+(-?\d+)\s*dBm\s+(-?\d+)\s*dBm\s+(-?\d+)", line)
                if not m:
                    continue
                mac = m.group(1).upper()
                out.setdefault(mac, []).append({
                    "mac": mac, "iface": iface, "ap": name, "band": band,
                    "ssid": "bernard" if band == "2.4" else "bernard_5G",
                    "ch": ch, "width": 40 if band == "2.4" else 160,
                    "rssi": int(m.group(2)), "snr": int(m.group(4)),
                })
    except Exception as e:
        print("  [warn] 小米 AP:", e, file=sys.stderr)
    finally:
        if sh:
            sh.close()
    return out


# ---------------------------------------------------------------- 汇总
def snapshot(force=False, with_ap=True):
    with _lock:
        now = time.time()
        if not force and _cache["data"] and now - _cache["ts"] < CACHE_TTL:
            return _cache["data"]
        devs = router_snapshot()
        if with_ap:
            for mac, lst in ap_snapshot().items():
                devs.setdefault(mac, []).extend(lst)
        ip2mac, mac2name = router_leases()
        data = {"ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "devices": devs, "ip2mac": ip2mac, "mac2name": mac2name}
        _cache.update(ts=now, data=data)
        return data


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "netplan/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            return          # 静音 API 日志
        sys.stderr.write("  %s\n" % (fmt % args))

    # ---------- 工具 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self._json({"error": "not found: " + path}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self):
        return self.client_address[0]

    # ---------- 路由 ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        qs = urllib.parse.parse_qs(u.query)

        if path in ("/", "/index.html"):
            self._file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")
            return
        if path == "/api/ping":
            self._json({"ok": True, "lan": lan_ip(),
                        "client": self._client_ip(), "ts": dt.datetime.now().isoformat(timespec="seconds")})
            return

        if path == "/api/live":
            try:
                d = snapshot(force=qs.get("fresh", ["0"])[0] == "1")
            except Exception as e:
                self._json({"error": str(e)}, 500)
                return
            self._json(build_live(d))
            return

        if path == "/api/measure":
            room = qs.get("room", [""])[0]
            try:
                d = snapshot(force=True)
            except Exception as e:
                self._json({"error": str(e)}, 500)
                return
            self._json(build_measure(d, self._client_ip(), room))
            return

        self._json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if u.path == "/api/measure":
            try:
                body = json.loads(raw or b"{}")
            except Exception:
                body = {}
            try:
                d = snapshot(force=True)
            except Exception as e:
                self._json({"error": str(e)}, 500)
                return
            self._json(build_measure(d, self._client_ip(), body.get("room", "")))
            return
        self._json({"error": "not found"}, 404)


def build_live(d):
    """全部设备，按 MAC 归并（同一台设备在多 AP 的观测并列）"""
    out = []
    for mac, obs in d["devices"].items():
        obs = [o for o in obs if "rssi" in o]
        if not obs:
            continue
        obs.sort(key=lambda o: -o["rssi"])
        best = obs[0]
        out.append({
            "mac": mac,
            "name": d["mac2name"].get(mac, "") or mac,
            "obs": [{"ap": o["ap"], "band": o["band"], "rssi": o["rssi"],
                     "ch": o.get("ch"), "width": o.get("width"),
                     "snr": o.get("snr"), "tx": o.get("tx"), "rx": o.get("rx")} for o in obs],
            "best": {"ap": best["ap"], "band": best["band"], "rssi": best["rssi"],
                     "ch": best.get("ch"), "width": best.get("width")},
        })
    out.sort(key=lambda x: -x["best"]["rssi"])
    return {"ts": d["ts"], "lan": lan_ip(), "count": len(out), "devices": out}


def build_measure(d, client_ip, room):
    """定位「发起请求的那台设备」并返回它的完整观测"""
    # 本机回环 = 在电脑上自己点，路由器看不到这个源 IP
    if client_ip in ("127.0.0.1", "::1"):
        return {
            "ts": d["ts"], "room": room, "client_ip": client_ip,
            "matched": False, "device": None, "loopback": True,
            "hint": "当前是在本机浏览器点的，路由器看不到 127.0.0.1。"
                    "请用手机打开 http://%s:端口/ 再点，才能测到手机自己的信号。"
                    % lan_ip(),
        }
    mac = d["ip2mac"].get(client_ip)
    dev = None
    if mac and mac in d["devices"]:
        obs = [o for o in d["devices"][mac] if "rssi" in o]
        if obs:
            obs.sort(key=lambda o: -o["rssi"])
            dev = {
                "mac": mac,
                "name": d["mac2name"].get(mac, "") or mac,
                "obs": [{"ap": o["ap"], "band": o["band"], "rssi": o["rssi"],
                         "ch": o.get("ch"), "width": o.get("width"),
                         "snr": o.get("snr"), "tx": o.get("tx"), "rx": o.get("rx")} for o in obs],
            }
    return {
        "ts": d["ts"], "room": room, "client_ip": client_ip,
        "matched": dev is not None,
        "device": dev,
        "hint": None if dev else
                ("没在路由器上找到 %s 对应的设备。可能它刚重连、用了随机 MAC、"
                 "或连的是 MIoT 隔离 SSID。稍等 2 秒再点一次。" % client_ip),
    }


def main():
    ap = argparse.ArgumentParser(description="本地服务：路由器实时信号 -> 网页")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--no-ap", action="store_true", help="不连小米 AP（更快）")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.no_ap:
        AP_IFACES.clear()

    ip = lan_ip()
    print("=" * 64)
    print(" 户型网络规划器 · 本地服务")
    print("=" * 64)
    print(" 本机:    http://localhost:%d/" % args.port)
    print(" 手机:    http://%s:%d/   <- 用手机浏览器打开这个" % (ip, args.port))
    print(" 路由器:  %s" % ROUTER["host"])
    print(" 小米 AP: %s%s" % (AP["host"], "（已禁用）" if args.no_ap else ""))
    print()
    print(" 手机上点房间标记即可记录当前信号。Ctrl+C 停止。")
    print("=" * 64)

    # 启动时先探一次，早发现连不上
    try:
        d = snapshot(force=True)
        print(" [ok] 已连接，当前 %d 台设备在线" % len(d["devices"]))
    except Exception as e:
        print(" [warn] 首次探测失败：%s" % e)
        print("        服务仍会启动，但 /api/* 会返回错误。")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
