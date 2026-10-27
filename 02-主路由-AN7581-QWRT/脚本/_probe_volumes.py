import importlib.util, struct, sys

spec = importlib.util.spec_from_file_location("v", "verify_qwrt_cu_v2.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

path = sys.argv[1] if len(sys.argv) > 1 else "QWRT-R26.10.21-hg5585f-cu-v2.itb"
dtb = v.load_dtb_bytes(path)
h, paths, ph, refs = v.fdt_validate(dtb)


def fmt(val):
    if len(val) == 4:
        n = struct.unpack(">I", val)[0]
        return "%d (0x%x)" % (n, n)
    if len(val) == 8:
        return str(struct.unpack(">2I", val))
    if val and val[-1:] == b"\x00" and all(32 <= c < 127 or c == 0 for c in val):
        return repr(val.split(b"\x00")[0].decode("ascii"))
    return val.hex()


for p in sorted(paths):
    if "/volumes" in p or p.endswith("partition@20000"):
        print("\n### " + p)
        for name, val in paths[p]:
            print("    %-24s = %s" % (name, fmt(val)))
