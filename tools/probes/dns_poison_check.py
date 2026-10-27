#!/usr/bin/env python3
"""Measure DNS poisoning rate through the router's resolver (dae DNS module)."""
import random
import socket
import struct
import sys

SRV = ("192.168.31.1", 53)
NAMES = ["youtubei.googleapis.com", "www.youtube.com", "redirector.googlevideo.com",
         "googlevideo.com", "youtube.com", "ggpht.com"]
QTYPE = {"A": 1, "AAAA": 28}

GOOD_V6 = ("2001:4860:", "2404:6800:", "2607:f8b0:", "2404:6801:", "2a00:1450:", "2001:4861:")


def build(name, qtype):
    tid = random.randint(0, 0xFFFF)
    q = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    for part in name.split("."):
        q += bytes([len(part)]) + part.encode()
    q += b"\x00" + struct.pack(">HH", qtype, 1)
    return tid, q


def parse_answers(buf, tid):
    (rid, flags, qd, an, ns, ar) = struct.unpack(">HHHHHH", buf[:12])
    if rid != tid:
        return None
    i = 12
    for _ in range(qd):
        while buf[i]:
            i += buf[i] + 1
        i += 5
    out = []
    for _ in range(an):
        if buf[i] & 0xC0 == 0xC0:
            i += 2
        else:
            while buf[i]:
                i += buf[i] + 1
            i += 1
        rtype, rclass, ttl, rdlen = struct.unpack(">HHIH", buf[i:i + 10])
        i += 10
        rd = buf[i:i + rdlen]
        i += rdlen
        if rtype == 1 and rdlen == 4:
            out.append(("A", ".".join(str(b) for b in rd)))
        elif rtype == 28 and rdlen == 16:
            out.append(("AAAA", socket.inet_ntop(socket.AF_INET6, rd)))
    return out


def query(name, qtype):
    tid, pkt = build(name, qtype)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
    try:
        s.sendto(pkt, SRV)
        while True:
            data, _ = s.recvfrom(4096)
            r = parse_answers(data, tid)
            if r is not None:
                return r
    except Exception as e:
        return [("ERR", str(e)[:30])]
    finally:
        s.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    total = bad = 0
    badsamples = []
    for r in range(rounds):
        for name in NAMES:
            for qt in ("AAAA", "A"):
                ans = query(name, QTYPE[qt])
                total += 1
                for t, v in ans:
                    if t == "ERR":
                        bad += 1
                        badsamples.append("%s %s -> %s" % (name, qt, v))
                    elif t == "AAAA" and not v.startswith(GOOD_V6):
                        bad += 1
                        badsamples.append("%s AAAA -> %s" % (name, v))
                    elif t == "A" and (v.startswith(("31.13.", "128.121.", "243.185.", "78.16.")) or v == "0.0.0.0"):
                        bad += 1
                        badsamples.append("%s A -> %s" % (name, v))
    print("queries=%d  suspicious=%d  (%.1f%%)" % (total, bad, 100.0 * bad / max(total, 1)))
    for s in badsamples[:25]:
        print("  SUSPECT:", s)
    if not badsamples:
        print("  no poisoning detected")
