#!/usr/bin/env python3
"""Diff two opkg status databases (name -> version)."""
import sys


def load(path):
    pkgs = {}
    name = ver = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("Package: "):
            name = line[9:].strip()
        elif line.startswith("Version: "):
            ver = line[9:].strip()
            if name:
                pkgs[name] = ver
        elif not line.strip():
            name = ver = None
    return pkgs


old = load(sys.argv[1])
new = load(sys.argv[2])
added = sorted(set(new) - set(old))
removed = sorted(set(old) - set(new))
changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
print(f"old={len(old)} new={len(new)}  +{len(added)} -{len(removed)} ~{len(changed)}")
if added:
    print("\n[新增]")
    for a in added:
        print("  +", a, new[a])
if removed:
    print("\n[移除]")
    for a in removed:
        print("  -", a, old[a])
if changed:
    print("\n[版本变化]")
    for c in changed:
        print(f"  ~ {c}: {old[c]} -> {new[c]}")
