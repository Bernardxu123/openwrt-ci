#!/usr/bin/env python3
"""Analyze per-core CPU samples collected by cpu_percore_sample.sh on the router."""
import re
import sys
from datetime import datetime

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def fetch():
    import paramiko
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)
    out = {}
    for name in ["meta.txt", "procstat.raw", "net.raw", "interrupts.raw", "interrupts.end", "top.snap", "procstat.end"]:
        stdin, stdout, stderr = c.exec_command(f"cat /tmp/cpusample/{name} 2>/dev/null", timeout=60)
        out[name] = stdout.read().decode("utf-8", "replace")
        stdout.channel.recv_exit_status()
    c.close()
    return out


def parse_stat(raw):
    samples = []
    for line in raw.splitlines():
        if not line.startswith("S "):
            continue
        parts = line.replace("|", " ").split()
        ts = float(parts[1])
        cores = {}
        idx = 2
        while idx < len(parts):
            p = parts[idx]
            if re.match(r"^cpu\d+$", p):
                f = p[3:]
                vals = [int(x) for x in parts[idx + 1: idx + 11]]
                cores[int(f)] = vals
                idx += 11
            else:
                break
        samples.append((ts, cores))
    return samples


def core_usage(prev, cur):
    """Return dict core -> (busy%, user%, sys%, irq+softirq%)"""
    out = {}
    for c, v in cur.items():
        if c not in prev:
            continue
        pv = prev[c]
        d = [cur_v - prev_v for cur_v, prev_v in zip(v, pv)]
        total = sum(d)
        if total <= 0:
            continue
        idle = d[3] + d[4]
        user = d[0] + d[1]
        sys = d[2]
        irq = d[5] + d[6]
        out[c] = (100.0 * (total - idle) / total, 100.0 * user / total, 100.0 * sys / total, 100.0 * irq / total)
    return out


def parse_net(raw):
    samples = []
    for line in raw.splitlines():
        if not line.startswith("N "):
            continue
        parts = line.split()
        ts = float(parts[1])
        devs = {}
        for p in parts[2:]:
            if ":" not in p:
                continue
            f = p.split(":")
            if len(f) != 5:
                continue
            devs[f[0]] = (int(f[1]), int(f[2]), int(f[3]), int(f[4]))
        samples.append((ts, devs))
    return samples


def net_rate(samples, dev):
    if len(samples) < 2:
        return []
    out = []
    for (t0, d0), (t1, d1) in zip(samples, samples[1:]):
        dt = t1 - t0
        if dt <= 0 or dev not in d0 or dev not in d1:
            continue
        rx = (d1[dev][0] - d0[dev][0]) / dt
        tx = (d1[dev][1] - d0[dev][1]) / dt
        out.append((t1, rx, tx))
    return out


def main():
    d = fetch()
    print("=" * 78)
    print("META")
    print("=" * 78)
    print(d["meta.txt"])

    samples = parse_stat(d["procstat.raw"])
    print(f"\n采样点: {len(samples)}  跨度: {samples[-1][0]-samples[0][0]:.1f}s" if samples else "NO SAMPLES")

    if len(samples) >= 2:
        ncpu = len(samples[0][1])
        print("\n" + "=" * 78)
        print("每核 CPU 占用（逐秒）")
        print("=" * 78)
        hdr = "  t(s)  " + "".join(f"  cpu{c}(busy/usr/sys/irq)".ljust(26) for c in range(ncpu))
        print(hdr)
        rows = []
        percore_busy = {c: [] for c in range(ncpu)}
        for (t0, c0), (t1, c1) in zip(samples, samples[1:]):
            u = core_usage(c0, c1)
            line = f"{t1-samples[0][0]:6.1f} "
            for c in range(ncpu):
                if c in u:
                    b, us, sy, iq = u[c]
                    percore_busy[c].append(b)
                    line += f" {b:5.1f}/{us:4.1f}/{sy:4.1f}/{iq:4.1f}".ljust(26)
                else:
                    line += " " * 26
            rows.append(line)
        for r in rows:
            print(r)

        print("\n" + "=" * 78)
        print("每核汇总")
        print("=" * 78)
        print(f"{'core':>6} {'avg_busy%':>10} {'max_busy%':>10} {'p95_busy%':>10} {'avg_user%':>10} {'avg_sys%':>10} {'avg_irq%':>10}")
        for c in range(ncpu):
            vals = percore_busy[c]
            if not vals:
                continue
            s = sorted(vals)
            p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
            print(f"{c:>6} {sum(vals)/len(vals):>10.1f} {max(vals):>10.1f} {p95:>10.1f}")
        # overall
        allv = [v for c in range(ncpu) for v in percore_busy[c]]
        if allv:
            s = sorted(allv)
            print(f"\n全核平均 busy = {sum(allv)/len(allv):.1f}%   峰值 = {max(allv):.1f}%   p95 = {s[int(len(s)*0.95)]:.1f}%")

    # network
    nets = parse_net(d["net.raw"])
    if nets:
        print("\n" + "=" * 78)
        print("网卡吞吐（Mbps，按 1s 窗口）")
        print("=" * 78)
        watch = ["br-lan", "eth0", "lan1", "phy0-ap0", "phy1-ap0", "pppoe-wan", "pon0.995", "pon0"]
        devs = sorted({k for _, dd in nets for k in dd})
        for dev in devs:
            if dev not in watch and not any(dev.startswith(w) for w in watch):
                continue
            r = net_rate(nets, dev)
            if not r:
                continue
            rxs = [x[1] for x in r]
            txs = [x[2] for x in r]
            if max(rxs) < 20000 and max(txs) < 20000:
                continue
            print(f"{dev:>12}  rx avg {sum(rxs)/len(rxs)*8/1e6:7.2f} Mbps  max {max(rxs)*8/1e6:7.2f}   "
                  f"tx avg {sum(txs)/len(txs)*8/1e6:7.2f} Mbps  max {max(txs)*8/1e6:7.2f}")
        # br-lan + pppoe timeline
        for dev in ("br-lan", "pppoe-wan", "phy0-ap0", "phy1-ap0"):
            r = net_rate(nets, dev)
            if not r:
                continue
            peak = max(r, key=lambda x: x[1] + x[2])
            print(f"\n--- {dev} 时间线 (每 5s 汇总, Mbps) ---")
            for i in range(0, len(r), 5):
                chunk = r[i:i + 5]
                rx = sum(x[1] for x in chunk) / len(chunk) * 8 / 1e6
                tx = sum(x[2] for x in chunk) / len(chunk) * 8 / 1e6
                print(f"  t={chunk[-1][0]-r[0][0]:6.1f}s  rx {rx:8.2f}  tx {tx:8.2f}")

    # irq delta
    if d["interrupts.raw"] and d["interrupts.end"]:
        print("\n" + "=" * 78)
        print("中断增量（采样窗口内，per-CPU 计数差）")
        print("=" * 78)

        def parse_irq(txt):
            res = {}
            for line in txt.splitlines():
                if ":" not in line:
                    continue
                head, rest = line.split(":", 1)
                toks = rest.split()
                nums = []
                for t in toks:
                    if t.isdigit():
                        nums.append(int(t))
                    else:
                        break
                name = " ".join(toks[len(nums):])
                res[head.strip()] = (nums, name)
            return res

        a = parse_irq(d["interrupts.raw"])
        b = parse_irq(d["interrupts.end"])
        for k in a:
            if k in b:
                na, nb = a[k][0], b[k][0]
                if len(na) == len(nb) and len(na) == 4:
                    delta = [nb[i] - na[i] for i in range(4)]
                    if sum(delta) == 0:
                        continue
                    name = a[k][1]
                    print(f"{k:>5} {name:<42} cpu0={delta[0]:>12} cpu1={delta[1]:>10} cpu2={delta[2]:>10} cpu3={delta[3]:>10}")

    print("\n" + "=" * 78)
    print("TOP SNAPSHOT (end)")
    print("=" * 78)
    print(d["top.snap"][:3000])


if __name__ == "__main__":
    main()
