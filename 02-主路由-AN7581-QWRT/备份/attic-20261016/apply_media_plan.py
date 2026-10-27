#!/usr/bin/env python3
"""Apply Media Group and Streamlined Routing to daed."""
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
    
    print("2. 检查现有分组...")
    groups = post({"query": "{ groups { id name policy } }"}, tok)["groups"]
    media_group = next((g for g in groups if g["name"] == "Media"), None)
    
    if not media_group:
        print("   创建 Media 分组 (policy=min_avg10)...")
        res = post({
            "query": """mutation($name: String!, $policy: Policy!) {
                createGroup(name: $name, policy: $policy) {
                    id
                    name
                    policy
                }
            }""",
            "variables": {"name": "Media", "policy": "min_avg10"}
        }, tok)
        media_group = res["createGroup"]
        print(f"   Media 分组已创建: id={media_group['id']}")
    else:
        print(f"   Media 分组已存在: id={media_group['id']}, policy={media_group['policy']}")
        if media_group["policy"] != "min_avg10":
            print("   更新 Media 分组策略为 min_avg10...")
            post({
                "query": "mutation($id: ID!, $policy: Policy!) { groupSetPolicy(id: $id, policy: $policy) { id } }",
                "variables": {"id": media_group["id"], "policy": "min_avg10"}
            }, tok)

    print("3. 关联订阅至 Media 分组 (排除 CF Worker，只选香港与新加坡高速节点)...")
    subs = post({"query": "{ subscriptions { id tag } }"}, tok)["subscriptions"]
    target_subs = [s["id"] for s in subs if s["tag"] in ["乌龟", "极速", "甲骨文-自建"]]
    print(f"   目标订阅: {[s['tag'] for s in subs if s['id'] in target_subs]}")
    
    # 关联订阅
    add_sub_res = post({
        "query": """mutation($id: ID!, $subscriptionIDs: [ID!]!, $nameFilterRegex: String) {
            groupAddSubscriptions(id: $id, subscriptionIDs: $subscriptionIDs, nameFilterRegex: $nameFilterRegex)
        }""",
        "variables": {
            "id": media_group["id"],
            "subscriptionIDs": target_subs,
            "nameFilterRegex": "香港|新加坡|Hong Kong|Singapore"
        }
    }, tok)
    print(f"   订阅关联成功: 匹配新增 {add_sub_res.get('groupAddSubscriptions')} 条规则/节点")

    print("4. 构建并校验精简后的路由规则...")
    routing_text = """pname(NetworkManager, systemd-resolved, dnsmasq) -> must_direct
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

# AI 专属路由 (地区严格合规)
domain(geosite:openai, geosite:anthropic, geosite:google-gemini) -> AI
domain(opencode.ai, oracle.com, oraclecloud.com, oci.oraclecloud.com) -> AI

# 流媒体专属路由 (物理隔离 CF Worker，保证带宽与 IP 粘性)
domain(geosite:youtube, geosite:netflix, geosite:disney, geosite:spotify) -> Media

# 兜底常规代理
fallback: proxy
"""
    # 校验路由语法
    parse_res = post({
        "query": "query($raw: String!) { parsedRouting(raw: $raw) { string } }",
        "variables": {"raw": routing_text}
    }, tok)
    print("   路由语法校验通过:", parse_res.get("parsedRouting") is not None)

    # 查当前选中的 routing id
    routings = post({"query": "{ routings(selected: true) { id name } }"}, tok)["routings"]
    routing_id = routings[0]["id"]
    print(f"   更新 Routing: id={routing_id} ({routings[0]['name']})...")
    post({
        "query": "mutation($id: ID!, $routing: String!) { updateRouting(id: $id, routing: $routing) { id } }",
        "variables": {"id": routing_id, "routing": routing_text}
    }, tok)

    print("5. 清理 DNS upstream 未使用配置...")
    clean_dns = """upstream {
  unicom: 'udp://210.22.70.3:53'
  cf: 'tls://1.1.1.1:853'
}

routing {
  request {
    qname(geosite:private) -> unicom
    qname(geosite:cn) -> unicom
    fallback: cf
  }
  response {
    upstream(cf) -> accept
    fallback: accept
  }
}
"""
    dnss = post({"query": "{ dnss(selected: true) { id name } }"}, tok)["dnss"]
    dns_id = dnss[0]["id"]
    print(f"   更新 DNS: id={dns_id} ({dnss[0]['name']})...")
    post({
        "query": "mutation($id: ID!, $dns: String!) { updateDns(id: $id, dns: $dns) { id } }",
        "variables": {"id": dns_id, "dns": clean_dns}
    }, tok)

    print("6. 恢复 logLevel 为 info...")
    cfg = post({"query": "{ configs(selected: true) { id global { logLevel tcpCheckUrl udpCheckDns checkInterval } } }"}, tok)["configs"][0]
    g = cfg["global"]
    g["logLevel"] = "info"
    post({
        "query": "mutation($id: ID!, $g: globalInput!) { updateConfig(id: $id, global: $g) { id } }",
        "variables": {"id": cfg["id"], "g": g}
    }, tok)

    print("7. 触发 run(dry: false) 下发生效...")
    run_res = post({"query": "mutation { run(dry: false) }"}, tok)
    print("   run 结果:", run_res)

    print("8. 验证分组最终状态...")
    final_groups = post({"query": """{
        groups {
            id
            name
            policy
            nodes {
                id
                name
            }
            subscriptions {
                subscription {
                    tag
                }
                matchedCount
                nameFilterRegex
            }
        }
    }"""}, tok)["groups"]
    for g in final_groups:
        subs_desc = [f"{s['subscription']['tag']}({s['matchedCount']})" for s in g.get("subscriptions", []) if s.get("subscription")]
        print(f"   组: {g['name']} (policy={g['policy']}, nodes={len(g['nodes'])}, subs={subs_desc})")

if __name__ == "__main__":
    main()
