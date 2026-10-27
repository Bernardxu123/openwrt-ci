#!/usr/bin/env python3
"""Convert the live OpenClash mihomo config into a nikki profile.

nikki runs mihomo with `-d /etc/nikki/run`, so relative provider paths would land
under /etc/nikki/run/.  We rewrite them to nikki's own provider directories
(/etc/nikki/run/providers/proxy and /etc/nikki/run/providers/rule).

Also:
  * fixed IDs: redir-port / tproxy-port / mixed-port are injected by nikki's mixin,
    so we drop the OpenClash-specific listener ports to avoid duplicated listeners
  * nikki supplies external-controller / secret / tun / dns basics via mixin;
    profile values that conflict are dropped
  * keeps: proxy-providers (url/interval/filter), proxies, proxy-groups,
           rule-providers, rules, dns nameserver-policy & fake-ip-filters

Usage: python tools/make_nikki_profile.py <in.yaml> <out.yaml>
"""
import re
import sys

# keys injected by nikki's ucode mixin -> drop from profile to avoid conflicts
DROP_SCALAR = [
    "port", "socks-port", "mixed-port", "redir-port", "tproxy-port",
    "external-controller", "secret", "allow-lan", "bind-address",
    "tun", "listeners",
]


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, encoding="utf-8").read().splitlines()
    out = []
    skip_block = None  # name of top-level block being skipped

    for ln in lines:
        stripped = ln.strip()
        indent = len(ln) - len(ln.lstrip())

        if indent == 0 and ln and not ln.startswith("#"):
            key = ln.split(":", 1)[0].strip()
            if key in DROP_SCALAR:
                skip_block = key
                out.append(f"# [nikki mixin 接管] {ln}")
                continue
            skip_block = None

        if skip_block:
            # keep comment placeholder, drop the block body
            out.append(f"# [nikki mixin 接管] {ln}")
            continue

        # rewrite provider paths
        if "path: ./proxy_provider/" in ln:
            name = ln.split("path:", 1)[1].strip()
            fname = name.rsplit("/", 1)[-1]
            ln = re.sub(r"path:.*", f"path: /etc/nikki/run/providers/proxy/{fname}", ln)
        elif "path: ./rule_provider/" in ln:
            name = ln.split("path:", 1)[1].strip()
            fname = name.rsplit("/", 1)[-1]
            ln = re.sub(r"path:.*", f"path: /etc/nikki/run/providers/rule/{fname}", ln)

        out.append(ln)

    text = "\n".join(out) + "\n"
    open(dst, "w", encoding="utf-8", newline="\n").write(text)
    print(f"wrote {dst} ({len(text)} bytes)")
    # sanity: show kept top-level keys
    keys = [l.split(":", 1)[0] for l in text.splitlines()
            if l and not l.startswith(" ") and not l.startswith("#") and ":" in l]
    print("top-level keys:", keys)


if __name__ == "__main__":
    main()
