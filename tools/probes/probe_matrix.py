#!/usr/bin/env python3
"""Matrix: which Google IPv6 addresses are actually usable through the tunnel."""
import socket
import ssl
import sys
import time

YOUTUBEI_AAAA = [
    "2001:4860:4840:400::", "2001:4860:4841:400::", "2001:4860:4842:400::", "2001:4860:4843:400::",
    "2001:4860:4844:400::", "2001:4860:4845:400::", "2001:4860:4846:400::", "2001:4860:4847:400::",
]
WWW_AAAA = [
    "2001:4860:4826:400::", "2001:4860:4827:400::", "2001:4860:4828:400::", "2001:4860:4829:400::",
    "2001:4860:482a:400::", "2001:4860:482b:400::", "2001:4860:482c:400::", "2001:4860:482d:400::",
]


def probe(host, sni):
    t0 = time.time()
    try:
        s = socket.create_connection((host, 443), timeout=8)
    except Exception as e:
        return "TCP-FAIL(%s)" % (type(e).__name__)
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
        return "FAIL(%s,%.2fs)" % (str(e).split("(")[0][:28], time.time() - t0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("== SNI youtubei.googleapis.com ==")
    for ip in YOUTUBEI_AAAA:
        print("  %-24s %s" % (ip, probe(ip, "youtubei.googleapis.com")), flush=True)
    print("== SNI www.youtube.com ==")
    for ip in WWW_AAAA:
        print("  %-24s %s" % (ip, probe(ip, "www.youtube.com")), flush=True)
    print("== cross-check: youtubei SNI on www addresses ==")
    for ip in WWW_AAAA[:3]:
        print("  %-24s %s" % (ip, probe(ip, "youtubei.googleapis.com")), flush=True)
