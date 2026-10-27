#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载光猫刷机所需物料到 光猫-HG5585F/downloads/

家宽到 GitHub 有间歇性 TLS EOF / DNS 抖动（AGENTS.md §三 记过同类症状），
所以每个 URL 走「多次重试 + 指数退避 + 断点续传」，失败会明确报出来。

用法:
    python 光猫-HG5585F/tools/fetch_flash_files.py            # 全下
    python 光猫-HG5585F/tools/fetch_flash_files.py --list     # 只列清单
    python 光猫-HG5585F/tools/fetch_flash_files.py --only cu   # 只下 CU
"""
import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "downloads")

UBOOT_REPO = "pbs05/uboot-an758x"
STOCK2UBI_REPO = "pbs05/an758x-stock2ubi"

# 需要的物料：两种机型都下（CU 在用，CT 是备胎/试刀机）
# ⚠️ release 里的资产名用【连字符】 hg5585f-cu，不是 ponwrt profile 的下划线 hg5585f_cu
WANT_UBOOT = [
    "an7581-fiberhome-hg5585f-cu-preloader.bin",
    "an7581-fiberhome-hg5585f-cu-firstblock.bin",
    "an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    "an7581-fiberhome-hg5585f-ct-preloader.bin",
    "an7581-fiberhome-hg5585f-ct-firstblock.bin",
    "an7581-fiberhome-hg5585f-ct-bl31-u-boot.fip",
]

CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(url, tries=10, timeout=40):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()
        except Exception as e:                     # noqa: BLE001
            last = e
            wait = min(2 ** i, 20)
            print("      重试 %d/%d  %s: %s" % (i + 1, tries, type(e).__name__, str(e)[:50]))
            time.sleep(wait)
    raise RuntimeError("%s 取不到：%s" % (url, last))


def api(repo, path=""):
    return json.loads(fetch("https://api.github.com/repos/" + repo + path).decode("utf-8"))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="只列清单不下")
    ap.add_argument("--only", choices=["cu", "ct", "both"], default="both")
    a = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    manifest = {"uboot": {}, "stock2ubi": {}}

    # ---- uboot-an758x release ----
    print("== 查 %s 最新 release ==" % UBOOT_REPO)
    rel = api(UBOOT_REPO, "/releases/latest")
    print("   tag = %s   发布于 %s" % (rel["tag_name"], rel.get("published_at")))
    manifest["uboot_tag"] = rel["tag_name"]
    want = list(WANT_UBOOT)
    if a.only == "cu":
        want = [w for w in want if "-cu-" in w]
    elif a.only == "ct":
        want = [w for w in want if "-ct-" in w]

    by_name = {x["name"]: x for x in rel["assets"]}
    print("   release 内共 %d 个资产，目标 %d 个" % (len(by_name), len(want)))
    for name in want:
        if name not in by_name:
            print("   [缺] %s  —— 该 release 没有这个资产" % name)
            continue
        a_ = by_name[name]
        print("   -> %-52s %8.1f KB" % (name, a_["size"] / 1024))
        manifest["uboot"][name] = {"url": a_["browser_download_url"],
                                   "size": a_["size"]}
    if a.list:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    print("\n== 下载 U-Boot 物料 ==")
    for name, m in manifest["uboot"].items():
        dest = os.path.join(OUT, name)
        if os.path.exists(dest) and os.path.getsize(dest) == m["size"]:
            print("   [已有] %s" % name)
            continue
        print("   下载 %s" % name)
        data = fetch(m["url"])
        with open(dest, "wb") as f:
            f.write(data)
        print("      %d 字节  sha256=%s" % (len(data), sha256(data)))
        if len(data) != m["size"]:
            print("      [警告] 大小与 release 标称不一致！")

    # ---- an758x-stock2ubi ----
    print("\n== 查 %s 最新 release ==" % STOCK2UBI_REPO)
    rel2 = api(STOCK2UBI_REPO, "/releases/latest")
    print("   tag = %s   发布于 %s" % (rel2["tag_name"], rel2.get("published_at")))
    manifest["stock2ubi_tag"] = rel2["tag_name"]
    for a_ in rel2["assets"]:
        print("   -> %-52s %8.1f KB" % (a_["name"], a_["size"] / 1024))
        manifest["stock2ubi"][a_["name"]] = {"url": a_["browser_download_url"],
                                             "size": a_["size"]}
        dest = os.path.join(OUT, a_["name"])
        if os.path.exists(dest) and os.path.getsize(dest) == a_["size"]:
            print("      [已有] %s" % a_["name"])
            continue
        print("      下载 %s" % a_["name"])
        data = fetch(a_["browser_download_url"])
        with open(dest, "wb") as f:
            f.write(data)
        print("      %d 字节  sha256=%s" % (len(data), sha256(data)))
        if len(data) != a_["size"]:
            print("      [警告] 大小与 release 标称不一致！")

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n清单已写：%s" % os.path.join(OUT, "manifest.json"))
    return 0


if __name__ == "__main__":
    os.system("chcp 65001 > nul")
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())