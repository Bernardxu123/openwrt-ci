#!/usr/bin/env python3
"""Parallel download throughput test (client side)."""
import subprocess, sys, time

URL = sys.argv[1] if len(sys.argv) > 1 else "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ls-lR.gz"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 4
T = sys.argv[3] if len(sys.argv) > 3 else "10"

procs = [subprocess.Popen(
    ["curl.exe", "-s", "-o", "NUL", "-w", "%{speed_download}\n", "--max-time", T, URL],
    stdout=subprocess.PIPE) for _ in range(N)]
out = []
for p in procs:
    try:
        out.append(float(p.communicate(timeout=int(T) + 10)[0].decode().strip() or 0))
    except Exception:
        out.append(0)
tot = sum(out)
print("streams:", " ".join("%.1f Mbps" % (x * 8 / 1e6) for x in out))
print("aggregate: %.1f Mbps  (%.1f MB/s)" % (tot * 8 / 1e6, tot / 1e6))
