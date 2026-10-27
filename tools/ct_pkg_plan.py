#!/usr/bin/env python3
"""Analyse opkg status: reverse dependencies + sizes for a candidate removal set.

Usage: python tools/ct_pkg_plan.py <status_file> [candidate1 candidate2 ...]
With no candidates, prints packages grouped by category for review.
"""
import re
import sys

CATEGORIES = {
    "cell/modem": r"qmodem|quectel|modem|sms|ubus-at-daemon|libqmodem|tom_modem",
    "usb stack": r"^kmod-usb|^usbutils$|^usbmuxd$|libusbmuxd|libimobiledevice|libplist|^libusb-1\.0-0$|^libeudev$",
    "IPTV/multicast": r"iptv|msd_lite|rtp2httpd|udpxy|igmpproxy|xupnpd|minidlna",
    "vlmcsd/KMS": r"vlmcsd",
    "zerotier": r"zerotier",
    "extra proxy": r"ssr-plus|shadowsocksr|xray-core|3proxy|microsocks|openvpn",
    "samba/ftp": r"samba|vsftpd|ksmbd|cifs",
    "upnp": r"upnp|natpmp",
    "other": r"arpbind|autoreboot|hd_idle|diskman|filetransfer|ipv6set|cpufreq|client-history|ramfree|oui",
}


def parse(path):
    pkgs = {}
    cur = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("Package: "):
            cur = line[10:].strip()
            pkgs[cur] = {"deps": [], "size": 0, "files": []}
        elif cur:
            if line.startswith("Depends: "):
                pkgs[cur]["deps"] = [d.split("(")[0].strip() for d in line[9:].split(",")]
            elif line.startswith("Installed-Size: "):
                pkgs[cur]["size"] = int(line[16:].strip() or 0)
            elif line.strip() == "":
                cur = None
    return pkgs


def main():
    pkgs = parse(sys.argv[1])
    cands = sys.argv[2:]
    if not cands:
        for name, pat in CATEGORIES.items():
            hits = sorted(p for p in pkgs if re.search(pat, p, re.I))
            total = sum(pkgs[p]["size"] for p in hits)
            print(f"\n== {name}  ({len(hits)} 包, {total/1024:.0f} KB)")
            print("   " + " ".join(hits))
        print(f"\n总计已安装: {len(pkgs)} 包, {sum(p['size'] for p in pkgs.values())/1024:.0f} KB")
        return

    # removal closure + reverse deps check
    remove = set()
    stack = list(cands)
    while stack:
        p = stack.pop()
        if p in remove or p not in pkgs:
            continue
        remove.add(p)
        stack.extend(pkgs[p]["deps"])

    remaining = {p: v for p, v in pkgs.items() if p not in remove}
    broken = {}
    for p, v in remaining.items():
        missing = [d for d in v["deps"] if d in remove]
        if missing:
            broken[p] = missing

    print(f"计划删除 {len(remove)} 包，释放约 {sum(pkgs[p]['size'] for p in remove)/1024:.0f} KB")
    print(f"连带删除: {' '.join(sorted(remove))}")
    if broken:
        print("\n!! 被其他包依赖，需保留或一并删除:")
        for p, m in broken.items():
            print(f"   {p} 需要 {m}")
    else:
        print("\n没有其他包依赖这些包，可安全删除。")


if __name__ == "__main__":
    main()
