import socket
import ssl
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def probe(host, sni, delay):
    t0 = time.time()
    try:
        s = socket.create_connection((host, 443), timeout=8)
    except Exception as e:
        return f"TCP-FAIL {type(e).__name__} ({time.time() - t0:.2f}s)"
    if delay:
        time.sleep(delay)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ss = ctx.wrap_socket(s, server_hostname=sni)
        v = ss.version()
        ss.close()
        return f"OK({(time.time() - t0) * 1000:.0f}ms, {v})"
    except Exception as e:
        try:
            s.close()
        except Exception:
            pass
        return f"FAIL({time.time() - t0:.2f}s, {str(e)[:40]})"

ips = [
    ("2404:6800:4003:18::4", "rr4---sn-ojnpo5-ci.googlevideo.com"),
    ("2404:6800:4003:18::2", "rr2---sn-ojnpo5-ci.googlevideo.com"),
    ("2404:6800:4003:c05::64", "redirector.googlevideo.com"),
    ("2001:4860:4846:400::", "youtubei.googleapis.com")
]

print("=== Probing with 0.8s delay (Simulating Sniffing Miss / No SNI) ===")
for ip, sni in ips:
    print(f"  {ip:<26} -> {probe(ip, sni, 0.8)}")

print("\n=== Probing with 0.0s delay (Normal Sniffing Path) ===")
for ip, sni in ips:
    print(f"  {ip:<26} -> {probe(ip, sni, 0.0)}")
