#!/usr/bin/env python3
"""Compare router DNS answers against DoH ground truth (pollution + AAAA policy)."""
import socket, struct, json, sys, urllib.request

ROUTER = ("192.168.31.1", 53)
DOH = "https://cloudflare-dns.com/dns-query"

DOMAINS = [
    ("www.google.com", "A"), ("www.google.com", "AAAA"),
    ("www.youtube.com", "A"), ("www.youtube.com", "AAAA"),
    ("www.baidu.com", "A"), ("www.baidu.com", "AAAA"),
    ("www.taobao.com", "AAAA"),
    ("chatgpt.com", "A"), ("chatgpt.com", "AAAA"),
    ("openai.com", "A"),
    ("aistudio.google.com", "A"), ("aistudio.google.com", "AAAA"),
    ("gemini.google.com", "A"),
    ("api.anthropic.com", "A"),
    ("claude.ai", "A"),
    ("github.com", "A"),
    ("api64.ipify.org", "AAAA"),
]


def q_udp(name, qtype, server, port, timeout=6):
    tid = 0x4321
    hdr = struct.pack('>HHHHHH', tid, 0x0100, 1, 0, 0, 0)
    qn = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\x00'
    pkt = hdr + qn + struct.pack('>HH', qtype, 1)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(pkt, (server, port))
        data, _ = s.recvfrom(4096)
        s.close()
    except Exception as e:
        return None, str(e)
    ancount = struct.unpack('>H', data[6:8])[0]
    off = 12
    while data[off] != 0:
        off += data[off] + 1
    off += 5
    ips = []
    for _ in range(ancount):
        if data[off] & 0xC0 == 0xC0:
            off += 2
        else:
            while data[off] != 0:
                off += data[off] + 1
            off += 1
        t, cl, ttl, dl = struct.unpack('>HHIH', data[off:off+10])
        off += 10
        rdata = data[off:off+dl]
        if t == 1:
            ips.append('.'.join(str(b) for b in rdata))
        elif t == 28:
            ips.append(socket.inet_ntop(socket.AF_INET6, rdata))
        off += dl
    return ips, None


def q_doh(name, qtype):
    t = "A" if qtype == 1 else "AAAA"
    req = urllib.request.Request(
        f"{DOH}?name={name}&type={t}",
        headers={"accept": "application/dns-json",
                 "user-agent": "dns-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.load(r)
        return [a.get("data") for a in j.get("Answer", []) if a.get("type") in (1, 28)]
    except Exception:
        return None


def main():
    print("%-24s %-4s | %-36s | %-30s | %s" %
          ("domain", "type", "router DNS", "DoH truth", "verdict"))
    print("-" * 140)
    polluted = aaaa_leak = checked = 0
    for name, tlabel in DOMAINS:
        qtype = 1 if tlabel == "A" else 28
        got, err = q_udp(name, qtype, *ROUTER)
        truth = q_doh(name, qtype)
        gs = "ERR:" + str(err)[:10] if got is None else (",".join(got[:2]) if got else "(empty)")
        ts = "?" if truth is None else (",".join(truth[:2]) if truth else "(empty)")
        verdict = ""
        if got is not None:
            checked += 1
            if truth is None:
                verdict = "?"
            elif tlabel == "A":
                if got and truth:
                    verdict = "OK" if set(got) & set(truth) else "*** POLLUTED ***"
                    if "POLLUTED" in verdict:
                        polluted += 1
                elif not got and not truth:
                    verdict = "OK"
                elif not got:
                    verdict = "EMPTY(doH has data)"
                else:
                    verdict = "DIFF"
            else:
                if not got:
                    verdict = "AAAA blocked (v4 only)"
                elif truth and set(got) & set(truth):
                    verdict = "AAAA ok"
                else:
                    verdict = "AAAA present"
                    aaaa_leak += 1
        print("%-24s %-4s | %-36s | %-30s | %s" % (name, tlabel, gs[:36], ts[:30], verdict))
    print("-" * 140)
    print("checked=%d  polluted=%d  AAAA-present=%d" % (checked, polluted, aaaa_leak))


if __name__ == "__main__":
    main()
