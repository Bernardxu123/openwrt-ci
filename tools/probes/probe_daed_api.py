#!/usr/bin/env python3
"""只读探测：daed GraphQL 是否暴露日志/连接类接口（决定出口记录页能否脱离 CGI 文件尾随）。

背景：官方面板 bundle 里带 graphql-ws 库，但未找到被使用的订阅操作（那些 `subscription`
命中全是"节点订阅"业务词）。所以直接问 schema：
  1. 有没有 Subscription 类型（服务端推送能力）；
  2. query 字段里有没有日志/连接类接口；
  3. 若有，出口记录页可以不再 tail 文件、不再 5s 轮询。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from daed import gql, token  # noqa: E402

Q = """query { __schema {
  queryType { name fields { name } }
  subscriptionType { name fields { name } }
} }"""

KEYS = ("log", "connect", "stream", "event", "trace", "record", "general", "node", "group")

if __name__ == "__main__":
    res = gql(Q, token())
    if "errors" in res:
        print("introspection 被拒：" + json.dumps(res["errors"], ensure_ascii=False)[:400])
        raise SystemExit(0)
    schema = res["data"]["__schema"]

    qf = [f["name"] for f in ((schema.get("queryType") or {}).get("fields") or [])]
    print(f"query 字段共 {len(qf)} 个：")
    print("  " + ", ".join(qf))

    sub = schema.get("subscriptionType")
    if sub:
        names = [f["name"] for f in (sub.get("fields") or [])]
        print(f"\nSubscription 类型 = {sub['name']}，字段 {len(names)} 个：{names}")
    else:
        print("\n无 Subscription 类型 → 服务端不支持 GraphQL 订阅推送")

    hit = [n for n in qf if any(k in n.lower() for k in KEYS)]
    print("\n日志/流相关候选：" + (", ".join(hit) if hit else "（无）"))
