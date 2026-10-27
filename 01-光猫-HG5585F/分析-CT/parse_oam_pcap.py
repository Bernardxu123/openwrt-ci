#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 pon-debug 抓到的 OAM pcap（Ethernet + EtherType 0x8809）。"""
import struct
import sys

PCAP = sys.argv[1] if len(sys.argv) > 1 else None
if not PCAP:
    raise SystemExit("usage: parse_oam_pcap.py <pcap>")

data = open(PCAP, "rb").read()
magic = data[:4]
endian = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
_, _, _, _, _, _, network = struct.unpack_from(endian + "IHHIIII", data, 0)
print(f"pcap magic={magic.hex()} endian={endian} network={network} size={len(data)}")

off = 24
idx = 0
while off + 16 <= len(data):
    ts_sec, ts_usec, incl, orig = struct.unpack_from(endian + "IIII", data, off)
    off += 16
    pkt = data[off:off + incl]
    off += incl
    if len(pkt) < 14:
        continue
    dst = ":".join(f"{b:02x}" for b in pkt[0:6])
    src = ":".join(f"{b:02x}" for b in pkt[6:12])
    etype = int.from_bytes(pkt[12:14], "big")
    if etype != 0x8809:
        continue
    payload = pkt[14:]
    print(f"\n#{idx} ts={ts_sec}.{ts_usec:06d} dst={dst} src={src} len={len(pkt)}")
    if len(payload) < 4:
        print("  short payload:", payload.hex())
        idx += 1
        continue
    subtype = payload[0]
    flags = int.from_bytes(payload[1:3], "big")
    code = payload[3]
    print(f"  subtype=0x{subtype:02x} flags=0x{flags:04x} code=0x{code:02x} body={payload[4:].hex(' ')}")
    # TLVs after 4-byte OAM header
    t = payload[4:]
    p = 0
    while p + 2 <= len(t):
        typ, ln = t[p], t[p + 1]
        val = t[p + 2:p + ln]
        if ln < 2 or p + ln > len(t):
            print(f"  TLV@{p}: type=0x{typ:02x} len={ln} (truncated) rest={t[p:].hex(' ')}")
            break
        if typ == 0xfd and len(val) >= 3:
            oui = val[0:3].hex(" ")
            print(f"  TLV@{p}: org type=0xfd len={ln} OUI={oui} data={val[3:].hex(' ')}")
        else:
            print(f"  TLV@{p}: type=0x{typ:02x} len={ln} data={val.hex(' ')}")
        p += ln
    idx += 1
