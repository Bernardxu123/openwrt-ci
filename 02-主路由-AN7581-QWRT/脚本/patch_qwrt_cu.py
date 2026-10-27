#!/usr/bin/env python3
"""
把 QWRT CT 版 sysupgrade.itb 改成 CU 适配版。

改动：
  DTB
    1. compatible  fiberhome,hg5585f-ct      -> fiberhome,hg5585f-cu
    2. model       FiberHome HG5585F CT      -> FiberHome HG5585F CU
    3. keys/reset  gpios GPIO0               -> GPIO35   （与 U-Boot 一致）
    4. ethernet-phy@9  增加 phandle=42       （内建 PHY1，CU 的 lan1）
    5. port@1     phy-handle -> PHY9；phy-mode 2500base-x -> internal
    6. 删除 ethernet-phy@7（GPY211C 外置 2.5G PHY，CU 没有）
  FIT
    7. fdt-1 的 crc32 / sha1 重算（data-size 保持不变，靠补零）
  metadata
    8. supported_devices / board  ct -> cu（等长替换，偏移不变）

用法: python patch_qwrt_cu.py <输入.itb> <输出.itb>
"""
import struct
import sys
import zlib
import hashlib

# ---------- FDT 读写 ----------
FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


class Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name):
        self.name = name
        self.props = []      # [(name, bytes)]
        self.children = []

    def get(self, key):
        for k, v in self.props:
            if k == key:
                return v
        return None

    def set(self, key, val):
        for i, (k, _) in enumerate(self.props):
            if k == key:
                self.props[i] = (key, val)
                return
        self.props.append((key, val))

    def delete(self, key):
        self.props = [(k, v) for k, v in self.props if k != key]

    def child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def walk(self, path=""):
        p = f"{path}/{self.name}" if self.name else path
        yield p or "/", self
        for c in self.children:
            yield from c.walk(p)


def parse_fdt(blob):
    magic, totalsize, off_struct, off_strings = struct.unpack(">4I", blob[:16])
    assert magic == FDT_MAGIC, f"bad fdt magic {magic:#x}"
    strings = blob[off_strings:]
    a4 = lambda x: (x + 3) & ~3

    def gs(off):
        end = strings.index(b"\0", off)
        return strings[off:end].decode()

    pos, end = off_struct, totalsize
    root = None
    stack = []
    while pos < end:
        tok, = struct.unpack(">I", blob[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            e = blob.index(b"\0", pos)
            name = blob[pos:e].decode()
            pos = a4(e + 1)
            node = Node(name)
            if stack:
                stack[-1].children.append(node)
            else:
                root = node
            stack.append(node)
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            ln, no = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            val = blob[pos:pos + ln]
            pos = a4(pos + ln)
            stack[-1].props.append((gs(no), val))
        elif tok == FDT_NOP:
            pass
        elif tok == FDT_END:
            break
        else:
            raise ValueError(f"bad token {tok} at {pos - 4}")
    return root, totalsize


def build_fdt(root, target_size):
    """重新序列化；结构块/字符串块按标准布局；补零到 target_size。"""
    strings = bytearray()
    str_index = {}

    def sid(s):
        if s not in str_index:
            str_index[s] = len(strings)
            strings.extend(s.encode() + b"\0")
        return str_index[s]

    out = bytearray()
    a4 = lambda x: (x + 3) & ~3

    def emit(node):
        out.extend(struct.pack(">I", FDT_BEGIN_NODE))
        nm = node.name.encode() + b"\0"
        out.extend(nm)
        out.extend(b"\0" * (a4(len(out)) - len(out)))
        for k, v in node.props:
            out.extend(struct.pack(">III", FDT_PROP, len(v), sid(k)))
            out.extend(v)
            out.extend(b"\0" * (a4(len(out)) - len(out)))
        for c in node.children:
            emit(c)
        out.extend(struct.pack(">I", FDT_END_NODE))

    emit(root)
    out.extend(struct.pack(">I", FDT_END))

    off_struct = 40 + 16          # header + rsvmap(2 x u64)
    off_strings = off_struct + len(out)
    totalsize = off_strings + len(strings)
    assert totalsize <= target_size, f"DTB 变大了：{totalsize} > {target_size}"

    hdr = struct.pack(
        ">10I", FDT_MAGIC, totalsize, off_struct, off_strings,
        40, 17, 16, 0, len(strings), len(out),
    )
    blob = bytearray(hdr)
    blob.extend(b"\0" * 16)                       # rsvmap: 全零终止项
    blob.extend(out)
    blob.extend(strings)
    blob.extend(b"\0" * (target_size - len(blob)))
    return bytes(blob)


def u32(v):
    return struct.pack(">I", v)


def get_u32(node, key):
    v = node.get(key)
    assert v is not None and len(v) == 4, f"{node.name}: {key} 不是 u32"
    return struct.unpack(">I", v)[0]


# ---------- fwtool trailer ----------
FWIMAGE_MAGIC = 0x46577830          # "FWx0"
TRAILER_LEN = 16
FWIMAGE_SIGNATURE = 0
FWIMAGE_INFO = 1


def find_trailers(data):
    """从尾部向前扫描所有 fwimage_trailer，返回 [(chunk_start, chunk_end, type, size)]。"""
    chunks = []
    end = len(data)
    while end >= TRAILER_LEN:
        off = end - TRAILER_LEN
        magic, crc, typ, _pad, size = struct.unpack(">IIB3xI", data[off:end])
        if magic != FWIMAGE_MAGIC:
            break
        start = end - size
        assert start >= 0, f"trailer @{off} 的 size={size} 越界"
        chunks.append((start, end, typ, size))
        end = start
    return chunks


def fwtool_crc(blob):
    """
    fwtool 的 CRC32 语义（busybox crc32_block）：
      初值 ~0，逐字节查表，结果不做最终取反。
    等价于 zlib.crc32 先 XOR ~0、再 XOR ~0 回来。
    已用原始镜像的两个 trailer 实测验证通过。
    """
    return (zlib.crc32(blob, 0xFFFFFFFF ^ 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def parse_trailer(data, end):
    off = end - TRAILER_LEN
    magic, crc = struct.unpack(">II", data[off:off + 8])
    typ = data[off + 8]
    size = struct.unpack(">I", data[off + 12:off + 16])[0]
    return magic, crc, typ, size, off


def verify_trailers(data):
    """从尾部逐层校验，返回 [(type, start, end, ok, stored, calc)]。"""
    out = []
    end = len(data)
    while end >= TRAILER_LEN:
        magic, stored, typ, size, off = parse_trailer(data, end)
        if magic != FWIMAGE_MAGIC:
            break
        start = end - size
        if start < 0:
            break
        calc = fwtool_crc(bytes(data[0:off]))
        out.append((typ, start, end, calc == stored, stored, calc))
        end = start
    return out


def rebuild_trailers(data):
    """
    重算所有 trailer 的 crc32。
    fwtool 的 crc32 覆盖 [0, trailer_off)，外层 trailer（signature）的 CRC 包含内层
    chunk（info）的内容，所以必须 **从内到外** 依次重算：先 info，再 signature。
    """
    # 先收集所有 trailer（从尾向头）
    layers = []
    end = len(data)
    while end >= TRAILER_LEN:
        magic, stored, typ, size, off = parse_trailer(data, end)
        if magic != FWIMAGE_MAGIC:
            break
        layers.append((off, stored, typ, size))
        end = end - size
    # 反转成从内到外
    layers.reverse()

    notes = []
    for off, stored, typ, size in layers:
        new_crc = fwtool_crc(bytes(data[0:off]))
        data[off + 4:off + 8] = struct.pack(">I", new_crc)
        name = {FWIMAGE_SIGNATURE: "signature", FWIMAGE_INFO: "info"}.get(typ, f"type{typ}")
        changed = "" if new_crc == stored else "  (已更新)"
        notes.append(f"{name:9s} trailer @0x{off:x}  crc {stored:08x} -> {new_crc:08x}{changed}")
    return data, notes


# ---------- FIT 读写 ----------
def parse_fit(d):
    magic, tot, off_struct, off_strings, off_rsv, ver, lc, bc, ss, sz = \
        struct.unpack(">10I", d[:40])
    assert magic == FDT_MAGIC, "不是 FIT"
    strings = d[off_strings:off_strings + ss]

    def gs(o):
        end = strings.index(b"\0", o)
        return strings[o:end].decode()

    a4 = lambda x: (x + 3) & ~3
    pos, end = off_struct, off_struct + sz
    path, info = [], {}

    def key():
        return "/".join(path).lstrip("/")

    while pos < end:
        tok, = struct.unpack(">I", d[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            e = d.index(b"\0", pos)
            path.append(d[pos:e].decode())
            pos = a4(e + 1)
        elif tok == FDT_END_NODE:
            path.pop()
        elif tok == FDT_PROP:
            ln, no = struct.unpack(">II", d[pos:pos + 8])
            pos += 8
            name = gs(no)
            info[(key(), name)] = (pos, ln)
            pos = a4(pos + ln)
        elif tok == FDT_NOP:
            pass
        elif tok == FDT_END:
            break
    return info, (off_struct, sz, off_strings, ss)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    data = bytearray(open(src, "rb").read())
    print(f"输入: {src}  ({len(data)} B)")

    fit, _ = parse_fit(bytes(data))

    # ---- 取出 DTB ----
    fdt_pos = struct.unpack(">I", bytes(data[fit[("images/fdt-1", "data-position")][0]:
                                            fit[("images/fdt-1", "data-position")][0] + 4]))[0]
    fdt_size = struct.unpack(">I", bytes(data[fit[("images/fdt-1", "data-size")][0]:
                                              fit[("images/fdt-1", "data-size")][0] + 4]))[0]
    print(f"fdt-1: pos=0x{fdt_pos:x} size={fdt_size}")

    root, orig_total = parse_fdt(bytes(data[fdt_pos:fdt_pos + fdt_size]))
    print(f"原 DTB totalsize={orig_total}")

    # ---- 1/2. compatible + model ----
    old_compat = root.get("compatible")
    assert old_compat == b"fiberhome,hg5585f-ct\0airoha,an7581\0airoha,en7581\0", old_compat
    root.set("compatible", b"fiberhome,hg5585f-cu\0airoha,an7581\0airoha,en7581\0")
    assert root.get("model") == b"FiberHome HG5585F CT\0"
    root.set("model", b"FiberHome HG5585F CU\0")
    print("  [1] compatible -> fiberhome,hg5585f-cu")
    print("  [2] model      -> FiberHome HG5585F CU")

    # ---- 3. reset 键 GPIO0 -> GPIO35 ----
    keys = root.child("keys")
    reset = keys.child("key-reset") or keys.child("reset")
    assert reset is not None, f"找不到 reset 键节点: {[c.name for c in keys.children]}"
    gp = reset.get("gpios")
    assert gp == u32(9) + u32(0) + u32(1), gp.hex()
    reset.set("gpios", u32(9) + u32(35) + u32(1))
    print(f"  [3] keys/{reset.name} gpios -> GPIO35 (与 U-Boot 一致)")

    # ---- 4/5/6. PHY 重接 ----
    mdio = None
    for c in root.children:
        if c.name.startswith("mdio@"):
            mdio = c
            break
    assert mdio is not None, "找不到 mdio 节点"

    phy7 = mdio.child("ethernet-phy@7")
    phy9 = mdio.child("ethernet-phy@9")
    assert phy7 is not None and phy9 is not None

    # 选一个没被占用的 phandle
    used = set()
    for _, n in root.walk():
        v = n.get("phandle")
        if v and len(v) == 4:
            used.add(struct.unpack(">I", v)[0])
    new_ph = max(used) + 1
    assert new_ph not in used
    phy9.set("phandle", u32(new_ph))
    print(f"  [4] ethernet-phy@9 phandle = {new_ph}")

    eth = None
    for c in root.children:
        if c.name.startswith("ethernet@1fb50000"):
            eth = c
            break
    port1 = eth.child("port@1")
    old_ph = get_u32(port1, "phy-handle")
    assert old_ph == struct.unpack(">I", phy7.get("phandle"))[0], "port@1 没指向 phy@7"
    port1.set("phy-handle", u32(new_ph))
    port1.set("phy-mode", b"internal\0")
    print(f"  [5] port@1 phy-handle {old_ph} -> {new_ph}, phy-mode -> internal")

    mdio.children.remove(phy7)
    print("  [6] 删除 ethernet-phy@7 (GPY211C)")

    # ---- 重新打包 DTB（保持原大小，FIT 偏移不变）----
    new_dtb = build_fdt(root, fdt_size)
    data[fdt_pos:fdt_pos + fdt_size] = new_dtb
    print(f"  新 DTB totalsize={struct.unpack('>I', new_dtb[4:8])[0]} (容器仍 {fdt_size})")

    # ---- 7. 重算 fdt 的 crc32 / sha1 ----
    blob = new_dtb
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    sha = hashlib.sha1(blob).digest()
    for node, val in (("images/fdt-1/hash-1", struct.pack(">I", crc)),
                      ("images/fdt-1/hash-2", sha)):
        off, ln = fit[(node, "value")]
        assert ln == len(val), f"{node} 长度不符 {ln} != {len(val)}"
        data[off:off + ln] = val
    print(f"  [7] fdt crc32={crc:08x} sha1={sha.hex()[:16]}…")

    # ---- 8. metadata: ct -> cu（等长替换）----
    import json
    moff = data.find(b'"metadata_version"')
    assert moff > 0, "找不到 metadata"
    jstart = data.rfind(b"{", 0, moff)
    # 括号匹配找 JSON 结尾
    depth, k, in_str, esc = 0, jstart, False, False
    while k < len(data):
        c = data[k:k + 1]
        if esc:
            esc = False
        elif c == b"\\":
            esc = True
        elif c == b'"':
            in_str = not in_str
        elif not in_str:
            if c == b"{":
                depth += 1
            elif c == b"}":
                depth -= 1
                if depth == 0:
                    break
        k += 1
    jtxt = bytes(data[jstart:k + 1])
    meta = json.loads(jtxt.decode())
    print(f"  metadata 原: {meta['supported_devices']} board={meta['version']['board']}")
    assert meta["supported_devices"] == ["fiberhome,hg5585f-ct", "fiberhome,hg5585f-ct-usb-sfp"]
    assert meta["version"]["board"] == "fiberhome_hg5585f-ct"

    new_jtxt = jtxt.replace(b"fiberhome,hg5585f-ct", b"fiberhome,hg5585f-cu")
    new_jtxt = new_jtxt.replace(b"fiberhome_hg5585f-ct", b"fiberhome_hg5585f-cu")
    assert len(new_jtxt) == len(jtxt), f"长度变了 {len(jtxt)} -> {len(new_jtxt)}"
    data[jstart:jstart + len(new_jtxt)] = new_jtxt
    meta2 = json.loads(bytes(data[jstart:jstart + len(new_jtxt)]).decode())
    print(f"  metadata 新: {meta2['supported_devices']} board={meta2['version']['board']}")
    print(f"  [8] metadata ct->cu 等长替换 OK ({len(new_jtxt)} B @0x{jstart:x})")

    # ---- 9. 重算 fwtool trailer 的 crc32 ----
    # trailer 的 crc32 覆盖 [0, trailer_off)，改了 DTB/metadata 后必然失效
    print("\n=== 9) fwtool trailer 重算 ===")
    before = verify_trailers(bytes(data))
    for typ, s, e, ok, stored, calc in before:
        print(f"  改前 {'signature' if typ==0 else 'info':9s} @0x{s:x}..0x{e:x}  "
              f"crc stored={stored:08x} calc={calc:08x}  {'OK' if ok else 'MISMATCH'}")
    data, notes = rebuild_trailers(data)
    for n in notes:
        print("  ", n)
    after = verify_trailers(bytes(data))
    for typ, s, e, ok, stored, calc in after:
        print(f"  改后 {'signature' if typ==0 else 'info':9s} @0x{s:x}..0x{e:x}  "
              f"crc stored={stored:08x} calc={calc:08x}  {'OK' if ok else 'MISMATCH'}")
    assert all(x[3] for x in after), "trailer CRC 校验仍未通过"
    print("  所有 trailer CRC 校验通过")

    open(dst, "wb").write(bytes(data))
    print(f"\n输出: {dst}  ({len(data)} B)")
    print(f"sha256 = {hashlib.sha256(bytes(data)).hexdigest()}")


if __name__ == "__main__":
    main()
