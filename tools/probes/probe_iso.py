#!/usr/bin/env python3
"""Disambiguate: is the failure tied to the destination IP or to the SNI domain?"""
import socket
import ssl
import sys
import time


def probe(label, host, sni):
    t0 = time.time()
    try:
        s = socket.create_connection((host, 443), timeout=8)
    except Exception as e:
        return "[%s] TCP-FAIL %s" % (label, type(e).__name__)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ss = ctx.wrap_socket(s, server_hostname=sni)
        v = ss.version()
        ss.close()
        return "[%s] OK %s %.0fms" % (label, v, (time.time() - t0) * 1000)
    except Exception as e:
        try:
            s.close()
        except Exception:
            pass
        return "[%s] FAIL %.2fs %s" % (label, time.time() - t0, str(e)[:60])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    BAD = "2001:4860:4842:400::"
    GOOD = "2001:4860:4844:400::"
    for i in range(2):
        print(probe("BAD+SNI youtubei  #%d" % i, BAD, "youtubei.googleapis.com"), flush=True)
    for i in range(2):
        print(probe("BAD+SNI www.youtube #%d" % i, BAD, "www.youtube.com"), flush=True)
    print(probe("BAD+SNI android.googleapis", BAD, "android.googleapis.com"), flush=True)
    print(probe("BAD+SNI opencode.ai", BAD, "opencode.ai"), flush=True)
    for i in range(2):
        print(probe("GOOD+SNI youtubei #%d" % i, GOOD, "youtubei.googleapis.com"), flush=True)
