#!/usr/bin/env python3
"""Does the SG6 group work when daed must dial an IPv6 LITERAL (sniff missed)?
0.8s delay makes daed's 100ms sniff time out -> dial by IP literal."""
import socket
import ssl
import sys
import time

POOL = ["2001:4860:4840:400::", "2001:4860:4842:400::", "2001:4860:4844:400::", "2001:4860:4847:400::"]
PROXY_CTRL = ["2001:4860:482b:400::"]


def probe(host, sni, delay):
    t0 = time.time()
    try:
        s = socket.create_connection((host, 443), timeout=8)
    except Exception as e:
        return "TCP-FAIL %s" % type(e).__name__
    if delay:
        time.sleep(delay)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ss = ctx.wrap_socket(s, server_hostname=sni)
        v = ss.version()
        ss.close()
        return "OK(%.0fms)" % ((time.time() - t0) * 1000)
    except Exception as e:
        try:
            s.close()
        except Exception:
            pass
        return "FAIL(%.2fs %s)" % (time.time() - t0, str(e)[:40])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("== SG6 group (pool) — dial by IPv6 literal ==")
    for ip in POOL:
        print("  %-24s %s" % (ip, probe(ip, "youtubei.googleapis.com", 0.8)), flush=True)
    print("== proxy group (HK) control — dial by IPv6 literal ==")
    for ip in PROXY_CTRL:
        print("  %-24s %s" % (ip, probe(ip, "www.youtube.com", 0.8)), flush=True)
