#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_qwrt_cu_v2.py — 把 QWRT (fiberhome,hg5585f-ct) sysupgrade .itb 改造成 CU 可启动版

与旧脚本 patch_qwrt_cu.py 的关键差异：
  * DTB 不再整体重序列化，改为 **libfdt 语义的原位编辑**：
    删除的节点/属性用 FDT_NOP 覆盖，新增属性插入原位，
    剩余空间用 FDT_NOP 补齐 → totalsize / off_dt_struct / off_dt_strings /
    size_dt_struct / size_dt_strings **全部保持原值**（=14698 = FIT data-size）。
  * port@1 的 phy-mode **整条删除**，绝不写 "internal"
    （本 5.4 BSP 内核的 phy_modes[] 没有这个字符串，of_get_phy_mode 会返回
     -EINVAL，phylink 探测失败 → 整块 eth 不 probe → lan1-4 全灭）。
  * 所有不变量集中断言，任一失败立即中止且不写输出文件。

改动集（相对 CT 原始 DTB，共 7 项）：
  1. /compatible            fiberhome,hg5585f-ct -> fiberhome,hg5585f-cu （等长）
  2. /model                 FiberHome HG5585F CT -> FiberHome HG5585F CU （等长）
  3. /ethernet@1fb50000/port@1/phy-handle   0x1d -> <新 phy@9 phandle>
  4. /ethernet@1fb50000/port@1/phy-mode     **删除**
  5. /mdio@1fb5f01c/ethernet-phy@9/phandle  新增
  6. /mdio@1fb5f01c/ethernet-phy@7          整个节点删除
  7. /keys/reset/gpios                      <9 0 1> -> <9 35 1>

打包层：
  * 重算 /images/fdt-1/hash-1(crc32) 与 hash-2(sha1)
  * fwtool metadata JSON 等长替换 hg5585f-ct -> hg5585f-cu
  * 重算两层 footer CRC（先内层 type=1，再外层 type=0）

用法:
  python patch_qwrt_cu_v2.py INPUT.itb OUTPUT.itb [--variant cu|control]

  --variant cu      完整 CU 改造（默认）
  --variant control 只改 metadata（DTB 与 CT 原版逐字节一致），用于诊断
"""

import argparse
import hashlib
import os
import struct
import sys
import zlib

# ---------------------------------------------------------------- 常量

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

FWX0 = b"FWx0"

ETH_NODE = "/ethernet@1fb50000"
PORT1 = ETH_NODE + "/port@1"
PORT2 = ETH_NODE + "/port@2"
MDIO_NODE = "/mdio@1fb5f01c"
PHY7 = MDIO_NODE + "/ethernet-phy@7"
PHY9 = MDIO_NODE + "/ethernet-phy@9"
PHYA = MDIO_NODE + "/ethernet-phy@a"
KEYS_RESET = "/keys/reset"

RESET_GPIO_OLD = 0     # CT DTB 里错写成 GPIO0（实为 uart1_txd）
RESET_GPIO_NEW = 35    # CU/CT 共用的复位键，与 U-Boot 一致


def be32(v):
    return struct.pack(">I", v)


def a4(n):
    return (n + 3) & ~3


# ---------------------------------------------------------------- FDT 模型

class Prop(object):
    __slots__ = ("name", "nameoff", "value")

    def __init__(self, name, nameoff, value):
        self.name = name
        self.nameoff = nameoff
        self.value = value


class Node(object):
    __slots__ = ("name", "props", "children")

    def __init__(self, name):
        self.name = name
        self.props = []
        self.children = []

    def prop(self, name):
        for p in self.props:
            if p.name == name:
                return p
        return None

    def child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None


class Fdt(object):
    """只解析我们关心的字段，同时保留原始 header 值以便原位还原。"""

    def __init__(self, blob):
        self.blob = blob
        if len(blob) < 40:
            raise ValueError("DTB 太短")
        (self.magic, self.totalsize, self.off_struct, self.off_strings,
         self.off_rsvmap, self.version, self.last_comp_version,
         self.boot_cpuid, self.size_strings, self.size_struct) = struct.unpack(
            ">10I", blob[:40])
        if self.magic != FDT_MAGIC:
            raise ValueError("DTB magic 错误: 0x%08x" % self.magic)
        if self.totalsize > len(blob):
            raise ValueError("DTB totalsize %d > 容器 %d" % (self.totalsize, len(blob)))
        self.strings = blob[self.off_strings:self.off_strings + self.size_strings]
        # memreserve
        self.rsv = []
        p = self.off_rsvmap
        while True:
            if p + 16 > self.totalsize:
                raise ValueError("memreserve 未终止")
            a, s = struct.unpack(">QQ", blob[p:p + 16])
            p += 16
            if a == 0 and s == 0:
                break
            self.rsv.append((a, s))
            if len(self.rsv) > 64:
                raise ValueError("memreserve 过多")
        self.root = self._parse_tree()
        self.by_path = {}
        self._index(self.root, "")

    # -- 解析 ----------------------------------------------------
    def _name(self, noff):
        end = self.strings.find(b"\0", noff)
        if noff >= len(self.strings) or end < 0:
            raise ValueError("属性名偏移非法: %d" % noff)
        return self.strings[noff:end].decode("utf-8")

    def _parse_tree(self):
        blob = self.blob
        pos = self.off_struct
        end = self.off_struct + self.size_struct
        root = None
        stack = []
        saw_end = False
        while pos < end:
            (tok,) = struct.unpack(">I", blob[pos:pos + 4])
            pos += 4
            if tok == FDT_BEGIN_NODE:
                e = blob.find(b"\0", pos, end)
                if e < 0:
                    raise ValueError("节点名未终止")
                name = blob[pos:e].decode("utf-8")
                pos = a4(e + 1)
                node = Node(name)
                if stack:
                    stack[-1].children.append(node)
                else:
                    if root is not None:
                        raise ValueError("出现多个根节点")
                    if name != "":
                        raise ValueError("根节点名必须为空, 实际 %r" % name)
                    root = node
                stack.append(node)
            elif tok == FDT_END_NODE:
                if not stack:
                    raise ValueError("END_NODE 下溢")
                stack.pop()
            elif tok == FDT_PROP:
                if not stack:
                    raise ValueError("属性出现在根节点之外")
                ln, noff = struct.unpack(">II", blob[pos:pos + 8])
                pos += 8
                val = blob[pos:pos + ln]
                if pos + ln > end:
                    raise ValueError("属性值越过 struct 块")
                pos = a4(pos + ln)
                stack[-1].props.append(Prop(self._name(noff), noff, val))
            elif tok == FDT_NOP:
                continue
            elif tok == FDT_END:
                saw_end = True
                break
            else:
                raise ValueError("未知 token 0x%x @%d" % (tok, pos - 4))
        if root is None:
            raise ValueError("没有根节点")
        if not saw_end:
            raise ValueError("缺少 FDT_END")
        if stack:
            raise ValueError("节点未闭合, 深度 %d" % len(stack))
        return root

    def _index(self, node, prefix):
        if node.name:
            path = prefix.rstrip("/") + "/" + node.name
        else:
            path = prefix or "/"
        self.by_path[path] = node
        for c in node.children:
            self._index(c, path)

    # -- 序列化 --------------------------------------------------
    def _emit(self, out, node):
        out += be32(FDT_BEGIN_NODE)
        nb = node.name.encode("utf-8") + b"\0"
        out += nb + b"\0" * (a4(len(nb)) - len(nb))
        for p in node.props:
            out += be32(FDT_PROP) + be32(len(p.value)) + be32(p.nameoff)
            out += p.value + b"\0" * (a4(len(p.value)) - len(p.value))
        for c in node.children:
            self._emit(out, c)
        out += be32(FDT_END_NODE)

    def serialize(self):
        """原位序列化：struct 块长度、strings 块、所有 offset 与 header 全部保持原值。

        删掉的节点/属性让 struct 块变短，缺口用 FDT_NOP 补齐。
        ⚠️ 关键：NOP 必须放在**根节点 END_NODE 之前**（树内部）。libfdt 的
        fdt_check_full() 里 `expect_end && tag != FDT_END -> -FDT_ERR_BADLAYOUT`，
        即根节点闭合后只允许紧跟 FDT_END；U-Boot 网页刷机正是用 fdt_check_full()
        校验 fdt-1，NOP 放在根 END_NODE 之后会让它报
        "Firmware device tree is invalid."
        （libfdt 自己的 fdt_del_node 也是把 NOP 写在父节点内部。）
        """
        import io
        buf = io.BytesIO()
        self._emit_into(buf, self.root)
        body = buf.getvalue()
        target = self.size_struct - 4          # 留 4 字节给 FDT_END
        if len(body) < 4:
            raise ValueError("struct 块异常短")
        if len(body) > target:
            raise ValueError("struct 块超出原长: %d > %d" % (len(body), target))
        pad = target - len(body)
        if pad % 4:
            raise ValueError("NOP 填充长度不是 4 的倍数")
        if body[-4:] != be32(FDT_END_NODE):
            raise ValueError("struct 块末尾不是 END_NODE")
        # 把 NOP 插到根 END_NODE 之前，保证"根闭合后紧跟 FDT_END"
        body = body[:-4] + be32(FDT_NOP) * (pad // 4) + be32(FDT_END_NODE) + be32(FDT_END)
        assert len(body) == self.size_struct
        header = struct.pack(
            ">10I", FDT_MAGIC, self.totalsize, self.off_struct, self.off_strings,
            self.off_rsvmap, self.version, self.last_comp_version,
            self.boot_cpuid, self.size_strings, self.size_struct)
        # rsvmap 原样复制
        rsv = self.blob[self.off_rsvmap:self.off_struct]
        blob = header + rsv + body + self.strings
        if len(blob) != self.totalsize:
            raise ValueError("重序列化后 totalsize 变化: %d != %d" % (len(blob), self.totalsize))
        return blob

    def _emit_into(self, out, node):
        out.write(be32(FDT_BEGIN_NODE))
        nb = node.name.encode("utf-8") + b"\0"
        out.write(nb + b"\0" * (a4(len(nb)) - len(nb)))
        for p in node.props:
            out.write(be32(FDT_PROP) + be32(len(p.value)) + be32(p.nameoff))
            out.write(p.value + b"\0" * (a4(len(p.value)) - len(p.value)))
        for c in node.children:
            self._emit_into(out, c)
        out.write(be32(FDT_END_NODE))


# ---------------------------------------------------------------- FIT

class Fit(object):
    def __init__(self, data):
        self.data = bytearray(data)
        if len(data) < 40:
            raise ValueError("不是 FIT")
        self.fdt = Fdt(data)
        self.by_path = self.fdt.by_path

    def prop_value(self, path, name):
        node = self.by_path.get(path)
        if node is None:
            raise KeyError("找不到节点 %s" % path)
        p = node.prop(name)
        if p is None:
            raise KeyError("节点 %s 没有属性 %s" % (path, name))
        return p.value

    def set_prop_value(self, path, name, value):
        node = self.by_path[path]
        p = node.prop(name)
        if p is None:
            raise KeyError("%s 没有 %s" % (path, name))
        if len(p.value) != len(value):
            raise ValueError("%s/%s 变长（%d -> %d），拒绝原地改写"
                             % (path, name, len(p.value), len(value)))
        pos = self._value_offset(path, name)
        self.data[pos:pos + len(value)] = value
        p.value = value

    def _value_offset(self, path, name):
        """在原始 blob 里定位某属性值的绝对偏移。"""
        blob = self.fdt.blob
        pos = self.fdt.off_struct
        end = self.fdt.off_struct + self.fdt.size_struct
        stack = []
        while pos < end:
            (tok,) = struct.unpack(">I", blob[pos:pos + 4])
            pos += 4
            if tok == FDT_BEGIN_NODE:
                e = blob.find(b"\0", pos, end)
                stack.append(blob[pos:e].decode("utf-8"))
                pos = a4(e + 1)
            elif tok == FDT_END_NODE:
                stack.pop()
            elif tok == FDT_PROP:
                ln, noff = struct.unpack(">II", blob[pos:pos + 8])
                pos += 8
                cur = "/" + "/".join([x for x in stack if x])
                if cur == path:
                    nm = self.fdt.strings[noff:self.fdt.strings.find(b"\0", noff)].decode("utf-8")
                    if nm == name:
                        return pos
                pos = a4(pos + ln)
            elif tok == FDT_END:
                break
        raise KeyError("定位失败: %s/%s" % (path, name))


# ---------------------------------------------------------------- 工具

def std_crc32(data):
    """OpenWrt fwtool 用的 crc32：标准 CRC32 去掉最终取反。"""
    return (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def find_footers(data):
    """返回 (info_footer, sig_footer) 偏移；footer = FWx0+crc+type+size 共 16 字节。"""
    n = len(data)
    sig = data.rfind(FWX0)
    if sig < 0 or sig + 16 != n:
        raise ValueError("找不到 signature footer（文件尾不是 FWx0 结尾的 16 字节）")
    info = data.rfind(FWX0, 0, sig)
    if info < 0:
        raise ValueError("找不到 info footer")
    return info, sig


def find_metadata_json(data, info_footer):
    """metadata JSON 位于 info footer 之前、以 '{' 开头、以 '}' + '\\n' 结束。"""
    k = data.find(b'"metadata_version"', 0, info_footer)
    if k < 0:
        raise ValueError("找不到 metadata_version")
    jstart = data.rfind(b"{", 0, k)
    if jstart < 0:
        raise ValueError("找不到 JSON 起始 '{'")
    # JSON 结束的 '}' 是 info footer 之前最后一个 '}'（正文里可能还有内层对象）
    jend = data.rfind(b"}", jstart, info_footer)
    if jend < 0:
        raise ValueError("找不到 JSON 结束 '}'")
    return jstart, jend + 1


def patch_metadata(data, info_footer):
    jstart, jend = find_metadata_json(data, info_footer)
    region = bytes(data[jstart:jend])
    cnt_ct = region.count(b"hg5585f-ct")
    if cnt_ct == 0:
        raise ValueError("metadata 里没有 hg5585f-ct（可能已改过）")
    region_cu = region.replace(b"hg5585f-ct", b"hg5585f-cu")
    if len(region_cu) != len(region):
        raise ValueError("metadata 替换后长度变化，破坏偏移约束")
    data[jstart:jend] = region_cu
    # 复核 JSON 里已无 ct 残留
    after = bytes(data[jstart:jend])
    if b"hg5585f-ct" in after:
        raise ValueError("metadata 仍有 hg5585f-ct 残留")
    return cnt_ct, bytes(region), after


def patch_dtb_via_fit(fit):
    """在 FIT 的 fdt-1 blob 上做原位编辑，返回新的 14698 字节 DTB。"""
    fdt_path = "/images/fdt-1"
    dpos = struct.unpack(">I", fit.prop_value(fdt_path, "data-position"))[0]
    dsize = struct.unpack(">I", fit.prop_value(fdt_path, "data-size"))[0]
    dtb = bytes(fit.data[dpos:dpos + dsize])

    fdt = Fdt(dtb)

    # ---- 0. 确认这是 CT 原版
    compat = fdt.by_path["/"].prop("compatible")
    if compat is None or b"fiberhome,hg5585f-ct\0" not in compat.value:
        raise ValueError("输入 DTB 不是 hg5585f-ct 原版（compatible=%r）" % (
            compat.value if compat else None))
    if PHY7 not in fdt.by_path:
        raise ValueError("输入 DTB 已无 ethernet-phy@7，疑似已打过补丁")
    if fdt.by_path[PORT1].prop("phy-mode") is None:
        raise ValueError("port@1 已无 phy-mode，疑似已打过补丁")

    # ---- 1/2. compatible + model（等长替换）
    if len(compat.value) != len(b"fiberhome,hg5585f-cu\0airoha,an7581\0airoha,en7581\0"):
        raise ValueError("compatible 长度不符预期: %r" % compat.value)
    compat.value = b"fiberhome,hg5585f-cu\0airoha,an7581\0airoha,en7581\0"

    model = fdt.by_path["/"].prop("model")
    if model is None or model.value != b"FiberHome HG5585F CT\0":
        raise ValueError("model 不符预期: %r" % (model.value if model else None))
    model.value = b"FiberHome HG5585F CU\0"

    # ---- 3/5. phy@9 拿一个空闲 phandle，port@1 指向它
    used = set()
    for path, node in fdt.by_path.items():
        for nm in ("phandle", "linux,phandle"):
            p = node.prop(nm)
            if p is not None:
                if len(p.value) != 4:
                    raise ValueError("%s/%s 长度非法" % (path, nm))
                used.add(struct.unpack(">I", p.value)[0])
    new_ph = max(used) + 1
    if new_ph in used:
        raise ValueError("phandle 分配冲突")
    if fdt.by_path[PHY9].prop("phandle") is not None:
        raise ValueError("phy@9 已有 phandle，疑似已打过补丁")

    # 复用 strings 块里已有的 "phandle" 名字偏移（不新增字符串）
    phandle_noff = None
    for node in fdt.by_path.values():
        for p in node.props:
            if p.name == "phandle":
                phandle_noff = p.nameoff
                break
        if phandle_noff is not None:
            break
    if phandle_noff is None:
        raise ValueError("strings 块里找不到 phandle 名字偏移")
    fdt.by_path[PHY9].props.append(Prop("phandle", phandle_noff, be32(new_ph)))

    port1 = fdt.by_path[PORT1]
    ph = port1.prop("phy-handle")
    if ph is None or struct.unpack(">I", ph.value)[0] != 0x1D:
        raise ValueError("port@1/phy-handle 非预期的 0x1d: %r" % (ph.value if ph else None))
    ph.value = be32(new_ph)

    # ---- 4. 删除 port@1/phy-mode（绝不写 "internal"）
    pm = port1.prop("phy-mode")
    if pm is None or pm.value.split(b"\0")[0] != b"2500base-x":
        raise ValueError("port@1/phy-mode 非预期: %r" % (pm.value if pm else None))
    port1.props = [p for p in port1.props if p.name != "phy-mode"]

    # ---- 6. 删除 ethernet-phy@7
    mdio = fdt.by_path[MDIO_NODE]
    mdio.children = [c for c in mdio.children if c.name != "ethernet-phy@7"]
    if PHY7 in fdt._index_rebuild():
        raise ValueError("phy@7 删除失败")

    # ---- 7. reset GPIO 0 -> 35
    kr = fdt.by_path[KEYS_RESET]
    gp = kr.prop("gpios")
    if gp is None or len(gp.value) != 12:
        raise ValueError("keys/reset/gpios 长度非法: %r" % (gp.value if gp else None))
    ph_, pin, flag = struct.unpack(">III", gp.value)
    if pin != RESET_GPIO_OLD:
        raise ValueError("keys/reset GPIO 非预期的 %d" % pin)
    gp.value = struct.pack(">III", ph_, RESET_GPIO_NEW, flag)

    # ---- 序列化 + 自校验
    new_dtb = fdt.serialize()
    if len(new_dtb) != dsize:
        raise ValueError("新 DTB 长度 %d != 原 data-size %d" % (len(new_dtb), dsize))

    check = Fdt(new_dtb)
    if check.totalsize != fdt.totalsize:
        raise ValueError("重解析 totalsize 不一致")
    if b"fiberhome,hg5585f-cu" not in check.by_path["/"].prop("compatible").value:
        raise ValueError("compatible 复核失败")
    if check.by_path[PORT1].prop("phy-mode") is not None:
        raise ValueError("port@1 仍有 phy-mode")
    if check.by_path[MDIO_NODE].child("ethernet-phy@7") is not None:
        raise ValueError("phy@7 仍在")
    if struct.unpack(">I", check.by_path[PORT1].prop("phy-handle").value)[0] != new_ph:
        raise ValueError("port@1 phy-handle 复核失败")
    if struct.unpack(">I", check.by_path[PHY9].prop("phandle").value)[0] != new_ph:
        raise ValueError("phy@9 phandle 复核失败")
    if struct.unpack(">III", check.by_path[KEYS_RESET].prop("gpios").value)[1] != RESET_GPIO_NEW:
        raise ValueError("reset GPIO 复核失败")

    return dpos, dsize, new_dtb, new_ph, used


def _index_rebuild(self):
    self.by_path = {}
    self._index(self.root, "")
    return self.by_path


Fdt._index_rebuild = _index_rebuild


def patch_fit_hashes(fit, dpos, dsize, new_dtb):
    fit.data[dpos:dpos + dsize] = new_dtb
    blob = bytes(fit.data[dpos:dpos + dsize])
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    sha1 = hashlib.sha1(blob).digest()
    for vpath, value in (("/images/fdt-1/hash-1", be32(crc)),
                         ("/images/fdt-1/hash-2", sha1)):
        node = fit.by_path[vpath]
        p = node.prop("value")
        if p is None or len(p.value) != len(value):
            raise ValueError("%s/value 长度不符" % vpath)
        off = fit._value_offset(vpath, "value")
        fit.data[off:off + len(value)] = value
        p.value = value
    return crc, sha1


def main(argv=None):
    ap = argparse.ArgumentParser(description="QWRT CT -> CU 改包工具 v2")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--variant", choices=("cu", "control"), default="cu")
    args = ap.parse_args(argv)

    if os.path.abspath(args.input) == os.path.abspath(args.output):
        raise SystemExit("输入输出不能是同一个文件")

    raw = open(args.input, "rb").read()
    print("[*] 输入 %s (%d 字节)" % (args.input, len(raw)))

    fit = Fit(raw)
    info_footer, sig_footer = find_footers(fit.data)
    print("[*] footer: info@0x%x sig@0x%x" % (info_footer, sig_footer))

    # ---- DTB
    if args.variant == "cu":
        dpos, dsize, new_dtb, new_ph, used = patch_dtb_via_fit(fit)
        print("[*] DTB @0x%x size=%d 已改造, 新 phandle=0x%x (已用=%d)"
              % (dpos, dsize, new_ph, len(used)))
        crc, sha1 = patch_fit_hashes(fit, dpos, dsize, new_dtb)
        print("[*] fdt-1 hash 重算: crc32=0x%08x sha1=%s..." % (crc, sha1.hex()[:16]))
    else:
        print("[*] control 模式：DTB 保持与 CT 原版逐字节一致")

    # ---- metadata
    data = fit.data
    info_footer, sig_footer = find_footers(data)
    cnt, before, after = patch_metadata(data, info_footer)
    print("[*] metadata 已替换 %d 处 hg5585f-ct -> hg5585f-cu（等长）" % cnt)

    # ---- footer CRC：先内层，再外层
    info_footer, sig_footer = find_footers(data)
    c1 = std_crc32(bytes(data[:info_footer]))
    data[info_footer + 4:info_footer + 8] = be32(c1)
    c2 = std_crc32(bytes(data[:sig_footer]))
    data[sig_footer + 4:sig_footer + 8] = be32(c2)
    print("[*] footer CRC: info=0x%08x sig=0x%08x" % (c1, c2))

    # ---- 最终复核
    final = bytes(data)
    fi, fs = find_footers(final)
    if struct.unpack(">I", final[fi + 4:fi + 8])[0] != std_crc32(final[:fi]):
        raise SystemExit("!! info footer CRC 复核失败")
    if struct.unpack(">I", final[fs + 4:fs + 8])[0] != std_crc32(final[:fs]):
        raise SystemExit("!! sig footer CRC 复核失败")
    if len(final) != len(raw):
        raise SystemExit("!! 输出长度变化")

    with open(args.output, "wb") as f:
        f.write(final)
    print("[+] 写出 %s (%d 字节)" % (args.output, len(final)))
    print("[+] sha256 %s" % hashlib.sha256(final).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
