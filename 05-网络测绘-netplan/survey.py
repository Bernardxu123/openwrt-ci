#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
survey.py — 双 AP 真实 RSSI 采集器

采集来源：
  · 主路由 192.168.31.1 (ponwrt)  — `iw dev <iface> station dump`
  · 小米 AP 192.168.31.158         — telnet + `iwinfo <iface> assoclist`

为什么不用手机 App 扫：
  · 浏览器读不到 WiFi RSSI（W3C Network Information API 至今没有把
    signalStrength 实现进任何主流浏览器）
  · 手机 App（NetSpot / WiFiman）能测，但只测「手机自己」一条链路，
    而且要靠人举着手机走一遍，坐标还得手画
  · 路由器侧读的是**每台已关联终端在每个 AP 上的真实 dBm**，
    两 AP 同时观测同一终端 -> 直接得到距离比，可以反解位置
    （见 locate.py）

用法：
  python survey.py                  # 采一轮
  python survey.py --watch 30       # 每 30 秒一轮
  python survey.py --probe 3        # 每轮采 3 次取中位数
  python survey.py --tag 客厅        # 打位置标签（人肉标注，可选）
"""
import argparse
import csv
import datetime as dt
import os
import re
import socket
import statistics
import sys
import time

import paramiko

ROUTER = dict(host="192.168.31.1", user="root", pwd="Qazswxdecf1")
AP = dict(host="192.168.31.158", user="root", pwd="admin")

# 路由器 iwinfo 接口 -> (显示名, 频段)
ROUTER_IFACES = {
    "phy0-ap0": ("ONT-2.4G", "2.4"),
    "phy1-ap0": ("ONT-5G", "5"),
}
# 小米 AP 接口 -> (显示名, 频段)
AP_IFACES = {
    "wl1": ("AP-2.4G", "2.4"),
    "wl0": ("AP-5G", "5"),
}

FIELDS = ["ts", "tag", "mac", "hostname", "ip", "band", "ap", "ssid",
          "channel", "width", "rssi", "snr", "tx_bitrate", "rx_bitrate"]


# ---------------------------------------------------------------- 路由器侧
def router_connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ROUTER["host"], username=ROUTER["user"], password=ROUTER["pwd"],
              look_for_keys=False, allow_agent=False, timeout=10)
    return c


def router_run(c, cmd, timeout=60):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", "replace")


def router_stations(c):
    """返回 {(iface, mac): {rssi, tx, rx, inactive}}"""
    res = {}
    for iface in ROUTER_IFACES:
        o = router_run(c, "iw dev %s station dump" % iface)
        cur = None
        for line in o.splitlines():
            m = re.match(r"Station ([0-9a-f:]{17})", line)
            if m:
                cur = {"mac": m.group(1).upper()}
                res[(iface, cur["mac"])] = cur
                continue
            if cur is None:
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
            elif s.startswith("inactive time:"):
                mm = re.search(r"(\d+)\s*ms", s)
                if mm:
                    cur["idle"] = int(mm.group(1))
    return res


def router_aps(c):
    """{iface: {ssid, channel, width}}"""
    o = router_run(c, "iw dev")
    out, cur = {}, None
    for line in o.splitlines():
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
            cur["channel"] = int(m.group(1))
            cur["width"] = int(m.group(3))
            out[cur["iface"]] = cur
            cur = None
    return out


def router_leases(c):
    info = {}
    for line in router_run(c, "cat /tmp/dhcp.leases 2>/dev/null").splitlines():
        p = line.split()
        if len(p) >= 4:
            info[p[1].upper()] = {"ip": p[2], "hostname": "" if p[3] == "*" else p[3]}
    return info


# ---------------------------------------------------------------- 小米 AP 侧
class TelnetShell:
    """极简 telnet 客户端（只做明文，够用）"""

    def __init__(self, host, user, pwd, timeout=10):
        self.sock = socket.socket()
        self.sock.settimeout(timeout)
        self.sock.connect((host, 23))
        time.sleep(1.4)
        self._drain()
        self.sock.sendall(user.encode() + b"\r\n")
        time.sleep(0.6)
        self._drain()
        self.sock.sendall(pwd.encode() + b"\r\n")
        time.sleep(1.4)
        self._drain()

    def _drain(self):
        try:
            while True:
                d = self.sock.recv(16384)
                if not d:
                    break
        except socket.timeout:
            pass
        except Exception:
            pass

    def cmd(self, c, wait=2.6):
        self._drain()
        self.sock.sendall(c.encode() + b"\r\n")
        time.sleep(wait)
        buf = b""
        try:
            while True:
                d = self.sock.recv(16384)
                if not d:
                    break
                buf += d
        except socket.timeout:
            pass
        return buf.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def ap_stations(sh):
    """解析 iwinfo assoclist 的表格，返回 {(iface, mac): {...}}"""
    res = {}
    for iface in AP_IFACES:
        o = sh.cmd("iwinfo %s assoclist" % iface)
        for line in o.splitlines():
            # 88:6C:60:1F:EE:60  be WPA2PSK -75 dBm -98 dBm  23  288M ...
            m = re.match(r"\s*([0-9A-Fa-f:]{17})\s+\S+\s+\S+\s+(-?\d+)\s*dBm\s+(-?\d+)\s*dBm\s+(-?\d+)", line)
            if not m:
                continue
            mac = m.group(1).upper()
            rest = line[m.end():].split()
            res[(iface, mac)] = {
                "mac": mac,
                "rssi": int(m.group(2)),
                "noise": int(m.group(3)),
                "snr": int(m.group(4)),
                "rx": rest[0] if rest else "",
                "tx": rest[5] if len(rest) > 5 else "",
            }
    return res


# ---------------------------------------------------------------- 汇总
def collect(probe=3):
    rc = router_connect()
    try:
        aps = router_aps(rc)
        leases = router_leases(rc)
        r_samples, r_meta = {}, {}
        for _ in range(probe):
            for k, v in router_stations(rc).items():
                if "rssi" in v:
                    r_samples.setdefault(k, []).append(v["rssi"])
                r_meta[k] = v
            time.sleep(0.4)
    finally:
        rc.close()

    ap_samples, ap_meta = {}, {}
    sh = None
    try:
        sh = TelnetShell(AP["host"], AP["user"], AP["pwd"])
        for _ in range(probe):
            for k, v in ap_stations(sh).items():
                ap_samples.setdefault(k, []).append(v["rssi"])
                ap_meta[k] = v
            time.sleep(0.4)
    except Exception as e:
        print("  [warn] 小米 AP 采集失败：%s" % e, file=sys.stderr)
    finally:
        if sh:
            sh.close()

    ts = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []
    for (iface, mac), vals in r_samples.items():
        name, band = ROUTER_IFACES[iface]
        ap = aps.get(iface, {})
        lease = leases.get(mac, {})
        med = int(statistics.median(vals))
        rows.append(dict(
            ts=ts, mac=mac, hostname=lease.get("hostname", ""), ip=lease.get("ip", ""),
            band=band, ap=name, ssid=ap.get("ssid", ""), channel=ap.get("channel", ""),
            width=ap.get("width", ""), rssi=med, snr=med + 92,
            tx_bitrate=r_meta[(iface, mac)].get("tx", ""),
            rx_bitrate=r_meta[(iface, mac)].get("rx", ""),
        ))
    for (iface, mac), vals in ap_samples.items():
        name, band = AP_IFACES[iface]
        lease = leases.get(mac, {})
        med = int(statistics.median(vals))
        rows.append(dict(
            ts=ts, mac=mac, hostname=lease.get("hostname", ""), ip=lease.get("ip", ""),
            band=band, ap=name, ssid="bernard" if band == "2.4" else "bernard_5G",
            channel=1 if band == "2.4" else 36,
            width=40 if band == "2.4" else 160,
            rssi=med, snr=ap_meta[(iface, mac)].get("snr", ""),
            tx_bitrate=ap_meta[(iface, mac)].get("tx", ""),
            rx_bitrate=ap_meta[(iface, mac)].get("rx", ""),
        ))
    rows.sort(key=lambda r: (r["ap"], -r["rssi"]))
    return rows


def append_csv(path, rows, tag=""):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            r["tag"] = tag
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser(description="采集双 AP 的真实 WiFi RSSI")
    ap.add_argument("--watch", type=int, default=0)
    ap.add_argument("--probe", type=int, default=3)
    ap.add_argument("--out", default="logs/survey.csv")
    ap.add_argument("--tag", default="", help="给这批数据打标签，如房间名")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    n = 0
    while True:
        n += 1
        rows = collect(probe=args.probe)
        append_csv(args.out, rows, args.tag)
        print("=" * 76)
        print("[%s] 第 %d 轮 · %d 条 · %s" % (
            dt.datetime.now().strftime("%H:%M:%S"), n, len(rows), args.out))
        cur = None
        for r in rows:
            if r["ap"] != cur:
                cur = r["ap"]
                print("  ── %s (ch%s/%sMHz) ──" % (cur, r["channel"], r["width"]))
            print("    %-30s %4d dBm  SNR %3s  %s" % (
                (r["hostname"] or r["mac"])[:30], r["rssi"], r["snr"], r["ip"]))
        if args.watch <= 0:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
