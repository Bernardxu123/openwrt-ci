#!/bin/sh
# dsh-dns-guard: mihomo 的 DNS 缓存/双向映射可能把「重拨前」的 AAAA 钉住，
# DDNS 记录更新后客户端仍可能拿到旧 IPv6（外网入口 000/超时）。
# 本脚本比较 mihomo 对 dsh.290490.xyz 的回答与当前 WAN IPv6，不一致则
# ① 先 POST /cache/dns/flush 刷 mihomo DNS 缓存（多数情况刷完即恢复，最小中断）
# ② 仍不一致再 PUT /configs 重载
# ③ 最后才重启 nikki。每 15 分钟跑一次。
DOMAIN="dsh.290490.xyz"
SECRET="917999"
API="http://127.0.0.1:9090"
LOG="/var/log/dsh-dns-guard.log"

WAN=$(ip -6 addr show dev pppoe-wan scope global 2>/dev/null | awk '/inet6 2/{print $2}' | cut -d/ -f1 | head -1)
[ -z "$WAN" ] && exit 0

query() {
  curl -s -m 5 -H "Authorization: Bearer $SECRET" \
    "$API/dns/query?name=$DOMAIN&type=AAAA" 2>/dev/null \
    | tr ',' '\n' | grep -m1 '"data"' | sed 's/.*"data":"\([^"]*\)".*/\1/'
}

ANS=$(query)
[ -z "$ANS" ] && exit 0
[ "$ANS" = "$WAN" ] && exit 0

mkdir -p /var/log
echo "$(date '+%F %T') mismatch: mihomo=$ANS wan=$WAN -> flush dns cache" >> "$LOG"
curl -s -m 5 -X POST -H "Authorization: Bearer $SECRET" "$API/cache/dns/flush" >/dev/null 2>&1
sleep 1
ANS1=$(query)
if [ -n "$ANS1" ] && [ "$ANS1" = "$WAN" ]; then
  echo "$(date '+%F %T') flush fixed: $ANS1" >> "$LOG"
  exit 0
fi
echo "$(date '+%F %T') flush ineffective ($ANS1) -> reload config" >> "$LOG"
curl -s -m 8 -X PUT -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
  -d '{"path":"/etc/nikki/run/config.yaml"}' "$API/configs?force=true" >/dev/null 2>&1
sleep 2
ANS2=$(query)
if [ "$ANS2" = "$WAN" ]; then
  echo "$(date '+%F %T') reload fixed: $ANS2" >> "$LOG"
  exit 0
fi
echo "$(date '+%F %T') reload ineffective ($ANS2) -> restart nikki" >> "$LOG"
/etc/init.d/nikki restart >/dev/null 2>&1
sleep 3
echo "$(date '+%F %T') after restart: $(query)" >> "$LOG"
