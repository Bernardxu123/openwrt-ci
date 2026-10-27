#!/usr/bin/env python3
"""只读探针：核验 daed runtimeOverview 的采样密度与载荷（Phase 1.1/1.2 依据）。

回答三个问题：
  1. maxPoints 120 vs 240 到底给出多少个点、点间隔多少秒；
  2. 更密的点是真的新样本，还是插值/重复（值重复率）；
  3. 面板那版 general 查询的响应字节数，预算 Phase 1.2 的载荷翻倍是否成立。
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from daed import gql, token  # noqa: E402

# 面板 app.js:168 实际请求的字段（含 runtimeOverview 之外的部分）
PANEL_Q = """query {{
  general {{
    dae {{ running version modified }}
    interfaces {{ name flag {{ up }} ip }}
    runtimeOverview(windowSec: 600, maxPoints: {mp}) {{
      updatedAt uploadRate downloadRate uploadTotal downloadTotal
      activeConnections udpSessions
      samples {{ timestamp uploadRate downloadRate }}
    }}
  }}
}}"""

OV_Q = """query {{ general {{ runtimeOverview(windowSec: 600, maxPoints: {mp}) {{
  updatedAt samples {{ timestamp uploadRate downloadRate }} }} }} }}"""


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def probe(mp):
    t0 = time.time()
    res = gql(OV_Q.format(mp=mp), token())
    ms = (time.time() - t0) * 1000
    raw = json.dumps(res, separators=(",", ":"))
    ov = res["data"]["general"]["runtimeOverview"]
    s = ov["samples"]
    ts = [parse_ts(x["timestamp"]) for x in s]
    gaps = [(ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1)]
    vals = [(x["uploadRate"], x["downloadRate"]) for x in s]
    dup = sum(1 for i in range(1, len(vals)) if vals[i] == vals[i - 1])
    distinct = len(set(vals))
    print(
        f"maxPoints={mp:4d} -> {len(s):4d} 点  "
        f"间隔 {min(gaps):.2f}~{max(gaps):.2f}s(中位 {sorted(gaps)[len(gaps)//2]:.2f}s)  "
        f"值重复对 {dup}/{max(1,len(vals)-1)}  去重值 {distinct}  "
        f"OV载荷 {len(raw)}B  用时 {ms:.0f}ms"
    )
    print(f"   窗口 {ts[0].strftime('%H:%M:%S')} → {ts[-1].strftime('%H:%M:%S')}  updatedAt={ov['updatedAt'][:19]}")


def panel_payload(mp):
    t0 = time.time()
    res = gql(PANEL_Q.format(mp=mp), token())
    ms = (time.time() - t0) * 1000
    raw = json.dumps(res, separators=(",", ":"))
    n = len(res["data"]["general"]["runtimeOverview"]["samples"])
    print(f"面板式 general 查询 maxPoints={mp:4d} -> {len(raw) / 1024:.1f}KB / {n} 点 / {ms:.0f}ms")


if __name__ == "__main__":
    print("== runtimeOverview 密度核验 ==")
    for mp in (6, 120, 240):
        probe(mp)
        time.sleep(0.5)
    print("\n== 面板载荷预算 ==")
    panel_payload(120)
    panel_payload(240)
