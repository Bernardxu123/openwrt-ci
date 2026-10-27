#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 daed 路由改动是否"无行为变化"。

用法:
    python verify_routing.py <基准文件> <候选文件> [<候选文件2> ...]

做两件事:
  1) 用 daed 自带解析器 (GraphQL parsedRouting) 校验每个候选能否解析;
  2) 把每条规则展开成 atom(条件原子)->出口 的"首个命中即胜出"映射,
     与基准逐项比对, 打印差异。0 处差异 == 覆盖集与优先级完全一致。

注意: 复合条件 (a&&b) 会被展平成两个原子, 故同一函数名出现在多条
复合规则时 (如 sip(...) 出现在不同 dip 组合里), 差异行可能是归一化
假象, 需人工确认。纯原子规则 (domain/dip/pname) 的差异一定是真差异。
"""
import json
import re
import sys
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://192.168.31.1:2023/graphql"


def gql(query, variables=None, tok=None):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = tok
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=30))


def get_token():
    r = gql('{ token(username:"root", password:"Qazswxdecf1") }')
    return r["data"]["token"]


def parse_ok(path, tok):
    raw = open(path, encoding="utf-8").read()
    r = gql('query($r:String!){ parsedRouting(raw:$r){ string } }', {"r": raw}, tok)
    if r.get("errors"):
        return False, r["errors"][0].get("message", str(r["errors"]))
    return True, "ok"


def atoms(path):
    """有序 [(atom, outbound)]，保留首次命中优先级。"""
    out = []
    for ln in open(path, encoding="utf-8"):
        t = ln.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("fallback"):
            out.append(("__FALLBACK__", t.split(":", 1)[1].strip()))
            continue
        lhs, rhs = [s.strip() for s in t.rsplit("->", 1)]
        for c in [x.strip() for x in lhs.split("&&")]:
            m = re.match(r"^(\w+)\((.*)\)$", c)
            if not m:
                out.append(("__RAW__", c))
                continue
            fn, arg = m.group(1), m.group(2)
            for a in arg.split(","):
                out.append(((fn, a.strip()), rhs))
    return out


def norm(path):
    m = {}
    for atom, ob in atoms(path):
        m.setdefault(atom, ob)
    return m


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    base_path, cands = sys.argv[1], sys.argv[2:]
    tok = get_token()

    print("== 解析校验 ==")
    okb, msgb = parse_ok(base_path, tok)
    print(f"  [base] {base_path}: {'OK' if okb else 'FAIL: ' + msgb}")
    for c in cands:
        ok, msg = parse_ok(c, tok)
        print(f"  [cand] {c}: {'OK' if ok else 'FAIL: ' + msg}")

    base = norm(base_path)
    print(f"\n== 覆盖集比对 (base atoms={len(base)}) ==")
    for c in cands:
        cand = norm(c)
        keys = set(base) | set(cand)
        ch = [(k, base.get(k), cand.get(k)) for k in keys if base.get(k) != cand.get(k)]
        ch.sort(key=lambda x: (str(x[0][0]), str(x[0][1])))
        print(f"\n### {base_path} -> {c}: {len(ch)} 处差异 (cand atoms={len(cand)})")
        for (fn, arg), va, vb in ch:
            print(f"    {fn}({arg}) : {va}  ->  {vb}")


if __name__ == "__main__":
    main()
