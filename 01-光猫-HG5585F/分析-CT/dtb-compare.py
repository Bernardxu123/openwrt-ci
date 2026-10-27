#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract the handful of DTB facts that decide whether a HG5585F image fits a
CT (电信, 2.5G lan1) or CU (联通, 4x1G) board, and print a side-by-side table.

Works for both device-tree bindings seen in the wild:
  * OpenWrt 6.18 / ponwrt :  /soc/...            (ethernet@1fb50000/ethernet@4)
  * older Airoha 5.4 BSP  :  /...                 (ethernet@1fb50000/port@1)

Uses fit_probe.parse_fdt (pure Python), no dtc / libfdt needed.

Usage:
  python dtb-compare.py <a.dtb> [<b.dtb> ...]
Outputs dtb-key-compare.txt (stdout) and dtb-key-compare.json next to this file.
"""

import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_probe import parse_fdt, iter_nodes, prop_str, prop_u32  # noqa: E402


def get(root, *paths):
    """Return the first node matching any of the candidate paths."""
    for p, n in iter_nodes(root):
        if p in paths:
            return n
    return None


def one(val):
    """Decode a single-cell property to an int."""
    if val is None:
        return None
    u = prop_u32(val)
    if u and len(u) == 1:
        return u[0]
    return list(u) if u is not None else None


def gpio_tuple(val):
    """Decode a gpios-like payload: <&phandle pin flags>."""
    if not val or len(val) % 4:
        return None
    u = list(struct.unpack(">%dI" % (len(val) // 4), val))
    if len(u) >= 3:
        return {"phandle": u[0], "pin": u[1], "flags": u[2]}
    return {"raw": u}


def summarize(path):
    data = open(path, "rb").read()
    root, header = parse_fdt(data)
    out = {
        "file": os.path.abspath(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "fdt_totalsize": header["totalsize"],
        "nodes": len(list(iter_nodes(root))),
    }

    def prop(*paths_and_name):
        *paths, name = paths_and_name
        n = get(root, *paths)
        return n["props"].get(name) if n else None

    def s(*paths_and_name):
        v = prop(*paths_and_name)
        return prop_str(v) if v is not None else None

    root_compat = root["props"].get("compatible", b"")
    out["model"] = s("", "model")
    out["compatible"] = [x for x in prop_str(root_compat).split("\x00") if x]

    chosen = get(root, "/chosen")
    if chosen and "rootdisk" in chosen["props"]:
        out["chosen/rootdisk_phandle"] = one(chosen["props"]["rootdisk"])

    # --- lan1 wiring: dedicated 2.5G MAC (CT) vs switch port 1 (CU) --------
    ETH4 = ("/soc/ethernet@1fb50000/ethernet@4", "/ethernet@1fb50000/ethernet@4")
    out["eth@4.status"] = s(*ETH4, "status")
    out["eth@4.phy-mode"] = s(*ETH4, "phy-mode")
    out["eth@4.netdev"] = s(*ETH4, "openwrt,netdev-name")
    out["eth@4.phy-handle_phandle"] = one(prop(*ETH4, "phy-handle"))

    PCS = ("/soc/pcs@1fa09000", "/pcs@1fa09000")
    out["pcs@1fa09000.status"] = s(*PCS, "status")

    # --- external MaxLinear GPY211C behind the switch MDIO bus -------------
    PHY7 = ("/soc/switch@1fb58000/mdio/ethernet-phy@7",
            "/mdio@1fb5f01c/ethernet-phy@7")
    out["mdio/phy@7.compatible"] = s(*PHY7, "compatible")
    out["mdio/phy@7.reg"] = one(prop(*PHY7, "reg"))
    out["mdio/phy@7.reset-gpios"] = gpio_tuple(prop(*PHY7, "reset-gpios"))
    out["mdio/phy@7.reset-assert-us"] = one(prop(*PHY7, "reset-assert-us"))
    out["mdio/phy@7.reset-deassert-us"] = one(prop(*PHY7, "reset-deassert-us"))

    # --- switch port 1 (CU uses the internal PHY1 for lan1) ----------------
    P1 = ("/soc/switch@1fb58000/ports/port@1", "/ethernet@1fb50000/port@1")
    out["switch/port@1.status"] = s(*P1, "status")
    out["switch/port@1.label"] = s(*P1, "label")
    out["switch/port@1.phy-mode"] = s(*P1, "phy-mode")
    PHY9 = ("/soc/switch@1fb58000/mdio/ethernet-phy@9",
            "/mdio@1fb5f01c/ethernet-phy@9")
    out["mdio/phy@9.status"] = s(*PHY9, "status")

    # --- reset key ---------------------------------------------------------
    KR = ("/keys/key-reset", "/keys/reset")
    out["keys/reset.label"] = s(*KR, "label")
    out["keys/reset.gpios"] = gpio_tuple(prop(*KR, "gpios"))
    out["keys/reset.linux,code"] = one(prop(*KR, "linux,code"))

    # --- factory nvmem layout (same on both boards?) -----------------------
    nln = get(root,
              "/soc/nand-controller@1fa11000/nand@0/partitions/partition@20000/volumes/ubi-volume-factory/nvmem-layout")
    layout = {}
    if nln:
        for c in nln["children"]:
            layout[c["name"]] = prop_u32(c["props"].get("reg", b""))
    out["factory_nvmem_layout"] = layout

    # --- UBI volume list ---------------------------------------------------
    vols = []
    for p, n in iter_nodes(root):
        parent, _, _leaf = p.rpartition("/")
        if parent.endswith("/volumes"):
            vols.append({"node": n["name"],
                         "volname": prop_str(n["props"].get("volname", b""))})
    out["ubi_volumes"] = vols

    # --- LEDs --------------------------------------------------------------
    leds = []
    ln = get(root, "/leds")
    if ln:
        for c in ln["children"]:
            pr = c["props"]
            rec = {"node": c["name"]}
            for k in ("label", "function"):
                if k in pr:
                    rec[k] = prop_str(pr[k])
            if "function-enumerator" in pr:
                rec["function-enumerator"] = one(pr["function-enumerator"])
            leds.append(rec)
    out["leds"] = leds
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows = [summarize(p) for p in argv[1:]]
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "dtb-key-compare.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)

    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    names = [os.path.basename(os.path.dirname(r["file"])) + "/" + os.path.basename(r["file"])
             for r in rows]
    w = 30
    print("KEY".ljust(w) + "".join(n[:36].ljust(38) for n in names))
    for k in keys:
        if k == "file":
            continue
        vals = []
        for r in rows:
            v = r.get(k)
            vals.append(json.dumps(v, ensure_ascii=False) if v is not None else "-")
        print(str(k).ljust(w) + "".join(v[:36].ljust(38) for v in vals))
    print()
    print("WROTE %s" % os.path.join(here, "dtb-key-compare.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
