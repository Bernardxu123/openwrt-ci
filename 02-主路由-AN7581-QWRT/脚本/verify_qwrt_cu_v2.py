#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_qwrt_cu_v2.py — QWRT CU 改造包校验器（只读）

校验层次：
  A. FIT 容器：magic / totalsize / 三镜像 data-position & data-size
  B. 镜像完整性：kernel-1 / fdt-1 / rootfs-1 的 crc32 + sha1 全部重算
  C. fwtool：两层 footer（FWx0+crc+type+size）CRC，先内层 type=1 再外层 type=0
  D. metadata JSON：可解析、supported_devices / board / 长度
  E. DTB 严格结构校验：header 一致性、offset 合法、token 嵌套、
     属性名偏移、phandle 唯一、所有 *-handle 引用可解析、FDT_END 收尾
  F. DTB 语义断言（按 --expect 分支）
  G. 与 CT 基线的逐节点/逐属性差分（cu 模式必须恰好等于预期 7 项）

用法:
  python verify_qwrt_cu_v2.py IMAGE.itb --expect cu|control|ct-baseline [--baseline CT.itb]
  python verify_qwrt_cu_v2.py --self-test
"""

import argparse
import hashlib
import json
import struct
import sys
import zlib

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
FWX0 = b"FWx0"

ETH = "/ethernet@1fb50000"
PORT1 = ETH + "/port@1"
PORT2 = ETH + "/port@2"
PORT3 = ETH + "/port@3"
PORT4 = ETH + "/port@4"
MDIO = "/mdio@1fb5f01c"
PHY7 = MDIO + "/ethernet-phy@7"
PHY9 = MDIO + "/ethernet-phy@9"
PHYA = MDIO + "/ethernet-phy@a"
KEYS_RESET = "/keys/reset"


def be32(v):
    return struct.pack(">I", v)


def a4(n):
    return (n + 3) & ~3


def std_crc32(data):
    return (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF


class Result(object):
    def __init__(self):
        self.items = []

    def check(self, ok, name, detail=""):
        self.items.append((bool(ok), name, detail))
        return ok

    def fail_count(self):
        return sum(1 for ok, _, _ in self.items if not ok)

    def report(self, title):
        print("\n=== %s ===" % title)
        for ok, name, detail in self.items:
            mark = "PASS" if ok else "FAIL"
            line = "  [%s] %s" % (mark, name)
            if detail:
                line += "  -- " + detail
            print(line)
        bad = self.fail_count()
        print("  -> %s（%d 项，失败 %d）" % ("PASS" if bad == 0 else "FAIL", len(self.items), bad))
        return bad == 0


# ---------------------------------------------------------------- DTB 严格校验

class BadFdt(Exception):
    pass


def fdt_validate(blob):
    """独立实现的严格 FDT 结构校验；返回 (header dict, paths, phandles, refs)。"""
    if len(blob) < 40:
        raise BadFdt("长度 < 40")
    (magic, totalsize, off_struct, off_strings, off_rsv, ver, lastcomp,
     cpuid, sstr, sstruct) = struct.unpack(">10I", blob[:40])
    hdr = dict(magic=magic, totalsize=totalsize, off_dt_struct=off_struct,
               off_dt_strings=off_strings, off_mem_rsvmap=off_rsv,
               version=ver, last_comp_version=lastcomp,
               boot_cpuid_phys=cpuid, size_dt_strings=sstr, size_dt_struct=sstruct)
    if magic != FDT_MAGIC:
        raise BadFdt("magic 0x%08x" % magic)
    if totalsize > len(blob):
        raise BadFdt("totalsize %d > 容器 %d" % (totalsize, len(blob)))
    if totalsize < 40:
        raise BadFdt("totalsize 过小")
    if not (16 <= ver <= 17):
        raise BadFdt("version %d 非法" % ver)
    if lastcomp > 17:
        raise BadFdt("last_comp_version %d" % lastcomp)
    if off_rsv % 8:
        raise BadFdt("off_mem_rsvmap 未 8 字节对齐")
    if off_rsv + 16 > totalsize:
        raise BadFdt("rsvmap 越界")
    if off_struct < off_rsv + 16 or off_struct >= totalsize:
        raise BadFdt("off_dt_struct 非法")
    if off_struct + sstruct > totalsize:
        raise BadFdt("struct 块越界")
    if off_strings + sstr > totalsize:
        raise BadFdt("strings 块越界")
    strings = blob[off_strings:off_strings + sstr]

    rsv = []
    p = off_rsv
    while True:
        if p + 16 > totalsize:
            raise BadFdt("rsvmap 未终止")
        a, s = struct.unpack(">QQ", blob[p:p + 16])
        p += 16
        if a == 0 and s == 0:
            break
        rsv.append((a, s))
        if len(rsv) > 64:
            raise BadFdt("rsvmap 条目过多")

    paths = {}
    phandles = {}
    refs = []
    pos, end = off_struct, off_struct + sstruct
    stack = []
    saw_end = False
    while pos < end:
        if pos + 4 > end:
            raise BadFdt("token 截断")
        (tok,) = struct.unpack(">I", blob[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            e = blob.find(b"\0", pos, end)
            if e < 0:
                raise BadFdt("节点名未终止")
            name = blob[pos:e].decode("utf-8")
            pos = a4(e + 1)
            if not stack and name != "":
                raise BadFdt("根节点名非空: %r" % name)
            stack.append(name)
            path = "/" + "/".join([x for x in stack if x])
            if path in paths:
                raise BadFdt("重复节点路径 %s" % path)
            paths[path] = []
        elif tok == FDT_END_NODE:
            if not stack:
                raise BadFdt("END_NODE 下溢")
            stack.pop()
        elif tok == FDT_PROP:
            if not stack:
                raise BadFdt("属性在节点之外")
            ln, noff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            if noff >= sstr:
                raise BadFdt("nameoff %d >= %d" % (noff, sstr))
            e = strings.find(b"\0", noff)
            if e < 0:
                raise BadFdt("属性名未终止")
            pname = strings[noff:e].decode("utf-8")
            if pos + ln > end:
                raise BadFdt("属性值越界: %s" % pname)
            val = blob[pos:pos + ln]
            pos = a4(pos + ln)
            if pos > end:
                raise BadFdt("属性值对齐越界: %s" % pname)
            path = "/" + "/".join([x for x in stack if x])
            paths[path].append((pname, val))
            if pname in ("phandle", "linux,phandle"):
                if ln != 4:
                    raise BadFdt("%s 长度 %d" % (pname, ln))
                v = struct.unpack(">I", val)[0]
                if v in phandles:
                    raise BadFdt("重复 phandle %d" % v)
                phandles[v] = path
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            saw_end = True
            break
        else:
            raise BadFdt("未知 token 0x%x" % tok)
    if not saw_end:
        raise BadFdt("缺 FDT_END")
    if stack:
        raise BadFdt("节点未闭合，深度 %d" % len(stack))

    # 引用解析
    for path, props in paths.items():
        for pname, val in props:
            if pname in ("phandle", "linux,phandle"):
                continue
            if not (pname.endswith("-handle") or pname in ("interrupt-parent", "next-level-cache")):
                continue
            if len(val) == 4:
                v = struct.unpack(">I", val)[0]
                if v not in phandles:
                    raise BadFdt("%s 的 %s=%d 无法解析" % (path, pname, v))
                refs.append((path, pname, v, phandles[v]))
            elif len(val) % 4 == 0 and val:
                for i in range(0, len(val), 4):
                    v = struct.unpack(">I", val[i:i + 4])[0]
                    if v not in phandles:
                        raise BadFdt("%s 的 %s[%d]=%d 无法解析" % (path, pname, i // 4, v))
                    refs.append((path, pname, v, phandles[v]))
    return hdr, paths, phandles, refs


def props(paths, path):
    return dict(paths.get(path, []))


# ---------------------------------------------------------------- FIT

def fit_parse(blob):
    hdr, paths, phandles, _ = fdt_validate(blob)  # FIT 本身就是个 FDT
    return hdr, paths, phandles


def prop_str(val):
    return val.split(b"\0")[0].decode("utf-8", "replace")


def fdt_check_full(blob, bufsize):
    """逐条照抄 libfdt fdt_check_full()（uboot-an758x/scripts/dtc/libfdt/fdt_ro.c:889）。

    U-Boot 网页刷机走的就是这个函数（net/lwip/httpd.c: validate_firmware_fit），
    比 OpenWrt 的 fit_check_sign 严：**根节点 END_NODE 之后只允许紧跟 FDT_END**，
    否则返回 -FDT_ERR_BADLAYOUT → "Firmware device tree is invalid."
    返回 (ok, 说明)。
    """
    if len(blob) < 40:
        return False, "bufsize < FDT_V1_SIZE"
    if bufsize < 28:
        return False, "bufsize < FDT_V1_SIZE"
    (magic, totalsize, off_struct, off_strings, off_rsv, ver, lastcomp,
     cpuid, sstr, sstruct) = struct.unpack(">10I", blob[:40])
    if magic != FDT_MAGIC:
        return False, "fdt_check_header: BADMAGIC"
    if ver < 16:
        return False, "fdt_check_header: BADVERSION(version=%d)" % ver
    if lastcomp > 17:
        return False, "fdt_check_header: BADVERSION(last_comp_version=%d)" % lastcomp
    if totalsize > len(blob):
        return False, "fdt_check_header: totalsize > 容器"
    if off_struct > 0xFFFFFFFF - sstruct:
        return False, "fdt_check_header: BADOFFSET"
    if off_struct + sstruct > totalsize:
        return False, "fdt_check_header: struct 越界"
    if off_strings + sstr > totalsize:
        return False, "fdt_check_header: strings 越界"
    if off_rsv + 16 > totalsize:
        return False, "fdt_check_header: rsvmap 越界"
    if bufsize < totalsize:
        return False, "bufsize(%d) < totalsize(%d)" % (bufsize, totalsize)

    strings = blob[off_strings:off_strings + sstr]
    # fdt_num_mem_rsv
    p = off_rsv
    n = 0
    while True:
        if p + 16 > totalsize:
            return False, "fdt_num_mem_rsv: rsvmap 未终止"
        a, b = struct.unpack(">QQ", blob[p:p + 16])
        p += 16
        if a == 0 and b == 0:
            break
        n += 1
        if n > 64:
            return False, "fdt_num_mem_rsv: 条目过多"

    a4 = lambda x: (x + 3) & ~3
    pos, end = off_struct, off_struct + sstruct
    depth = 0
    expect_end = False
    while True:
        if pos + 4 > end:
            return False, "fdt_next_tag: 越过 struct 块"
        (tag,) = struct.unpack(">I", blob[pos:pos + 4])
        off_here = pos
        pos += 4
        # libfdt: expect_end && tag != FDT_END -> BADLAYOUT
        if expect_end and tag != FDT_END:
            return False, ("BADLAYOUT: 根节点 END_NODE(0x%x) 之后出现 tag=0x%x（只允许 FDT_END）"
                           % (off_here - 4, tag))
        if tag == FDT_NOP:
            continue
        if tag == FDT_END:
            if depth != 0:
                return False, "FDT_END 时 depth=%d != 0" % depth
            return True, "OK (depth=0, totalsize=%d)" % totalsize
        if tag == FDT_BEGIN_NODE:
            e = blob.find(b"\0", pos, end)
            if e < 0:
                return False, "节点名未终止"
            name = blob[pos:e]
            pos = a4(e + 1)
            depth += 1
            if depth == 1 and name != b"":
                return False, "根节点名非空"
            continue
        if tag == FDT_END_NODE:
            if depth == 0:
                return False, "END_NODE 时 depth 已为 0"
            depth -= 1
            if depth == 0:
                expect_end = True
            continue
        if tag == FDT_PROP:
            if pos + 8 > end:
                return False, "属性头截断"
            ln, noff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            if noff >= sstr:
                return False, "fdt_getprop_by_offset: nameoff %d >= %d" % (noff, sstr)
            if strings.find(b"\0", noff) < 0:
                return False, "fdt_getprop_by_offset: 属性名未终止"
            if pos + ln > end:
                return False, "属性值越界"
            pos = a4(pos + ln)
            continue
        return False, "未知 tag 0x%x" % tag


def load_dtb_bytes(path):
    """从 .itb(FIT) 里取出 fdt-1；若文件本身就是裸 DTB 则原样返回。"""
    raw = open(path, "rb").read()
    try:
        _, paths, _ = fit_parse(raw)
        if "/images/fdt-1" in paths:
            d = props(paths, "/images/fdt-1")
            dp = struct.unpack(">I", d["data-position"])[0]
            ds = struct.unpack(">I", d["data-size"])[0]
            return raw[dp:dp + ds]
    except BadFdt:
        pass
    return raw


def check_image(path, expect, baseline=None, verbose=True):
    res = Result()
    raw = open(path, "rb").read()
    if verbose:
        print("\n" + "#" * 78)
        print("# %s  (%d 字节, sha256=%s...)" % (path, len(raw), hashlib.sha256(raw).hexdigest()[:16]))

    # ---- A. FIT
    try:
        hdr, paths, phandles = fit_parse(raw)
        fit_ok = True
    except BadFdt as e:
        res.check(False, "FIT 容器可解析", str(e))
        res.report(path)
        return res
    res.check(fit_ok, "FIT 容器可解析", "totalsize=%d 节点=%d" % (hdr["totalsize"], len(paths)))
    imgs = {}
    for p in paths:
        if p.startswith("/images/") and p.count("/") == 2:
            d = props(paths, p)
            if "data-position" in d and "data-size" in d:
                imgs[p.rsplit("/", 1)[1]] = (
                    struct.unpack(">I", d["data-position"])[0],
                    struct.unpack(">I", d["data-size"])[0])
    res.check(set(imgs) == {"kernel-1", "fdt-1", "rootfs-1"},
              "FIT 含三镜像", str(sorted(imgs)))
    cfg = props(paths, "/configurations/config@1")
    res.check(prop_str(cfg.get("kernel", b"")) == "kernel-1" and
              prop_str(cfg.get("fdt", b"")) == "fdt-1" and
              prop_str(cfg.get("loadables", b"")) == "rootfs-1",
              "config@1 引用正确",
              "kernel=%s fdt=%s loadables=%s" % (
                  prop_str(cfg.get("kernel", b"")), prop_str(cfg.get("fdt", b"")),
                  prop_str(cfg.get("loadables", b""))))
    res.check(prop_str(props(paths, "/configurations").get("default", b"")) == "config@1",
              "默认配置 = config@1")

    # ---- B. 镜像 hash
    for img, (dp, ds) in sorted(imgs.items()):
        if dp + ds > len(raw):
            res.check(False, "%s 数据越界" % img, "pos=0x%x size=%d" % (dp, ds))
            continue
        blob = raw[dp:dp + ds]
        h1 = props(paths, "/images/%s/hash-1" % img)
        h2 = props(paths, "/images/%s/hash-2" % img)
        algo1 = prop_str(h1.get("algo", b""))
        algo2 = prop_str(h2.get("algo", b""))
        ok1 = ok2 = False
        det1 = det2 = ""
        if algo1 == "crc32" and len(h1.get("value", b"")) == 4:
            calc = zlib.crc32(blob) & 0xFFFFFFFF
            stored = struct.unpack(">I", h1["value"])[0] & 0xFFFFFFFF
            ok1 = calc == stored
            det1 = "0x%08x" % calc
        if algo2 == "sha1" and len(h2.get("value", b"")) == 20:
            ok2 = hashlib.sha1(blob).digest() == h2["value"]
            det2 = hashlib.sha1(blob).hexdigest()[:16] + "..."
        res.check(ok1, "%s crc32" % img, det1)
        res.check(ok2, "%s sha1" % img, det2)

    # ---- C. fwtool footer
    sig = raw.rfind(FWX0)
    info = raw.rfind(FWX0, 0, sig) if sig > 0 else -1
    ok = sig > 0 and sig + 16 == len(raw) and info > 0
    res.check(ok, "两层 footer 定位", "info@0x%x sig@0x%x" % (info, sig))
    if ok:
        c_info = struct.unpack(">I", raw[info + 4:info + 8])[0]
        c_sig = struct.unpack(">I", raw[sig + 4:sig + 8])[0]
        res.check(std_crc32(raw[:info]) == c_info, "info footer CRC",
                  "stored=0x%08x calc=0x%08x" % (c_info, std_crc32(raw[:info])))
        res.check(std_crc32(raw[:sig]) == c_sig, "signature footer CRC",
                  "stored=0x%08x calc=0x%08x" % (c_sig, std_crc32(raw[:sig])))
        # ---- D. metadata
        k = raw.find(b'"metadata_version"', 0, info)
        js = raw.rfind(b"{", 0, k) if k > 0 else -1
        je = raw.rfind(b"}", js, info) if js > 0 else -1
        if js < 0 or je < 0:
            res.check(False, "metadata JSON 定位")
        else:
            mtext = raw[js:je + 1]
            try:
                meta = json.loads(mtext.decode("utf-8"))
                res.check(True, "metadata JSON 可解析")
            except Exception as e:
                meta = None
                res.check(False, "metadata JSON 可解析", str(e))
            if meta is not None:
                sd = meta.get("supported_devices") or []
                board = (meta.get("version") or {}).get("board", "")
                if expect in ("cu", "control"):
                    res.check("fiberhome,hg5585f-cu" in sd, "supported_devices 含 cu", str(sd))
                    res.check(board == "fiberhome_hg5585f-cu", "board = fiberhome_hg5585f_cu", board)
                    res.check(all("hg5585f-ct" not in x for x in sd), "supported_devices 无 ct 残留", str(sd))
                else:
                    res.check("fiberhome,hg5585f-ct" in sd, "supported_devices 含 ct", str(sd))
                    res.check(board == "fiberhome_hg5585f-ct", "board = fiberhome_hg5585f_ct", board)

    # ---- E. DTB 结构
    if "fdt-1" in imgs:
        dp, ds = imgs["fdt-1"]
        dtb = raw[dp:dp + ds]
        try:
            dh, dpaths, dph, drefs = fdt_validate(dtb)
            res.check(True, "DTB 严格结构校验",
                      "nodes=%d phandles=%d refs=%d" % (len(dpaths), len(dph), len(drefs)))
        except BadFdt as e:
            res.check(False, "DTB 严格结构校验", str(e))
            res.report(path)
            return res
        res.check(dh["totalsize"] == ds, "DTB totalsize == FIT data-size",
                  "totalsize=%d data-size=%d" % (dh["totalsize"], ds))
        # U-Boot 网页刷机同款校验（fdt_check_full）
        ok_full, why_full = fdt_check_full(dtb, ds)
        res.check(ok_full, "fdt_check_full（U-Boot 网页刷机同款）", why_full)

        # ---- F. 语义断言
        if expect == "cu":
            p1 = props(dpaths, PORT1)
            res.check("phy-mode" not in p1, "port@1 无 phy-mode",
                      "props=%s" % sorted(p1))
            if "phy-handle" in p1 and len(p1["phy-handle"]) == 4:
                v = struct.unpack(">I", p1["phy-handle"])[0]
                tgt = dph.get(v)
                res.check(tgt == PHY9, "port@1 phy-handle -> ethernet-phy@9",
                          "phandle=%d -> %s" % (v, tgt))
            else:
                res.check(False, "port@1 phy-handle 存在且为 4 字节")
            res.check(PHY7 not in dpaths, "ethernet-phy@7 已删除")
            p9 = props(dpaths, PHY9)
            res.check("phandle" in p9, "phy@9 有 phandle")
            res.check(prop_str(props(dpaths, "/").get("compatible", b"")).startswith("fiberhome,hg5585f-cu"),
                      "/compatible = fiberhome,hg5585f-cu",
                      prop_str(props(dpaths, "/").get("compatible", b"")))
            res.check(prop_str(props(dpaths, "/").get("model", b"")) == "FiberHome HG5585F CU",
                      "/model = FiberHome HG5585F CU",
                      prop_str(props(dpaths, "/").get("model", b"")))
            gp = props(dpaths, KEYS_RESET).get("gpios")
            ok = gp is not None and len(gp) == 12 and struct.unpack(">III", gp)[1] == 35
            res.check(ok, "keys/reset GPIO = 35",
                      str(struct.unpack(">III", gp)) if gp and len(gp) == 12 else repr(gp))
            # port@2/3/4 必须保持无 phy-mode（与改造前一致）
            for pth in (PORT2, PORT3, PORT4):
                res.check("phy-mode" not in props(dpaths, pth),
                          "%s 无 phy-mode" % pth.rsplit("/", 1)[1])
        elif expect == "control":
            res.check(PHY7 in dpaths, "control 模式保留 phy@7")
            res.check(prop_str(props(dpaths, PORT1).get("phy-mode", b"")) == "2500base-x",
                      "control 模式 port@1 仍为 2500base-x")
        else:  # ct-baseline
            res.check(PHY7 in dpaths, "CT 基线含 phy@7")
            res.check(prop_str(props(dpaths, PORT1).get("phy-mode", b"")) == "2500base-x",
                      "CT 基线 port@1 phy-mode=2500base-x")

        # ---- G. 与基线差分
        if baseline:
            bdtb = load_dtb_bytes(baseline)
            try:
                bh, bpaths, bph, _ = fdt_validate(bdtb)
            except BadFdt as e:
                res.check(False, "基线 DTB 可解析", str(e))
                bpaths = None
            if bpaths is not None:
                if expect == "control":
                    res.check(dtb == bdtb,
                              "control 模式 DTB 与基线逐字节一致",
                              "len %d vs %d" % (len(dtb), len(bdtb)))
                diffs = diff_trees(bpaths, dpaths)
                if expect == "cu":
                    ok, detail = check_expected_diff(diffs, dpaths, bpaths)
                    res.check(ok, "DTB 差分 = 预期 7 项", detail)
                else:
                    res.check(True, "DTB 差分（基线模式仅记录）", summarize(diffs))

    return res


def diff_trees(old, new):
    out = {"nodes_added": [], "nodes_removed": [], "props_added": [], "props_removed": [], "props_changed": []}
    for p in new:
        if p not in old:
            out["nodes_added"].append(p)
    for p in old:
        if p not in new:
            out["nodes_removed"].append(p)
    for p in sorted(set(old) & set(new)):
        od, nd = dict(old[p]), dict(new[p])
        for k in nd:
            if k not in od:
                out["props_added"].append((p, k))
            elif od[k] != nd[k]:
                out["props_changed"].append((p, k, od[k], nd[k]))
        for k in od:
            if k not in nd:
                out["props_removed"].append((p, k))
    return out


def summarize(d):
    return ("added nodes=%s removed nodes=%s added props=%s removed props=%s changed props=%s"
            % (d["nodes_added"], d["nodes_removed"],
               [x[1] for x in d["props_added"]], [x[1] for x in d["props_removed"]],
               [(x[0].rsplit('/', 1)[-1], x[1]) for x in d["props_changed"]]))


def check_expected_diff(d, new_paths, old_paths):
    expect_added_nodes = []
    expect_removed_nodes = [PHY7]
    expect_added_props = [(PHY9, "phandle")]
    expect_removed_props = [(PORT1, "phy-mode")]
    expect_changed = [("/", "compatible"), ("/", "model"), (PORT1, "phy-handle"), (KEYS_RESET, "gpios")]

    ok = True
    detail = []
    if sorted(d["nodes_added"]) != sorted(expect_added_nodes):
        ok = False
        detail.append("多余新增节点 %s" % d["nodes_added"])
    if sorted(d["nodes_removed"]) != sorted(expect_removed_nodes):
        ok = False
        detail.append("删除节点不符 %s" % d["nodes_removed"])
    got_added = sorted(d["props_added"])
    if got_added != sorted(expect_added_props):
        ok = False
        detail.append("新增属性不符 %s" % got_added)
    got_removed = sorted(d["props_removed"])
    if got_removed != sorted(expect_removed_props):
        ok = False
        detail.append("删除属性不符 %s" % got_removed)
    got_changed = sorted([(x[0], x[1]) for x in d["props_changed"]])
    if got_changed != sorted(expect_changed):
        ok = False
        detail.append("变更属性不符 %s" % got_changed)
    # 变更内容还要逐项核对
    if ok:
        ch = {(p, k): (o, n) for p, k, o, n in d["props_changed"]}
        if ch[("/", "compatible")][1] != b"fiberhome,hg5585f-cu\0airoha,an7581\0airoha,en7581\0":
            ok = False; detail.append("compatible 目标值不符: %r" % (ch[("/", "compatible")][1],))
        if ch[("/", "model")][1] != b"FiberHome HG5585F CU\0":
            ok = False; detail.append("model 目标值不符: %r" % (ch[("/", "model")][1],))
        gp = dict(new_paths[KEYS_RESET])["gpios"]
        if struct.unpack(">III", gp) != (9, 35, 1):
            ok = False; detail.append("gpios 目标值不符: %r" % (gp,))
        newph = struct.unpack(">I", ch[(PORT1, "phy-handle")][1])[0]
        if struct.unpack(">I", dict(new_paths[PHY9])["phandle"])[0] != newph:
            ok = False; detail.append("phy@9 phandle 与 port@1 phy-handle 不一致")
    if not detail:
        detail.append("7 项全部匹配")
    return ok, "; ".join(detail)


def selftest():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    base = os.path.join(root, "光猫-HG5585F",
                        "QWRT-R26.10.21-airoha-an7581-fiberhome_hg5585f-ct-squashfs-sysupgrade.itb")
    oldpatched = os.path.join(here, "QWRT-R26.10.21-hg5585f-cu-patched.itb")
    v2 = os.path.join(here, "QWRT-R26.10.21-hg5585f-cu-v2.itb")
    control = os.path.join(here, "QWRT-R26.10.21-hg5585f-cu-control.itb")
    cases = [
        (base, "ct-baseline", None, True),
    ]
    if os.path.exists(oldpatched):
        cases.append((oldpatched, "cu", base, False))   # 旧包必须在 cu 断言上失败
    if os.path.exists(v2):
        cases.append((v2, "cu", base, True))
    if os.path.exists(control):
        cases.append((control, "control", base, True))
    allok = True
    for path, expect, baseline, want_pass in cases:
        r = check_image(path, expect, baseline)
        got = r.report(path)
        allok = allok and (got == want_pass)
        if got != want_pass:
            print("  !! 期望 %s 实际 %s" % ("PASS" if want_pass else "FAIL", "PASS" if got else "FAIL"))
    print("\n自测结果: %s" % ("全部符合预期" if allok else "有不符合预期的项"))
    return 0 if allok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="QWRT CU 包校验器")
    ap.add_argument("image", nargs="?")
    ap.add_argument("--expect", choices=("cu", "control", "ct-baseline"), default="cu")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return selftest()
    if not args.image:
        ap.error("需要镜像路径（或用 --self-test）")
    res = check_image(args.image, args.expect, args.baseline)
    return 0 if res.report(args.image) else 1


if __name__ == "__main__":
    sys.exit(main())
