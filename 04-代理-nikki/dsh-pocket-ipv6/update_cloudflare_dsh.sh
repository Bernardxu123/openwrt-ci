#!/bin/sh
# Cloudflare AAAA 更新脚本（ddns-scripts custom update_script，被 source 调用）
#
# 由 /usr/lib/ddns/dynamic_dns_updater.sh 的 send_update() 以 `. $update_script` 方式加载，
# 因此可直接使用父脚本变量：$__IP（检测到的 IPv6）、$domain（uci 里的域名）。
# 返回 0 = 成功；非 0 = 失败（ddns-scripts 会按 retry 设置重试）。
#
# 设计要点：
#  1) AAAA 指向**路由器 WAN（pppoe-wan）的 IPv6**，由本机 nginx 反代到 PC 的 DSH Pocket。
#     PC 的 IPv6 是 RA/SLAAC，前缀随重拨变化，不参与 DDNS。
#  2) 本地缓存最后推送过的 IP（/etc/dsh-ddns-last）：ddns-scripts 的 lookup_host 校验会被
#     nikki/mihomo 的 fake-IP 干扰，这里用缓存短路，避免每轮空打 CF API。
#  3) 12 小时对账（/etc/dsh-ddns-last-verify）：记录被删/被别的程序改掉、而 IP 没变时，
#     原短路逻辑永远不会修复；到期时 GET 一次线上记录，不一致就重写（每 12h 仅 1 次 API）。
#  4) zone id / record id 缓存到 /etc 下，减少 API 往返；record id 失效会自动重建。
#  5) 记录为 DNS-only（proxied=false）+ TTL 60，手机直连家宽 IPv6（不走 Cloudflare 代理）。

API="https://api.cloudflare.com/client/v4"
ZONE_NAME="${CF_ZONE:-290490.xyz}"
TOKEN_FILE="/etc/cf-dns.token"
LAST_FILE="/etc/dsh-ddns-last"
VERIFY_FILE="/etc/dsh-ddns-last-verify"
ZONE_ID_FILE="/etc/dsh-cf-zone.id"
REC_ID_FILE="/etc/dsh-cf-record.id"
REC_NAME="${domain:-dsh.290490.xyz}"
RECONCILE_SECONDS=43200   # 12 小时

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

cf_api() {
    curl -s -m 20 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"
}

# 地址没变、且未到对账窗口，则直接成功返回（避免每轮空打 API）
SAME_IP=0
if [ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE" 2>/dev/null)" = "$__IP" ]; then
    SAME_IP=1
fi
if [ "$SAME_IP" = "1" ]; then
    LAST_VERIFY=$(cat "$VERIFY_FILE" 2>/dev/null)
    case "$LAST_VERIFY" in ''|*[!0-9]*) LAST_VERIFY=0;; esac
    if [ $(( $(date +%s) - LAST_VERIFY )) -lt "$RECONCILE_SECONDS" ]; then
        write_log 7 "cloudflare: IP 未变化 ($__IP)，跳过 API 调用"
        return 0
    fi
    write_log 7 "cloudflare: 12h 对账窗口到期，校验线上记录"
fi

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

# ---- record id + 现有内容（缓存失效则重查）----
REC_ID=""
REC_CONTENT=""
REC_EXISTS=0
[ -s "$REC_ID_FILE" ] && REC_ID=$(cat "$REC_ID_FILE")
if [ -n "$REC_ID" ]; then
    RESP=$(cf_api "$API/zones/$ZONE_ID/dns_records/$REC_ID")
    if echo "$RESP" | grep -q '"success":true'; then
        REC_EXISTS=1
        REC_CONTENT=$(echo "$RESP" | jsonfilter -e '@.result.content' 2>/dev/null)
    else
        write_log 4 "cloudflare: 缓存的 record id 失效，重新查询"
        REC_ID=""
    fi
fi
if [ -z "$REC_ID" ]; then
    RESP=$(cf_api "$API/zones/$ZONE_ID/dns_records?type=AAAA&name=$REC_NAME")
    REC_ID=$(echo "$RESP" | jsonfilter -e '@.result[0].id' 2>/dev/null)
    if [ -n "$REC_ID" ]; then
        echo "$REC_ID" > "$REC_ID_FILE"
        REC_EXISTS=1
        REC_CONTENT=$(echo "$RESP" | jsonfilter -e '@.result[0].content' 2>/dev/null)
    fi
fi

# 对账：IP 未变 && 记录存在 && 内容一致 → 只刷新对账时间戳
if [ "$SAME_IP" = "1" ] && [ "$REC_EXISTS" = "1" ] && [ "$REC_CONTENT" = "$__IP" ]; then
    date +%s > "$VERIFY_FILE"
    write_log 5 "cloudflare: 对账一致 ($REC_NAME AAAA=$__IP)"
    return 0
fi

BODY="{\"type\":\"AAAA\",\"name\":\"$REC_NAME\",\"content\":\"$__IP\",\"ttl\":60,\"proxied\":false,\"comment\":\"dsh-pocket-router-ddns\"}"
if [ "$REC_EXISTS" = "1" ]; then
    RESP=$(cf_api -X PUT "$API/zones/$ZONE_ID/dns_records/$REC_ID" --data "$BODY")
else
    RESP=$(cf_api -X POST "$API/zones/$ZONE_ID/dns_records" --data "$BODY")
    NEW_ID=$(echo "$RESP" | jsonfilter -e '@.result.id' 2>/dev/null)
    [ -n "$NEW_ID" ] && echo "$NEW_ID" > "$REC_ID_FILE"
fi

if echo "$RESP" | grep -q '"success":true'; then
    echo "$__IP" > "$LAST_FILE"
    date +%s > "$VERIFY_FILE"
    write_log 5 "cloudflare: $REC_NAME AAAA -> $__IP 更新成功"
    return 0
fi
write_log 3 "cloudflare: 更新失败: $RESP"
return 1
