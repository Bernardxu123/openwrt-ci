#!/usr/bin/env python3
"""Send no payload at all -> dae's 100ms sniff times out -> dae must dial by IP.
Reveals which outbound dae picks for un-sniffable destinations."""
import socket
import sys
import time

TARGETS = [
    ("2001:4860:4842:400::", 443, "v6 google-4842 (BAD)"),
    ("2001:4860:4844:400::", 443, "v6 google-4844"),
    ("2001:4860:482b:400::", 443, "v6 google-482b www.youtube"),
    ("2606:4700:78::90:0:140", 443, "v6 cloudflare"),
    ("142.251.16.100", 443, "v4 google"),
    ("172.217.114.4", 443, "v4 google youtubei"),
    ("1.1.1.1", 443, "v4 cloudflare"),
]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for host, port, label in TARGETS:
        try:
            s = socket.create_connection((host, port), timeout=5)
            time.sleep(1.2)   # exceed sniffingTimeout(100ms) so dae dials by IP
            s.close()
            print("opened+slept  %-34s %s" % (label, host), flush=True)
        except Exception as e:
            print("connect-fail  %-34s %s : %s" % (label, host, e), flush=True)
        time.sleep(0.4)
    time.sleep(1)
