#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""U-Boot recovery 分步执行器（HG5585F-CT / an758x）。

对应 U-Boot 页面 /api/upload + /api/task：
  重建 UBI      task {"operation":"ubi-rebuild"}
  写 fip        upload fip   -> task {"operation":"flash-uboot","upload_id":N}
  写板级数据    upload 1MiB  -> task {"operation":"write","kind":"ubi","target":"factory","upload_id":N}
  刷系统        upload itb   -> task {"operation":"flash","upload_id":N}
  启动系统      task {"operation":"boot-production"}

用法（一次一步，失败即停）：
  python uboot-install.py --check
  python uboot-install.py --rebuild
  python uboot-install.py --fip  ..\物料\引导\an7581-fiberhome-hg5585f-ct-bl31-u-boot.fip
  python uboot-install.py --factory ..\备份\factory-1m.bin
  python uboot-install.py --firmware ..\物料\可选-QWRT\QWRT-...itb
  python uboot-install.py --boot
"""
import argparse
import os
import sys
import time

try:
    import requests
except ImportError:
    print("缺少依赖：pip install requests", file=sys.stderr)
    raise SystemExit(2)

BASE = "http://192.168.0.1"


def get_task(timeout=10):
    r = requests.get(BASE + "/api/task", timeout=timeout)
    r.raise_for_status()
    return r.json()


def device():
    r = requests.get(BASE + "/api/device", timeout=10)
    r.raise_for_status()
    return r.json()


def upload(path):
    size = os.path.getsize(path)
    print(f"[upload] {path}  {size:,} bytes ...", flush=True)
    with open(path, "rb") as f:
        r = requests.post(BASE + "/api/upload", data=f, timeout=900)
    r.raise_for_status()
    info = r.json()
    print(f"[upload] -> {info}", flush=True)
    if "upload_id" not in info:
        raise RuntimeError(f"upload response missing upload_id: {info}")
    return info["upload_id"]


def wait_task(payload, timeout=1200):
    r = requests.post(BASE + "/api/task", json=payload, timeout=30)
    r.raise_for_status()
    st = r.json()
    tid = st.get("id")
    print(f"[task] id={tid} payload={payload}", flush=True)
    deadline = time.time() + timeout
    last = None
    while True:
        time.sleep(1.5)
        try:
            st = get_task()
        except Exception as e:
            print(f"  poll: {type(e).__name__}: {e}", flush=True)
            if time.time() > deadline:
                raise
            continue
        key = (st.get("state"), st.get("phase"), st.get("code"))
        if key != last:
            print(f"  state={st.get('state')} phase={st.get('phase')} code={st.get('code')} out={st.get('output','')[:200]!r}", flush=True)
            last = key
        if st.get("id") != tid:
            raise RuntimeError(f"task id changed: {tid} -> {st.get('id')}")
        if st.get("state") == "done":
            if st.get("code"):
                raise RuntimeError(f"task failed code={st.get('code')}: {st.get('output')}")
            print("[task] done", flush=True)
            return st
        if time.time() > deadline:
            raise TimeoutError(f"task {tid} timeout")


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--fip")
    ap.add_argument("--factory")
    ap.add_argument("--firmware")
    ap.add_argument("--boot", action="store_true")
    a = ap.parse_args()
    BASE = a.base.rstrip("/")

    if a.check:
        print(device())
        print(get_task())
        return 0
    if a.rebuild:
        wait_task({"operation": "ubi-rebuild"})
        return 0
    if a.fip:
        wait_task({"operation": "flash-uboot", "upload_id": upload(a.fip)})
        return 0
    if a.factory:
        wait_task({"operation": "write", "kind": "ubi", "target": "factory", "upload_id": upload(a.factory)})
        return 0
    if a.firmware:
        wait_task({"operation": "flash", "upload_id": upload(a.firmware)}, timeout=1800)
        return 0
    if a.boot:
        try:
            r = requests.post(BASE + "/api/task", json={"operation": "boot-production"}, timeout=10)
            print(f"[boot] HTTP {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"[boot] 连接中断（预期，设备正在重启）: {type(e).__name__}: {e}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
