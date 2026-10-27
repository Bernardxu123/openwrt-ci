#!/usr/bin/env python3
"""Is UDP relay through daed working at all?

Control: a domestic NTP server (routed direct) proves the host can do UDP.
Test:    Google NTP (routed via proxy) proves UDP works through the tunnel.
"""
import socket
import struct
import sys
import time

NTP_PKT = b"\x1b" + 47 * b"\x00"


def ntp(host, family, label, wait=5.0):
    fam = socket.AF_INET6 if family == 6 else socket.AF_INET
    s = socket.socket(fam, socket.SOCK_DGRAM)
    s.settimeout(wait)
    t0 = time.time()
    try:
        s.sendto(NTP_PKT, (host, 123))
        d, a = s.recvfrom(1024)
        return "[%s] REPLY %d bytes from %s in %.0fms" % (label, len(d), a[0], (time.time() - t0) * 1000)
    except Exception as e:
        return "[%s] NO REPLY (%s) after %.1fs" % (label, type(e).__name__, time.time() - t0)
    finally:
        s.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # domestic (direct route) controls
    print(ntp("ntp.aliyun.com", 4, "control-alyun-CN"), flush=True)
    print(ntp("120.25.115.20", 4, "control-alyun-IP-CN"), flush=True)
    # foreign, goes through proxy
    print(ntp("216.239.35.0", 4, "google-ntp-via-proxy"), flush=True)
    print(ntp("216.239.35.4", 4, "google-ntp-via-proxy2"), flush=True)
    # foreign DNS over UDP on port 53 is hijacked by dae, so use 5353-ish alt none; skip
