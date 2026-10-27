#!/usr/bin/env python3
"""Stability check: repeated TLS to the previously-dead pool address."""
import socket
import ssl
import sys
import time

TARGET = "2001:4860:4842:400::"
SNI = "youtubei.googleapis.com"

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ok = 0
    for i in range(6):
        t0 = time.time()
        try:
            s = socket.create_connection((TARGET, 443), timeout=10)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ss = ctx.wrap_socket(s, server_hostname=SNI)
            v = ss.version()
            ss.close()
            ok += 1
            print("#%d OK   %s  %.0fms" % (i + 1, v, (time.time() - t0) * 1000), flush=True)
        except Exception as e:
            print("#%d FAIL      %.2fs  %s" % (i + 1, time.time() - t0, str(e)[:60]), flush=True)
        time.sleep(1)
    print("== %d/6 succeeded ==" % ok)
