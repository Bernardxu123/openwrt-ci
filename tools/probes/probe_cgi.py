#!/usr/bin/env python3
"""Phase 3/4 验收：按前端的游标协议驱动线上 CGI，测每次轮询的真实字节数。

对比基线：旧 CGI 每次（5s）固定 165,243 字节 ≈ 33KB/s。
新 CGI 目标：稳态 <5KB/次（节拍 3s）。
"""
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CGI = "http://192.168.31.1/cgi-bin/daed-board-log"
META_RE = re.compile(rb"^#META inode=(\d+) size=(\d+) off=(\d+) reset=(\d)", re.M)


def get(url=CGI):
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=15) as r:
        raw = r.read()
    return raw, (time.time() - t0) * 1000


def split_ctrl(raw):
    """返回 (控制段字节, 日志体字节)；控制段 = 到 #META 行为止。"""
    m = META_RE.search(raw)
    assert m, "响应里没有 #META（CGI 没升级？）"
    end = raw.index(b"\n", m.start()) + 1
    return raw[:end], raw[end:], m


def main(rounds=6, gap=3.0, traffic=True):
    raw, ms = get()
    ctrl, body, m = split_ctrl(raw)
    ino, size, off, reset = (int(x) for x in m.groups())
    print(f"首次（回填）: 总 {len(raw):,}B = 控制 {len(ctrl):,}B + 日志体 {len(body):,}B / {ms:.0f}ms  reset={reset}")
    cur = off + len(body.rstrip(b"\n") and body[: body.rfind(b"\n") + 1] or b"")
    print(f"游标 → {cur:,}（文件 size={size:,}）")

    print(f"\n稳态轮询（每 {gap}s 一次，{'期间制造代理流量' if traffic else '静默'}）:")
    tot = 0
    for i in range(rounds):
        if traffic and i % 2 == 0:
            subprocess.run(["curl.exe", "-s", "-o", "NUL", "-m", "10",
                            "https://www.youtube.com/generate_204"], capture_output=True)
        time.sleep(gap)
        raw, ms = get(f"{CGI}?inode={ino}&off={cur}")
        ctrl, body, m = split_ctrl(raw)
        ino, size, off, reset = (int(x) for x in m.groups())
        complete = body[: body.rfind(b"\n") + 1] if b"\n" in body else b""
        cur = off + len(complete)
        tot += len(raw)
        print(f"  #{i + 1}: 总 {len(raw):,}B（控制 {len(ctrl):,} + 新增 {len(body):,}，其中完整行 {len(complete):,}）"
              f" / {ms:.0f}ms  reset={reset}  游标 {cur:,}")
    avg = tot / rounds
    print(f"\n平均每次 {avg:,.0f} 字节   （旧版固定 165,243 字节 → 降幅 {100 * (1 - avg / 165243):.1f}%）")
    print(f"折算持续流量: {avg / gap / 1024:.1f} KB/s（旧版 ≈ {165243 / 5 / 1024:.1f} KB/s）")


if __name__ == "__main__":
    main(rounds=int(sys.argv[1]) if len(sys.argv) > 1 else 6)
