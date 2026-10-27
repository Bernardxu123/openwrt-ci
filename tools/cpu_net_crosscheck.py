#!/usr/bin/env python3
"""Offline check: does pon0 rx track pon0.995 rx / br-lan rx ? (counter sanity)"""
import re
import sys

raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
samples = []
for line in raw.splitlines():
    if not line.startswith("N "):
        continue
    p = line.split()
    ts = float(p[1])
    devs = {}
    for tok in p[2:]:
        f = tok.split(":")
        if len(f) == 5:
            devs[f[0]] = (int(f[1]), int(f[2]))
    samples.append((ts, devs))


def rate(dev, idx):
    out = []
    for (t0, d0), (t1, d1) in zip(samples, samples[1:]):
        dt = t1 - t0
        if dt <= 0 or dev not in d0 or dev not in d1:
            continue
        out.append((t1, (d1[dev][idx] - d0[dev][idx]) / dt * 8 / 1e6))
    return out


print(f"{'t(s)':>7} {'pon0.rx':>9} {'pon0.tx':>9} {'pon995.rx':>10} {'pon995.tx':>10} {'pppoe.rx':>9} {'pppoe.tx':>9} {'brlan.rx':>9} {'brlan.tx':>9} {'phy1.rx':>8} {'phy1.tx':>8}")
r = {d: rate(d, 0) for d in ["pon0", "pon0.995", "pppoe-wan", "br-lan", "phy1-ap0"]}
t2 = {d: rate(d, 1) for d in ["pon0", "pon0.995", "pppoe-wan", "br-lan", "phy1-ap0"]}
n = min(len(v) for v in r.values())
for i in range(n):
    if i % 3:
        continue
    print(f"{r['pon0'][i][0]-r['pon0'][0][0]:>7.1f} "
          f"{r['pon0'][i][1]:>9.1f} {t2['pon0'][i][1]:>9.1f} "
          f"{r['pon0.995'][i][1]:>10.1f} {t2['pon0.995'][i][1]:>10.1f} "
          f"{r['pppoe-wan'][i][1]:>9.1f} {t2['pppoe-wan'][i][1]:>9.1f} "
          f"{r['br-lan'][i][1]:>9.1f} {t2['br-lan'][i][1]:>9.1f} "
          f"{r['phy1-ap0'][i][1]:>8.1f} {t2['phy1-ap0'][i][1]:>8.1f}")

# correlation pon0.rx vs br-lan.rx
import statistics
a = [x[1] for x in r["pon0"]]
b = [x[1] for x in r["br-lan"]]
if len(a) > 5 and statistics.pstdev(a) > 0:
    ma, mb = statistics.mean(a), statistics.mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    corr = cov / (len(a) * statistics.pstdev(a) * statistics.pstdev(b))
    print(f"\ncorr(pon0.rx, br-lan.rx) = {corr:.3f}")
    print(f"sum pon0.rx = {sum(a)*1e6/8/1e6:.1f} MB ; sum br-lan.rx = {sum(b)*1e6/8/1e6:.1f} MB")
    print(f"sum pon0.tx = {sum(x[1] for x in t2['pon0'])*1e6/8/1e6:.1f} MB ; sum pppoe.tx = {sum(x[1] for x in t2['pppoe-wan'])*1e6/8/1e6:.1f} MB")
