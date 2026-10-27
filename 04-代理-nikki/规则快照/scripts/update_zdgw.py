#!/usr/bin/env python3
"""把 GitHub 仓库 Bernardxu123/xu 的 zdgw.list 同步进路由器 daed 路由（PC 上运行）。

列表格式：Clash 规则（DOMAIN-SUFFIX,xxx / DOMAIN,xxx，# 注释与空行忽略）。
逻辑：拉列表 → 生成 dae 路由行 → 删掉 routing 里本脚本维护的旧行（识别特征
"-> proxy" 的 domain/domainSuffix 行）→ 插到 ANCHOR（geosite:cn 直连）之前
→ updateRouting + run(dry:false)。

用法：python update_zdgw.py
"""
import json
import re
import sys
import urllib.request

BASE = "http://192.168.31.1:2023/graphql"
USER, PASS = "root", "Qazswxdecf1"
LIST_URL = "https://raw.githubusercontent.com/Bernardxu123/xu/main/zdgw.list"
ROUTING_ID = "Y3Vyc29yMQ"                       # default routing
ANCHOR = "domain(geosite:cn) -> direct"          # 插入锚点：geosite:cn 直连之前
# 本脚本维护的行（ routing 里 "-> proxy" 的 domain 行只会是本脚本写的）
MARK = re.compile(r"^domain(?:Suffix)?\([^)]*\) -> proxy$")


def gql(query, token=None, **variables):
    data = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", token)
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if resp.get("errors"):
        raise SystemExit("GraphQL 错误: " + json.dumps(resp["errors"], ensure_ascii=False))
    return resp


def to_dae_lines(text):
    """Clash 列表 → dae 路由行。

    dae 的 domain() 无独立 domainSuffix 函数：普通条目=后缀匹配（等价
    domain(suffix:)），Clash 的 DOMAIN（精确）映射为 full: 前缀条目，
    两者可同行混写。
    """
    entries = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 2 or not parts[1]:
            continue
        kind = parts[0].upper()
        if kind == "DOMAIN-SUFFIX":
            entries.append(parts[1])
        elif kind == "DOMAIN":
            entries.append("full: " + parts[1])
        else:  # DOMAIN-KEYWORD → keyword: / DOMAIN-REGEX → regex: 按需扩展
            print("忽略未支持类型:", ln)
    if not entries:
        return []
    return ["domain(%s) -> proxy" % ", ".join(entries)]


def main():
    tok = gql('{ token(username:"%s", password:"%s") }' % (USER, PASS))["data"]["token"]

    raw = urllib.request.urlopen(LIST_URL, timeout=30).read().decode()
    new_lines = to_dae_lines(raw)
    if not new_lines:
        sys.exit("zdgw.list 无有效条目，中止")
    print("本次条目:", *new_lines, sep="\n  ")

    rt = next(r for r in gql('{ routings { id routing { string } } }', tok)["data"]["routings"]
              if r["id"] == ROUTING_ID)["routing"]["string"]
    lines = rt.splitlines()
    lines = [l for l in lines if not MARK.match(l.strip())]      # 先清旧行
    if ANCHOR not in lines:
        sys.exit("锚点缺失（%s），请人工检查 routing" % ANCHOR)
    pos = lines.index(ANCHOR)
    lines[pos:pos] = new_lines                                    # 锚点前插入
    new_rt = "\n".join(lines) + "\n"

    print("updateRouting:", json.dumps(gql(
        'mutation($id:ID!,$r:String!){ updateRouting(id:$id, routing:$r){ id } }',
        tok, id=ROUTING_ID, r=new_rt))[:150])
    print("run:", json.dumps(gql('mutation { run(dry: false) }', tok))[:200])


if __name__ == "__main__":
    main()
