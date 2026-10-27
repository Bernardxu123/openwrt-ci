#!/usr/bin/env python3
"""把 GitHub 仓库 Bernardxu123/xu 的 cfhk.list 同步成 daed 订阅（PC 上运行）。

列表格式：`IP:端口#备注`（# 后为备注，空行与 # 注释行忽略）——和 bestcf 的
tiancheng/hk.txt 同格式，方便直接粘贴筛选。

链路：cfhk.list（源，可读）→ 生成 vless 分享链接 → base64 → 推送为仓库里的
cfhk.sub → raw.githubusercontent.com 直链被 daed 当订阅拉取。
（dae 的订阅解析只认 SIP008 / base64，纯文本分享链列表解不出来，见
dae/common/subscription/subscription.go 的 ResolveSubscriptionAsBase64。）

daed 侧已配置（2026-09-21）：订阅 tag=cfhk（id Y3Vyc29yMTA），cron 已关
（清单是静态的，自动更新只会触发无谓的"删旧建新"重建）；已用
groupAddSubscriptions 挂到 proxy 组——订阅节点走"匹配"进组，订阅更新时
自动对账，不会像显式成员那样被清掉。

用法：
  python update_cfhk.py            # 推送 cfhk.sub + 触发 daed 更新订阅
  python update_cfhk.py --dry      # 只生成本地文件，不推送、不动 daed
  python update_cfhk.py --import   # 首次：在 daed 导入订阅并挂到 proxy 组
依赖：gh CLI（已登录 Bernardxu123，用于推仓库）、requests 之外只用标准库。
"""
import argparse
import base64
import json
import subprocess
import sys
import urllib.parse
import urllib.request

REPO = "Bernardxu123/xu"
LIST_PATH = "cfhk.list"
SUB_PATH = "cfhk.sub"
RAW = "https://raw.githubusercontent.com/%s/main/%s" % (REPO, SUB_PATH)
TAG = "cfhk"
PROXY_GROUP_ID = "Y3Vyc29yMQ"          # proxy 组

# edgetunnel（byJoey/cfnew 经典轻量版，Cloudflare Worker 内 VLESS-over-WS）
UUID = "334d1657-4335-4359-8ece-a22034d76152"
SNI = "gogo.290490.xyz"
WS_PATH = "/?ed=2048"

BASE = "http://192.168.31.1:2023/graphql"
USER, PASS = "root", "Qazswxdecf1"


def gql(query, token=None, timeout=180, **variables):
    data = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    if resp.get("errors"):
        raise SystemExit("GraphQL 错误: " + json.dumps(resp["errors"], ensure_ascii=False))
    return resp.get("data")


def daed_token():
    return gql('{ token(username: "%s", password: "%s") }' % (USER, PASS))["token"]


def fetch_list():
    url = "https://raw.githubusercontent.com/%s/main/%s" % (REPO, LIST_PATH)
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_entries(text):
    """cfhk.list → [(ip, port, remark)]；忽略空行与 # 注释行。"""
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        hostport, _, remark = ln.partition("#")
        ip, _, port = hostport.strip().partition(":")
        if not ip or not port:
            raise SystemExit("坏行（缺端口）: " + ln)
        out.append((ip, int(port), remark.strip()))
    return out


def make_link(ip, port, remark):
    q = urllib.parse.urlencode({
        "encryption": "none", "security": "tls", "sni": SNI,
        "fp": "chrome", "type": "ws", "host": SNI, "path": WS_PATH,
    })
    name = "香港反代 | %s:%d" % (ip, port)
    return "vless://%s@%s:%d?%s#%s" % (UUID, ip, port, q, urllib.parse.quote(name))


def push_sub(b64):
    """把 base64 订阅内容推送为仓库里的 cfhk.sub（gh api 走 Contents API）。"""
    body = json.dumps({
        "message": "cfhk: regenerate cfhk.sub from cfhk.list",
        "content": base64.b64encode(b64.encode()).decode(),
    })
    r = subprocess.run(
        ["gh", "api", "--method", "PUT", "repos/%s/contents/%s" % (REPO, SUB_PATH), "--input", "-"],
        input=body, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("推送失败: " + (r.stderr or r.stdout)[:300])


def sub_id(tok):
    for s in gql("{ subscriptions { id tag } }", tok)["subscriptions"]:
        if s["tag"] == TAG:
            return s["id"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只生成本地文件")
    ap.add_argument("--import", dest="do_import", action="store_true", help="首次导入并挂组")
    args = ap.parse_args()

    entries = parse_entries(fetch_list())
    if not entries:
        raise SystemExit("cfhk.list 里没有有效条目")
    links = [make_link(ip, port, remark) for ip, port, remark in entries]
    b64 = base64.b64encode(("\n".join(links) + "\n").encode()).decode()
    for l in links:
        print(l)
    if args.dry:
        print("（--dry：未推送、未动 daed）")
        return

    push_sub(b64)
    print("已推送 %s（%d 个节点）" % (SUB_PATH, len(links)))

    tok = daed_token()
    sid = sub_id(tok)
    if args.do_import or sid is None:
        r = gql('mutation { importSubscription(rollbackError: false, arg: {link: "%s", tag: "%s"})'
                ' { sub { id tag } nodeImportResult { error } } }' % (RAW, TAG), tok)
        sid = r["importSubscription"]["sub"]["id"]
        print("已导入订阅:", sid)
        gql('mutation { groupAddSubscriptions(id: "%s", subscriptionIDs: ["%s"]) }'
            % (PROXY_GROUP_ID, sid), tok)
        gql('mutation { updateSubscriptionCron(id: "%s", cronExp: "10 */6 * * *", cronEnable: false) { id } }' % sid, tok)
        print("已挂到 proxy 组并关闭 cron")
    else:
        gql('mutation { updateSubscription(id: "%s") { id tag } }' % sid, tok)
        print("已触发 daed 更新订阅:", sid)
    gql("mutation { run(dry: false) }", tok)
    print("已 run 生效")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
