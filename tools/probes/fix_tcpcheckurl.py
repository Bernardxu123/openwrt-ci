#!/usr/bin/env python3
"""Fix daed health-check DNS resolution: add explicit IPs to tcpCheckUrl.

Root cause: dae resolves the tcp_check_url hostname via the "system DNS"
(first non-loopback nameserver in /etc/resolv.conf, else global.fallbackResolver).
This router's resolv.conf is loopback-only (dnsmasq), so it dials 223.5.5.5:53
directly and that query fails -> every node latency test aborts with
"failed to parse tcp_check_url: ResolveIp46: no valid ip for cp.cloudflare.com".
udpCheckDns already carries explicit IPs; tcpCheckUrl did not.
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "tmp")
from daed import gql, token  # noqa: E402

CFG_ID = "Y3Vyc29yMQ"

GLOBAL = {
    "logLevel": "info",
    "dialMode": "domain",
    "sniffingTimeout": "100ms",
    # Only change vs. current config: explicit IPs appended (bypasses resolution)
    "tcpCheckUrl": [
        "http://cp.cloudflare.com",
        "104.16.132.229",
        "104.16.133.229",
        "2606:4700::6810:84e5",
        "2606:4700::6810:85e5",
    ],
    "udpCheckDns": ["dns.google:53", "8.8.8.8", "2001:4860:4860::8888"],
    "checkInterval": "3m0s",
    "checkTolerance": "100ms",
    "autoConfigKernelParameter": True,
    "autoConfigFirewallRule": False,
    "disableWaitingNetwork": False,
    "tcpCheckHttpMethod": "HEAD",
    "allowInsecure": False,
    "tlsImplementation": "tls",
    "utlsImitate": "chrome_auto",
    "mptcp": False,
    "disableThp": True,
    "enableLocalTcpFastRedirect": False,
    "tproxyPort": 12345,
    "tproxyPortProtect": True,
    "soMarkFromDae": 0,
    "soMarkFromDaeSet": True,
    "pprofPort": 0,
    "bpfConnStateMapSize": 262144,
    "lanInterface": ["br-lan"],
    "wanInterface": ["auto"],
    "bootstrapResolver": "",
    "fallbackResolver": "223.5.5.5:53",
    "bandwidthMaxTx": "200 mbps",
    "bandwidthMaxRx": "1 gbps",
    "udphopInterval": "30s",
    "tlsFragment": False,
    "tlsFragmentLength": "50-100",
    "tlsFragmentInterval": "10-20",
}

MUT = """mutation($id:ID!,$g:globalInput!){
  updateConfig(id:$id, global:$g){ id }
}"""


def main():
    tok = token()
    r = gql(MUT, tok, variables={"id": CFG_ID, "g": GLOBAL})
    print("updateConfig:", json.dumps(r, ensure_ascii=False))
    if "errors" in r:
        sys.exit("updateConfig failed")
    r = gql("mutation{ run(dry:false) }", tok, timeout=120)
    print("run:", json.dumps(r, ensure_ascii=False)[:500])
    if "errors" in r:
        sys.exit("run failed")


if __name__ == "__main__":
    main()
