#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复判死/回检对托管态的依赖：改为直接查 cf 订阅节点（不再走组内匹配）。"""
import io

lines = open("cfhk-sub-live3.sh", "rb").read().replace(b"\r\n", b"\n").decode("utf-8").split("\n")
if lines[0].startswith("$ cat /usr/bin/cfhk-rotate-sub.sh"):
    lines = lines[1:]
src = "\n".join(lines)


def rep(old, new, tag, cnt=1):
    global src
    assert src.count(old) == cnt, f"{tag}: 匹配数 {src.count(old)} != {cnt}"
    src = src.replace(old, new)
    print("OK:", tag)


# 1) 判死段：查询改为直接取 cf 订阅的节点
rep(
    "# ---------- 3. daed 判死（cf 订阅 matchedNodes） ----------",
    "# ---------- 3. daed 判死（直接查 cf 订阅节点，与组托管状态解耦） ----------",
    "判死段标题",
)
rep(
    """  resp=$(gql "$DTOK" '{"query":"{ groups { subscriptions { subscription { tag } matchedNodes { id address } } } }"}')
  seg=$(printf '%s' "$resp" | sed 's/.*"tag":"cf"},"matchedNodes":\\[//')""",
    """  # 不能走「组内匹配」：区域托管会摘除订阅匹配，那时组里查不到节点、判死失效，
  # 死节点永远换不掉（2026-09-30 港+新托管下实测复现）。直接查订阅本身。
  resp=$(gql "$DTOK" '{"query":"{ subscriptions { tag nodes { edges { id address } } } }"}')
  seg=$(printf '%s' "$resp" | sed 's/.*"tag":"cf","nodes":{"edges":\\[//')""",
    "判死查询",
)

# 2) 回检段：同样改为订阅节点，且只统计本轮选中的 4 个
rep(
    """resp=$(gql "$DTOK" '{"query":"{ groups { subscriptions { subscription { tag } matchedNodes { id address } } } }"}')
seg=$(printf '%s' "$resp" | sed 's/.*"tag":"cf"},"matchedNodes":\\[//')
seg=$(printf '%s' "$seg" | sed 's/]}.*//' 2>/dev/null)
printf '%s' "$seg" | grep -o '"id":"[^"]*","address":"[^"]*"' \\
  | sed 's/"id":"//;s/","address":"/ /;s/"$//' > "$WORK/check.tsv"
: > "$WORK/check.dead"
while read -r nid addr; do
  [ -z "$nid" ] && continue
  alive=$(gql "$DTOK" "{\\"query\\":\\"{ nodeLatencies(ids: [\\\\\\"$nid\\\\\\"]) { alive } }\\"}" \\
    | grep -o '"alive":[a-z]*' | head -1 | cut -d: -f2)
  [ "$alive" != "true" ] && echo "$addr" >> "$WORK/check.dead"
done < "$WORK/check.tsv\"""",
    """resp=$(gql "$DTOK" '{"query":"{ subscriptions { tag nodes { edges { id address } } } }"}')
seg=$(printf '%s' "$resp" | sed 's/.*"tag":"cf","nodes":{"edges":\\[//')
[ "$seg" != "$resp" ] || { log "回检跳过：查不到 cf 订阅节点"; exit 0; }
seg=$(printf '%s' "$seg" | sed 's/\\]}.*//')
printf '%s' "$seg" | grep -o '"id":"[^"]*","address":"[^"]*"' \\
  | sed 's/"id":"//;s/","address":"/ /;s/"$//' > "$WORK/check.tsv"
: > "$WORK/check.dead"
while read -r nid addr; do
  [ -z "$nid" ] && continue
  grep -qxF "$addr" "$WORK/new.sorted" || continue   # 只回检本轮选中的
  alive=$(gql "$DTOK" "{\\"query\\":\\"{ nodeLatencies(ids: [\\\\\\"$nid\\\\\\"]) { alive } }\\"}" \\
    | grep -o '"alive":[a-z]*' | head -1 | cut -d: -f2)
  [ "$alive" != "true" ] && echo "$addr" >> "$WORK/check.dead"
done < "$WORK/check.tsv\"""",
    "回检查询",
)

io.open("cfhk-rotate-sub.sh", "w", encoding="utf-8", newline="\n").write(src)
print("判死/回检托管态修复完成")
