#!/bin/sh
# Cloudflare AAAA 更新脚本（ddns-scripts custom update_script，被 source 调用）
#
# 由 /usr/lib/ddns/dynamic_dns_updater.sh 的 send_update() 以 `. $update_script` 方式加载，
# 因此可直接使用父脚本变量：$__IP（检测到的 IPv6）、$domain（uci 里的域名）。
# 返回 0 = 成功；非 0 = 失败（ddns-scripts 会按 retry 设置重试）。
#
# 设计要点：
#  1) AAAA 指向**路由器 WAN（pppoe-wan）的 IPv6**，由本机 nginx 反代到 PC 的 DSH Pocket。
#  2) 本地缓存最后推送过的 IP（/etc/dsh-ddns-last）：ddns-scripts 的 lookup_host 校验会被
#     nikki/mihomo 的 fake-IP 干扰（必然"不一致"），这里用缓存短路，避免每 5 分钟空打 CF API。
#  3) zone id / record id 缓存到 /etc 下，减少 API 往返；record id 失效会自动重建。
#  4) 记录为 DNS-only（proxied=false）+ TTL 60，手机直连家宽 IPv6（不走 Cloudflare 代理）。

API="https://api.cloudflare.com/client/v4"
ZONE_NAME="${CF_ZONE:-290490.xyz}"
TOKEN_FILE="/etc/cf-dns.token"
LAST_FILE="/etc/dsh-ddns-last"
ZONE_ID_FILE="/etc/dsh-cf-zone.id"
REC_ID_FILE="/etc/dsh-cf-record.id"
REC_NAME="${domain:-dsh.290490.xyz}"

if [ -z "$__IP" ]; then
    write_log 3 "cloudflare: 未拿到 IPv6 地址，跳过"
    return 1
fi
if [ ! -r "$TOKEN_FILE" ]; then
    write_log 3 "cloudflare: 缺少 token 文件 $TOKEN_FILE"
    return 1
fi
TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null)
if [ -z "$TOKEN" ]; then
    write_log 3 "cloudflare: token 为空"
    return 1
fi

# 地址没变则直接成功返回（避免每轮空打 API）
if [ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE" 2>/dev/null)" = "$__IP" ]; then
    write_log 7 "cloudflare: IP 未变化 ($__IP)，跳过 API 调用"
    return 0
fi

cf_api() {
    curl -s -m 20 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"
}

# ---- zone id ----
ZONE_ID=""
[ -s "$ZONE_ID_FILE" ] && ZONE_ID=$(cat "$ZONE_ID_FILE")
if [ -z "$ZONE_ID" ]; then
    RESP=$(cf_api "$API/zones?name=$ZONE_NAME")
    ZONE_ID=$(echo "$RESP" | jsonfilter -e '@.result[0].id' 2>/dev/null)
    if [ -z "$ZONE_ID" ]; then
        write_log 3 "cloudflare: 查询 zone '$ZONE_NAME' 失败: $RESP"
        return 1
    fi
    echo "$ZONE_ID" > "$ZONE_ID_FILE"
fi

# ---- record id（缓存失效则重查）----
REC_ID=""
[ -s "$REC_ID_FILE" ] && REC_ID=$(cat "$REC_ID_FILE")
if [ -n "$REC_ID" ]; then
    RESP=$(cf_api "$API/zones/$ZONE_ID/dns_records/$REC_ID")
    echo "$RESP" | grep -q '"success":true' || REC_ID=""
fi
if [ -z "$REC_ID" ]; then
    RESP=$(cf_api "$API/zones/$ZONE_ID/dns_records?type=AAAA&name=$REC_NAME")
    REC_ID=$(echo "$RESP" | jsonfilter -e '@.result[0].id' 2>/dev/null)
    [ -n "$REC_ID" ] && echo "$REC_ID" > "$REC_ID_FILE"
fi

BODY="{\"type\":\"AAAA\",\"name\":\"$REC_NAME\",\"content\":\"$__IP\",\"ttl\":60,\"proxied\":false,\"comment\":\"dsh-pocket-router-ddns\"}"
if [ -n "$REC_ID" ]; then
    RESP=$(cf_api -X PUT "$API/zones/$ZONE_ID/dns_records/$REC_ID" --data "$BODY")
else
    RESP=$(cf_api -X POST "$API/zones/$ZONE_ID/dns_records" --data "$BODY")
    NEW_ID=$(echo "$RESP" | jsonfilter -e '@.result.id' 2>/dev/null)
    [ -n "$NEW_ID" ] && echo "$NEW_ID" > "$REC_ID_FILE"
fi

if echo "$RESP" | grep -q '"success":true'; then
    echo "$__IP" > "$LAST_FILE"
    write_log 5 "cloudflare: $REC_NAME AAAA -> $__IP 更新成功"
    return 0
fi
write_log 3 "cloudflare: 更新失败: $RESP"
return 1
