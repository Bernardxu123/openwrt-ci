#!/usr/bin/env python3
"""应用 aistudio 路由修复：备份当前路由 -> parsedRouting 校验 -> updateRouting + run。
用法:
  python apply_aistudio_routing.py           # 只备份+校验+展示 diff，不生效
  python apply_aistudio_routing.py --apply   # 真正写入并 reload
"""
import json
import sys
import urllib.request

BASE = "http://192.168.31.1:2023/graphql"
USER, PASS = "root", "Qazswxdecf1"
ROUTING_ID_HINT = "default"
NEW_FILE = "routing-20261012-aistudio-stable.txt"
BAK_FILE = "routing-20261012-preaistudio.bak"


def gql(query, token=None, variables=None, timeout=120):
    data = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main():
    apply = "--apply" in sys.argv
    tok = gql('{ token(username: "%s", password: "%s") }' % (USER, PASS))["data"]["token"]

    # 1) 取当前生效路由
    res = gql("{ routings { id name selected routing { string } } }", tok)
    if res.get("errors"):
        sys.exit("routings 查询失败: %s" % res["errors"])
    cur = [r for r in res["data"]["routings"] if r.get("selected")]
    if not cur:
        sys.exit("找不到 selected 路由")
    cur = cur[0]
    cur_text = cur["routing"]["string"]
    print("当前路由: id=%s name=%s 长度=%d" % (cur["id"], cur["name"], len(cur_text)))

    # 2) 安全断言：当前配置确实是修复前状态
    assert 'sip("2408:820c::/16")&&dip("2404:6800::/32")->Media' in cur_text, "当前路由与预期不符，中止"
    assert "aistudio" not in cur_text, "当前路由已包含 aistudio 规则，可能已修复过，中止"

    # 3) 备份
    with open(BAK_FILE, "w", encoding="utf-8") as f:
        f.write(cur_text)
    print("已备份当前路由 -> %s" % BAK_FILE)

    # 4) 读新配置并 diff
    with open(NEW_FILE, "r", encoding="utf-8") as f:
        new_text = f.read()
    import difflib
    diff = list(difflib.unified_diff(
        cur_text.splitlines(), new_text.splitlines(),
        fromfile="current(router)", tofile=NEW_FILE, lineterm="", n=2))
    print("\n".join(diff) if diff else "(无差异！)")

    # 5) parsedRouting 校验（纯语法解析，不生效）
    chk = gql("query($raw:String!){ parsedRouting(raw:$raw){ rules { conditions { and { name not params { key val } } } } } }",
              tok, {"raw": new_text})
    if chk.get("errors"):
        sys.exit("parsedRouting 失败，不应用: %s" % json.dumps(chk["errors"], ensure_ascii=False))
    nrules = len(chk["data"]["parsedRouting"]["rules"])
    cur_chk = gql("query($raw:String!){ parsedRouting(raw:$raw){ rules { conditions { and { name not params { key val } } } } } }",
                  tok, {"raw": cur_text})
    ncur = len(cur_chk["data"]["parsedRouting"]["rules"])
    print("\nparsedRouting 通过：新配置 %d 条规则（原 %d 条，+%d）" % (nrules, ncur, nrules - ncur))
    if nrules - ncur != 1:
        sys.exit("规则数变化不等于 1，预期只新增 1 条，中止")

    if not apply:
        print("\n[ dry-run 模式 ] 未写入。加 --apply 生效。")
        return

    # 6) 写入
    mv = "mutation($id:ID!,$routing:String!){ updateRouting(id:$id, routing:$routing){ id } }"
    res = gql(mv, tok, {"id": cur["id"], "routing": new_text})
    print("updateRouting =>", json.dumps(res, ensure_ascii=False))
    if res.get("errors"):
        sys.exit("updateRouting 失败（旧配置仍在跑）")

    # 7) reload
    run = gql("mutation { run(dry: false) }", tok, {})
    print("run =>", json.dumps(run, ensure_ascii=False))
    if run.get("errors"):
        sys.exit("run 失败（旧配置仍在跑，需人工核对）")

    # 8) 核对
    chk2 = gql("{ routings { name selected routing { string } } general { dae { running modified } } }", tok)
    live = [r for r in chk2["data"]["routings"] if r.get("selected")][0]["routing"]["string"]
    print("核对: dae running=%s modified=%s；生效路由含 aistudio 规则 = %s"
          % (chk2["data"]["general"]["dae"]["running"], chk2["data"]["general"]["dae"]["modified"],
             "aistudio.google.com" in live))


if __name__ == "__main__":
    main()
