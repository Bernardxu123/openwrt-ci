#!/usr/bin/env python3
"""Targeted fix for Huawei YouTube App (resolves No-SNI IP mismatch and slow dialer)."""
import json
import sys
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://192.168.31.1:2023/graphql"

def post(body, tok=None):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = tok
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=headers)
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if r.get("errors"):
        raise RuntimeError(f"GraphQL Error: {r['errors']}")
    return r.get("data")

def main():
    print("1. 获取 Token...")
    tok = post({"query": '{ token(username:"root", password:"Qazswxdecf1") }'})["token"]

    print("2. 优化 Global Config (将 sniffingTimeout 从 100ms 调整为 300ms)...")
    cfg = post({"query": "{ configs(selected: true) { id global { logLevel tcpCheckUrl udpCheckDns checkInterval sniffingTimeout dialMode lanInterface wanInterface } } }"}, tok)["configs"][0]
    g = cfg["global"]
    g["sniffingTimeout"] = "300ms"
    g["logLevel"] = "info"
    post({
        "query": "mutation($id: ID!, $g: globalInput!) { updateConfig(id: $id, global: $g) { id } }",
        "variables": {"id": cfg["id"], "g": g}
    }, tok)
    print("   Global Config 更新完成: sniffingTimeout=300ms, logLevel=info")

    print("3. 优化 Media 分组...")
    groups = post({"query": "{ groups { id name policy nodes { id name } } }"}, tok)["groups"]
    media_g = next((x for x in groups if x["name"] == "Media"), None)
    if not media_g:
        raise RuntimeError("Media group not found!")

    # 锁定 policy 为 min_avg10
    print(f"   设置 Media 策略为 min_avg10 (当前={media_g['policy']})...")
    post({
        "query": "mutation($id: ID!, $policy: Policy!) { groupSetPolicy(id: $id, policy: $policy) }",
        "variables": {"id": media_g["id"], "policy": "min_avg10"}
    }, tok)

    # 优化 Media 组内的订阅过滤器，只选用极速、乌龟 VLESS、甲骨文，排除超时的乌龟 Hy2 节点
    subs = post({"query": "{ subscriptions { id tag } }"}, tok)["subscriptions"]
    # 先删除旧的订阅关联
    post({
        "query": "mutation($id: ID!, $subIds: [ID!]!) { groupDelSubscriptions(id: $id, subscriptionIDs: $subIds) }",
        "variables": {"id": media_g["id"], "subIds": [s["id"] for s in subs]}
    }, tok)

    # 重新绑定：极速 (优质港新 VLESS, 120-170ms) + 甲骨文自建
    jisu_sub = next((s["id"] for s in subs if s["tag"] == "极速"), None)
    oracle_sub = next((s["id"] for s in subs if s["tag"] == "甲骨文-自建"), None)
    wugui_sub = next((s["id"] for s in subs if s["tag"] == "乌龟"), None)

    sub_targets = []
    if jisu_sub:
        sub_targets.append(jisu_sub)
    if oracle_sub:
        sub_targets.append(oracle_sub)
    if wugui_sub:
        sub_targets.append(wugui_sub)

    # 排除 Hy2 超时节点，只选 VLESS 和可用节点：港新
    post({
        "query": """mutation($id: ID!, $subscriptionIDs: [ID!]!, $nameFilterRegex: String) {
            groupAddSubscriptions(id: $id, subscriptionIDs: $subscriptionIDs, nameFilterRegex: $nameFilterRegex)
        }""",
        "variables": {
            "id": media_g["id"],
            "subscriptionIDs": sub_targets,
            "nameFilterRegex": "(🇭🇰|🇸🇬|Hong Kong|Singapore)"
        }
    }, tok)
    print("   Media 组订阅重新绑定完成 (锁定高速港新节点池)")

    print("4. 更新精准分流规则 (彻底根治华为无 SNI 导致的 API 误入 AI 组问题)...")
    new_routing = """pname(NetworkManager, systemd-resolved, dnsmasq) -> must_direct
dip(geoip:private) -> direct
domain(geosite:private) -> direct

# 传输层协议治理：全局阻断 QUIC 强制 TCP，NTP 直连校时
l4proto(udp) && dport(443) -> block
l4proto(udp) && dport(123) -> direct

# 自建服务直连
domain(xx.290490.xyz) -> direct

# 境外特例直连修正与国内放行
domain(stripo.email, justuno.com, mailchimp.com, freepik.com, joeyblog.net, googleapis.cn, services.googleapis.cn, xn--ngstr-lra8j.com, dl.google.com, nvidia.com, workbuddy.ai) -> proxy
domain(geosite:cn) -> direct
dip(geoip:cn) -> direct

# 1. 精确 AI 域名 (有真实 SNI 的 Gemini 与 AI 业务，优先且精确进入 AI 组)
domain(generativelanguage.googleapis.com, ai.google.dev, gemini.google.com, bard.google.com) -> AI
domain(geosite:openai, geosite:anthropic) -> AI
domain(opencode.ai, oracle.com, oraclecloud.com, oci.oraclecloud.com) -> AI

# 2. 流媒体专属路由 (YouTube 所有域名进入 Media 组)
domain(geosite:youtube, geosite:netflix, geosite:disney, geosite:spotify) -> Media

# 3. 华为设备关键修复：无 SNI 的 Google 核心 IPv6 字面量统合归入 Media，绝不让 API 错入 AI 组导致签名 403
dip("2001:4860::/32", "2404:6800::/32") -> Media

# 兜底常规代理
fallback: proxy
"""

    routings = post({"query": "{ routings(selected: true) { id name } }"}, tok)["routings"]
    routing_id = routings[0]["id"]
    post({
        "query": "mutation($id: ID!, $routing: String!) { updateRouting(id: $id, routing: $routing) { id } }",
        "variables": {"id": routing_id, "routing": new_routing}
    }, tok)
    print("   路由规则更新完成")

    print("5. 触发 run(dry: false) 下发部署...")
    run_res = post({"query": "mutation { run(dry: false) }"}, tok)
    print("   run 结果:", run_res)

    print("6. 最终状态核验...")
    cur = post({"query": """{
        groups {
            name
            policy
            nodes {
                name
            }
            subscriptions {
                subscription { tag }
                matchedCount
            }
        }
    }"""}, tok)["groups"]
    for g in cur:
        subs_desc = [f"{s['subscription']['tag']}({s['matchedCount']})" for s in g.get("subscriptions", []) if s.get("subscription")]
        print(f"   组 {g['name']}: policy={g['policy']}, nodes={len(g['nodes'])}, subs={subs_desc}")

if __name__ == "__main__":
    main()
