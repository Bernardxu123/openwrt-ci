#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
locate.py — 用双 AP 的 RSSI 差值反解终端位置，并把实测数据回灌进规划器。

原理
----
同一台终端在两个 AP 上的接收功率差，只跟「距离比」有关：

    RSSI_A - RSSI_B = 10·n·log10(d_B / d_A) + (墙损耗差)

忽略墙损耗时，这是一个「阿波罗尼斯圆」（到两定点距离之比为常数）。
n 取 3.2（5 GHz 室内典型值）时，2 dB 的差值约等于 20% 的距离差，
所以双 AP 能把终端定位到「一条圆弧」上；再叠加「必须在室内」的约束，
通常能收敛到 1~2 m 的精度。

用法
----
  python locate.py                     # 读取 logs/survey.csv，输出定位结果
  python locate.py --export geo.json   # 导出给 index.html 用的实测文件
  python locate.py --anchor 780,700    # 已知某终端在 (x,y)px，用它反标定 AP 坐标
"""
import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

# ---- 户型坐标（plan 像素，80 px = 1 m），与 index.html 保持一致 ----
PX_PER_M = 80.0
PLAN_PX = 1020

# 两台 AP 在户型里的位置（先验，可用 --calibrate 修正）
AP_POS = {
    "ONT-5G":   (330, 470),
    "ONT-2.4G": (330, 470),
    "AP-5G":    (830, 640),
    "AP-2.4G":  (830, 640),
}

# 路径损耗指数
N_24 = 2.7
N_5 = 3.2

# 室内区域多边形（与 data.js 的 OUTLINE 一致）
OUTLINE = [
    (290, 36), (487, 36), (487, 88), (640, 88), (640, 28), (854, 28),
    (854, 340), (935, 340), (935, 1003), (640, 1003), (640, 940),
    (296, 940), (296, 932), (45, 932), (45, 552), (196, 552),
    (196, 352), (290, 352),
]


def in_poly(x, y, poly=OUTLINE):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def load(path):
    """-> {mac: {'name':..., 'obs': {ap: rssi}, 'band': ...}}"""
    dev = {}
    if not os.path.exists(path):
        return dev
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            mac = r["mac"]
            d = dev.setdefault(mac, {"name": r.get("hostname") or mac,
                                     "ip": r.get("ip", ""),
                                     "band": r.get("band", "5"),
                                     "obs": defaultdict(list)})
            try:
                d["obs"][r["ap"]].append(int(r["rssi"]))
            except (ValueError, KeyError):
                pass
    # 取中位数
    for d in dev.values():
        d["obs"] = {k: sorted(v)[len(v) // 2] for k, v in d["obs"].items()}
    return dev


def solve_ratio(ap_a, ap_b, rssi_a, rssi_b, n, step=4, tol_db=2.0):
    """
    在室内网格上搜索，最小化 |预测RSSI差 - 实测RSSI差|。

    关键：两 AP 的 RSSI 差只决定「到两点的距离比」，在平面上是一个圆，
    不是点。所以这里不只返回最优点，还返回所有「误差在 tol_db 内」的
    候选点，用它们的散布度作为不确定度。若候选点连成一片（跨越大半个
    户型），说明这组观测退化，定位不可信 —— 标出来，别误导用户。

    返回 dict: {x, y, err, spread_m, candidates, reliable}
    """
    pa, pb = AP_POS[ap_a], AP_POS[ap_b]
    target = rssi_a - rssi_b
    pts = []
    best = None
    for y in range(20, PLAN_PX - 20, step):
        for x in range(20, PLAN_PX - 20, step):
            if not in_poly(x, y):
                continue
            da = max(math.hypot(x - pa[0], y - pa[1]) / PX_PER_M, 0.4)
            db = max(math.hypot(x - pb[0], y - pb[1]) / PX_PER_M, 0.4)
            pred = 10 * n * math.log10(db / da)
            err = abs(pred - target)
            if best is None or err < best[2]:
                best = (x, y, err)
            if err <= tol_db:
                pts.append((x, y))
    if best is None:
        return None

    # 不确定度：候选点集在平面上的最大跨度（米）
    spread = 0.0
    if len(pts) > 1:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        spread = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / PX_PER_M

    # 可靠判据：候选跨度 < 6 m 且最优点误差 < 1.5 dB
    reliable = (spread < 6.0) and (best[2] < 1.5)

    # 最优点若落在候选簇边缘，改用候选簇质心更稳
    if pts and reliable:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        # 质心与最优点取折中（质心更稳，最优点更贴合实测）
        x = (cx + best[0]) / 2
        y = (cy + best[1]) / 2
        best = (int(round(x)), int(round(y)), best[2])

    return {
        "x": best[0], "y": best[1], "err": round(best[2], 2),
        "spread_m": round(spread, 1), "n_cand": len(pts),
        "reliable": reliable,
    }


def solve_triple(obs, n, step=4):
    """
    三台以上 AP 时，用最小二乘直接拟合距离
    obs: {ap: rssi}
    """
    aps = [a for a in obs if a in AP_POS]
    if len(aps) < 2:
        return None
    # 以最强 AP 为参考，反推每台的距离
    ref = max(aps, key=lambda a: obs[a])
    d = {ref: 1.0}
    for a in aps:
        if a == ref:
            continue
        d[a] = 10 ** ((obs[ref] - obs[a]) / (10 * n))
    # 网格搜索，最小化距离误差平方和
    best = None
    for y in range(20, PLAN_PX - 20, step):
        for x in range(20, PLAN_PX - 20, step):
            if not in_poly(x, y):
                continue
            err = 0.0
            for a in aps:
                pa = AP_POS[a]
                dist = max(math.hypot(x - pa[0], y - pa[1]) / PX_PER_M, 0.4)
                err += (dist / d[a] - 1.0) ** 2
            if best is None or err < best[2]:
                best = (x, y, err)
    if best is None:
        return None
    return {"x": best[0], "y": best[1], "err": round(best[2], 3),
            "spread_m": 0.0, "reliable": best[2] < 0.35}


def main():
    ap = argparse.ArgumentParser(description="用双 AP RSSI 反解终端位置")
    ap.add_argument("--csv", default="logs/survey.csv")
    ap.add_argument("--export", default="", help="导出实测 JSON 给 index.html")
    ap.add_argument("--min-obs", type=int, default=2, help="至少被几台 AP 观测到")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dev = load(args.csv)
    if not dev:
        print("没有数据，先跑 python survey.py")
        return

    # 按频段配对：ONT-5G ↔ AP-5G，ONT-2.4G ↔ AP-2.4G
    PAIRS = [("ONT-5G", "AP-5G", N_5), ("ONT-2.4G", "AP-2.4G", N_24)]

    results = []
    for mac, d in dev.items():
        obs = d["obs"]
        if len(obs) < args.min_obs:
            continue
        pos = None
        how = ""
        for a, b, n in PAIRS:
            if a in obs and b in obs:
                pos = solve_ratio(a, b, obs[a], obs[b], n)
                how = "%s(%d) ↔ %s(%d)" % (a, obs[a], b, obs[b])
                break
        if pos is None:
            # 同频段两台以上
            for band, n in (("5", N_5), ("2.4", N_24)):
                sub = {k: v for k, v in obs.items()
                       if (k.endswith("5G") and band == "5") or (k.endswith("2.4G") and band == "2.4")}
                if len(sub) >= 2:
                    pos = solve_triple(sub, n)
                    how = " ".join("%s(%d)" % (k, v) for k, v in sub.items())
                    break
        if pos is None:
            continue
        results.append({
            "mac": mac, "name": d["name"], "ip": d["ip"], "band": d["band"],
            "x": pos["x"], "y": pos["y"], "err": pos["err"],
            "spread_m": pos.get("spread_m", 0),
            "reliable": pos.get("reliable", False),
            "obs": obs, "how": how,
        })

    results.sort(key=lambda r: r["err"])
    print("=" * 84)
    print("定位结果（%d 台终端被 ≥%d 台 AP 同时观测到）" % (len(results), args.min_obs))
    print("=" * 84)
    print("%-28s %-9s %-11s %-8s %-6s %s" % (
        "设备", "位置(px)", "位置(m)", "残差", "不确定", "可靠 / 观测"))
    for r in results:
        mx, my = r["x"] / PX_PER_M, r["y"] / PX_PER_M
        print("%-28s %-9s %-11s %-8s %-6s %s  %s" % (
            r["name"][:28], "%d,%d" % (r["x"], r["y"]),
            "%.1f,%.1f" % (mx, my), "%.1fdB" % r["err"],
            "±%.1fm" % r.get("spread_m", 0),
            "✓" if r.get("reliable") else "✗",
            r["how"]))
    bad = [r for r in results if not r.get("reliable")]
    if bad:
        print("\n⚠ %d 台定位不可靠：两台 AP 的 RSSI 差太小（<2dB），" % len(bad))
        print("  解是一段圆弧而非一个点。让该设备靠近其中一台 AP 再采一次，")
        print("  或走到户型对角重采，差值拉开到 6dB 以上就准了。")

    if args.export:
        out = {
            "generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "planPx": PLAN_PX, "pxPerM": PX_PER_M,
            "apPos": AP_POS,
            "devices": results,
        }
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("\n已导出 %s（%d 台）" % (args.export, len(results)))


if __name__ == "__main__":
    main()
