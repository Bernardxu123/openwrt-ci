#!/usr/bin/env python3
"""Minimal protobuf reader for v2ray/dae geosite.dat.

GeoSite   { repeated GeoSiteList site = 1; }
GeoSiteList { string type = 1; repeated Domain domain = 2; }
Domain    { Domain_Type type = 1; string value = 2; }
"""
import sys


def read_varint(buf, i):
    shift = 0
    val = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def parse_fields(buf):
    """Yield (field_no, wire_type, payload_bytes_or_int)."""
    i = 0
    n = len(buf)
    while i < n:
        key, i = read_varint(buf, i)
        fno, wt = key >> 3, key & 7
        if wt == 0:
            v, i = read_varint(buf, i)
            yield fno, wt, v
        elif wt == 2:
            ln, i = read_varint(buf, i)
            yield fno, wt, buf[i:i + ln]
            i += ln
        elif wt == 5:
            yield fno, wt, buf[i:i + 4]
            i += 4
        elif wt == 1:
            yield fno, wt, buf[i:i + 8]
            i += 8
        else:
            raise ValueError("wire type %d" % wt)


def main():
    path = sys.argv[1]
    target = sys.argv[2].lower()
    with open(path, "rb") as f:
        data = f.read()
    sys.stdout.reconfigure(encoding="utf-8")

    hits = []
    ncat = 0
    for fno, wt, payload in parse_fields(data):
        if fno != 1 or wt != 2:
            continue
        ncat += 1
        cat = None
        domains = []
        for sf, swt, sp in parse_fields(payload):
            if sf == 1 and swt == 2:
                cat = sp.decode("utf-8", "replace")
            elif sf == 2 and swt == 2:
                val = None
                for df, dwt, dp in parse_fields(sp):
                    if df == 2 and dwt == 2:
                        val = dp.decode("utf-8", "replace")
                if val:
                    domains.append(val)
        if cat and any(target in d.lower() for d in domains):
            hits.append((cat, [d for d in domains if target in d.lower()]))

    print("categories parsed:", ncat)
    print("=== categories containing %r ===" % target)
    for cat, ds in hits:
        print("  %-28s %s" % (cat, ds))
    if not hits:
        print("  (none)")


if __name__ == "__main__":
    main()
