#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 fiberhome-factory 产出的 1 MiB factory 镜像（ponwrt/QWRT board data）。

五项硬指标（与 pbs05/fiberhome-factory 的 model.rs 一致）：
  0x0000  2 KiB  APONCAL 容器（magic/version/header_size/chip/format/payload len/CRC）
  0x1000  4 KiB  MT7916 EEPROM（device id 必须 0x7916，即字节 16 79）
  0x2000  6 B    Base MAC
  0x2010  8 B    PON SN（FHTT + 4 字节）
  0x2020  32 B   Device SN（ASCII，右侧补 0）
"""
import argparse
import sys

SIZE = 0x100000
PON_OFF = 0x0000
PON_SIZE = 0x0800
WIFI_OFF = 0x1000
WIFI_SIZE = 0x1000
MAC_OFF = 0x2000
SN_OFF = 0x2010
DEV_OFF = 0x2020


def crc32_reg(data, crc):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & (0xFFFFFFFF if crc & 1 else 0))
            crc &= 0xFFFFFFFF
    return crc


def cal_crc(data):
    return crc32_reg(data, 0xFFFFFFFF) ^ 0xFFFFFFFF


def u16(d, o):
    return int.from_bytes(d[o:o + 2], "little")


def u32(d, o):
    return int.from_bytes(d[o:o + 4], "little")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--mac", default="", help="期望 MAC，如 70:D5:1E:06:9C:78")
    ap.add_argument("--pon-sn", default="", help="期望 PON SN（16 hex），如 46485454C123E98A")
    ap.add_argument("--device-sn", default="", help="期望设备 SN（ASCII）")
    ap.add_argument("--eeprom-source", default="", help="JFFS2 的 AX3000...EEPROM 文件，用于对比前 4 KiB")
    a = ap.parse_args()

    d = open(a.image, "rb").read()
    ok = True
    print(f"file : {a.image}")
    print(f"size : {len(d)} (0x{len(d):x})  {'OK' if len(d) == SIZE else 'FAIL, 期望 1048576'}")
    if len(d) != SIZE:
        return 1

    print("\n[1] APONCAL @0x0")
    magic = d[PON_OFF:PON_OFF + 8]
    ver = u16(d, 0x08)
    hsz = u16(d, 0x0A)
    chip = u32(d, 0x0C)
    fmt = u32(d, 0x10)
    plen = u32(d, 0x14)
    pcrc = u32(d, 0x18)
    hcrc = u32(d, 0x7C)
    chip_name = {1: "GN28L95", 2: "UX3363"}.get(chip, f"unknown({chip})")
    hcrc_calc = cal_crc(d[PON_OFF:PON_OFF + 0x7C])
    pcrc_calc = cal_crc(d[PON_OFF + 0x80:PON_OFF + 0x80 + plen]) if plen <= PON_SIZE - 0x80 else -1
    print(f"  magic={magic!r}  version={ver}  header_size={hsz}  chip={chip_name}  format={fmt}")
    print(f"  payload_len={plen}  payload_crc=0x{pcrc:08x} (calc 0x{pcrc_calc:08x})  header_crc=0x{hcrc:08x} (calc 0x{hcrc_calc:08x})")
    for name, cond in [
        ("magic=APONCAL\\0", magic == b"APONCAL\0"),
        ("version=1", ver == 1),
        ("header_size=0x80", hsz == 0x80),
        ("chip 1/2", chip in (1, 2)),
        ("format=1", fmt == 1),
        ("payload_len<=1920", 0 < plen <= PON_SIZE - 0x80),
        ("payload CRC", pcrc == pcrc_calc),
        ("header CRC", hcrc == hcrc_calc),
    ]:
        print(f"    {'OK  ' if cond else 'FAIL'} {name}")
        ok &= cond

    print("\n[2] MT7916 EEPROM @0x1000")
    eep = d[WIFI_OFF:WIFI_OFF + WIFI_SIZE]
    devid = u16(eep, 0)
    print(f"  first16={eep[:16].hex(' ')}  device_id=0x{devid:04x}  {'OK' if devid == 0x7916 else 'FAIL'}")
    ok &= devid == 0x7916
    if a.eeprom_source:
        src = open(a.eeprom_source, "rb").read()[:WIFI_SIZE]
        same = src == eep
        print(f"  与 {a.eeprom_source} 前 4KiB 对比：{'OK 完全一致' if same else 'FAIL 不一致'}")
        ok &= same

    print("\n[3] Base MAC @0x2000")
    mac = ":".join(f"{b:02X}" for b in d[MAC_OFF:MAC_OFF + 6])
    print(f"  image = {mac}")
    if a.mac:
        want = a.mac.upper().replace("-", ":")
        print(f"  expect= {want}  {'OK' if mac == want else 'FAIL'}")
        ok &= mac == want

    print("\n[4] PON SN @0x2010")
    sn = d[SN_OFF:SN_OFF + 8]
    print(f"  image = {sn.hex().upper()}  ({sn[:4]!r} + {sn[4:].hex().upper()})")
    if a.pon_sn:
        want = a.pon_sn.upper().replace(":", "")
        print(f"  expect= {want}  {'OK' if sn.hex().upper() == want else 'FAIL'}")
        ok &= sn.hex().upper() == want

    print("\n[5] Device SN @0x2020")
    raw = d[DEV_OFF:DEV_OFF + 32]
    text = raw.rstrip(b"\x00").decode("ascii", "replace")
    print(f"  image = {text!r}")
    print(f"  hex   = {raw.hex(' ')}")
    if a.device_sn:
        want = a.device_sn
        print(f"  expect= {want!r}  {'OK' if text == want else 'FAIL'}")
        ok &= text == want

    print("\n结果：", "全部通过" if ok else "存在 FAIL，先不要写板级数据")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
