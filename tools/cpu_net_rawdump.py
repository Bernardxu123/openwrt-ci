import sys

raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
rows = [l for l in raw.splitlines() if l.startswith("N ")]
t0 = float(rows[0].split()[1])
devs = ["pon0", "pon0.995", "pppoe-wan", "br-lan", "phy0-ap0", "phy1-ap0", "eth0"]
print("RAW ABSOLUTE BYTES")
for l in rows:
    p = l.split()
    ts = float(p[1]) - t0
    if not (8 <= ts <= 46):
        continue
    d = {}
    for tok in p[2:]:
        f = tok.split(":")
        if len(f) == 5:
            d[f[0]] = (int(f[1]), int(f[2]))
    parts = []
    for dv in devs:
        if dv in d:
            parts.append(f"{dv}=({d[dv][0]},{d[dv][1]})")
    print(f"t={ts:6.1f}  " + " ".join(parts))
