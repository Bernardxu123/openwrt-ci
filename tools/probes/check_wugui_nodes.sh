#!/bin/sh
printf '{"query":"query($u:String!,$p:String!){ token(username:$u,password:$p) }","variables":{"u":"root","p":"Qazswxdecf1"}}' > /tmp/dd-tok.json
TOKEN=$(curl -s -X POST http://192.168.31.1:2023/graphql -H 'Content-Type: application/json' --data-binary @/tmp/dd-tok.json | jsonfilter -e '@.data.token')
# 订阅详情 + 前几个节点名
printf '%s' '{"query":"{ subscriptions { id tag status info cronExp cronEnable updatedAt nodes { totalCount edges { id name protocol } } } }"}' > /tmp/dd-full.json
curl -s -X POST http://192.168.31.1:2023/graphql -H 'Content-Type: application/json' -H "Authorization: $TOKEN" --data-binary @/tmp/dd-full.json > /tmp/dd-full.resp
jsonfilter -i /tmp/dd-full.resp -e '@.data.subscriptions[@.tag="乌龟"].status'
echo
jsonfilter -i /tmp/dd-full.resp -e '@.data.subscriptions[@.tag="乌龟"].info'
echo
jsonfilter -i /tmp/dd-full.resp -e '@.data.subscriptions[@.tag="乌龟"].updatedAt'
echo
jsonfilter -i /tmp/dd-full.resp -e '@.data.subscriptions[@.tag="乌龟"].nodes.totalCount'
echo
echo "--- node names (first 15) ---"
jsonfilter -i /tmp/dd-full.resp -e '@.data.subscriptions[@.tag="乌龟"].nodes.edges[@.name]' 2>/dev/null | head -15
# 上面表达式不一定支持，兜底：文本抽 name
echo "--- fallback names ---"
grep -o '"name":"[^"]*"' /tmp/dd-full.resp | head -20
