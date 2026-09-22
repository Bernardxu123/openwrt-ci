#!/bin/sh
# wugui-sub-update.sh — 同步乌龟订阅链接 + 解锁订阅开关 + 触发 daed 更新
# 配置: /etc/wugui-sub.conf (chmod 600)
# 日志: /tmp/wugui-sub-update.log
set -eu

CONF="${WUGUI_SUB_CONF:-/etc/wugui-sub.conf}"
LOG="${WUGUI_SUB_LOG:-/tmp/wugui-sub-update.log}"
LOCKDIR="${WUGUI_SUB_LOCK:-/tmp/wugui-sub-update.lock.d}"
LOG_KEEP=50
TMPD="/tmp/wugui-sub.$$"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
}

die() {
    log "FAIL: $*"
    exit 1
}

# json_get FILE EXPR — EXPR is JsonPath like @.data.token
json_get() {
    jsonfilter -i "$1" -e "$2" 2>/dev/null | head -n1
}

# json_escape STRING → safe JSON string body (no surrounding quotes)
# handles \, ", tab, CR; multi-line values are not supported
json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' -e 's/\r/\\r/g'
}

mkdir -p "$TMPD"

# --- lock (mkdir + PID; reclaim stale after crash) ---
acquire_lock() {
    if mkdir "$LOCKDIR" 2>/dev/null; then
        echo $$ > "$LOCKDIR/pid"
        return 0
    fi
    old_pid=$(cat "$LOCKDIR/pid" 2>/dev/null || echo "")
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        return 1
    fi
    # stale (no live PID): reclaim
    rm -rf "$LOCKDIR"
    if mkdir "$LOCKDIR" 2>/dev/null; then
        echo $$ > "$LOCKDIR/pid"
        return 0
    fi
    return 1
}

acquire_lock || die "another run is in progress ($LOCKDIR)"
cleanup() {
    rm -rf "$LOCKDIR"
    rm -rf "$TMPD"
}
trap cleanup EXIT

# --- load config (values must be shell-quoted in conf) ---
[ -r "$CONF" ] || die "config not readable: $CONF"
# shellcheck disable=SC1090
. "$CONF"

: "${WUGUI_EMAIL:?WUGUI_EMAIL missing}"
: "${WUGUI_PASSWORD:?WUGUI_PASSWORD missing}"
: "${WUGUI_API:?WUGUI_API missing}"
: "${DAED_URL:=http://192.168.31.1:2023/graphql}"
: "${DAED_USER:?DAED_USER missing}"
: "${DAED_PASS:?DAED_PASS missing}"
: "${DAED_SUB_ID:?DAED_SUB_ID missing}"
: "${DAED_SUB_TAG:=乌龟}"

# rotate log (keep last LOG_KEEP lines)
if [ -f "$LOG" ]; then
    tail -n "$LOG_KEEP" "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" || true
fi

log "=== wugui-sub-update start ==="

# --- 1) login (auth_data = Authorization header; data.token = subscribe URL token) ---
printf '{"email":"%s","password":"%s"}' \
    "$(json_escape "$WUGUI_EMAIL")" "$(json_escape "$WUGUI_PASSWORD")" > "$TMPD/login.json"
HTTP_CODE=$(curl -sk --connect-timeout 15 --max-time 60 \
    -X POST "$WUGUI_API/passport/auth/login" \
    -H 'Content-Type: application/json' -H 'Accept: application/json' \
    --data-binary @"$TMPD/login.json" \
    -o "$TMPD/login.resp" -w '%{http_code}') || HTTP_CODE=000
[ "$HTTP_CODE" = "200" ] || die "login HTTP $HTTP_CODE: $(head -c 200 "$TMPD/login.resp" 2>/dev/null)"

AUTH=$(json_get "$TMPD/login.resp" '@.data.auth_data')
[ -n "$AUTH" ] || die "login ok but no auth_data: $(head -c 200 "$TMPD/login.resp")"
log "login ok"

# --- 2) getSubscribe: current subscribe_url (token may have rotated) ---
HTTP_CODE=$(curl -sk --connect-timeout 15 --max-time 60 \
    -H "Authorization: $AUTH" -H 'Accept: application/json' \
    "$WUGUI_API/user/getSubscribe" \
    -o "$TMPD/subinfo.resp" -w '%{http_code}') || HTTP_CODE=000
[ "$HTTP_CODE" = "200" ] || die "getSubscribe HTTP $HTTP_CODE: $(head -c 200 "$TMPD/subinfo.resp" 2>/dev/null)"
SUB_URL=$(json_get "$TMPD/subinfo.resp" '@.data.subscribe_url')
[ -n "$SUB_URL" ] || die "no subscribe_url: $(head -c 200 "$TMPD/subinfo.resp")"
log "subscribe_url ok"

# --- 3) daed auth ---
printf '{"query":"query($u:String!,$p:String!){ token(username:$u,password:$p) }","variables":{"u":"%s","p":"%s"}}' \
    "$(json_escape "$DAED_USER")" "$(json_escape "$DAED_PASS")" > "$TMPD/daed-token.json"
HTTP_CODE=$(curl -sk --connect-timeout 10 --max-time 30 \
    -X POST "$DAED_URL" -H 'Content-Type: application/json' \
    --data-binary @"$TMPD/daed-token.json" \
    -o "$TMPD/daed-token.resp" -w '%{http_code}') || HTTP_CODE=000
[ "$HTTP_CODE" = "200" ] || die "daed token HTTP $HTTP_CODE"
DAED_TOKEN=$(json_get "$TMPD/daed-token.resp" '@.data.token')
[ -n "$DAED_TOKEN" ] || die "daed token empty: $(head -c 200 "$TMPD/daed-token.resp")"
log "daed auth ok"

# --- 4) sync daed subscription link if token rotated ---
printf '%s' '{"query":"{ subscriptions { id tag link } }"}' > "$TMPD/daed-subs.json"
HTTP_CODE=$(curl -sk --connect-timeout 10 --max-time 30 \
    -X POST "$DAED_URL" -H 'Content-Type: application/json' \
    -H "Authorization: $DAED_TOKEN" \
    --data-binary @"$TMPD/daed-subs.json" \
    -o "$TMPD/daed-subs.resp" -w '%{http_code}') || HTTP_CODE=000
[ "$HTTP_CODE" = "200" ] || die "daed subscriptions HTTP $HTTP_CODE"

CUR_LINK=$(jsonfilter -i "$TMPD/daed-subs.resp" -e "@.data.subscriptions[@.id=\"$DAED_SUB_ID\"].link" 2>/dev/null | head -n1)
if [ -z "$CUR_LINK" ]; then
    CUR_LINK=$(jsonfilter -i "$TMPD/daed-subs.resp" -e "@.data.subscriptions[@.tag=\"$DAED_SUB_TAG\"].link" 2>/dev/null | head -n1)
fi
if [ "$CUR_LINK" != "$SUB_URL" ]; then
    log "link changed, updating daed subscription link"
    printf '{"query":"mutation($id:ID!,$link:String!){ updateSubscriptionLink(id:$id,link:$link){ id link } }","variables":{"id":"%s","link":"%s"}}' \
        "$(json_escape "$DAED_SUB_ID")" "$(json_escape "$SUB_URL")" > "$TMPD/daed-link.json"
    HTTP_CODE=$(curl -sk --connect-timeout 10 --max-time 30 \
        -X POST "$DAED_URL" -H 'Content-Type: application/json' \
        -H "Authorization: $DAED_TOKEN" \
        --data-binary @"$TMPD/daed-link.json" \
        -o "$TMPD/daed-link.resp" -w '%{http_code}') || HTTP_CODE=000
    NEW_LINK=$(json_get "$TMPD/daed-link.resp" '@.data.updateSubscriptionLink.link')
    [ -n "$NEW_LINK" ] || die "updateSubscriptionLink failed HTTP $HTTP_CODE: $(head -c 300 "$TMPD/daed-link.resp")"
    log "daed link synced"
else
    log "daed link unchanged"
fi

# --- 5) unlock (Authorization = auth_data as-is; do NOT re-lock) ---
# success is 200 with locked=false; anything else is failure (exit 1)
printf '{}' > "$TMPD/unlock.json"
HTTP_CODE=$(curl -sk --connect-timeout 15 --max-time 60 \
    -X POST "$WUGUI_API/user/subscribe/unlock" \
    -H 'Content-Type: application/json' -H 'Accept: application/json' \
    -H "Authorization: $AUTH" \
    --data-binary @"$TMPD/unlock.json" \
    -o "$TMPD/unlock.resp" -w '%{http_code}') || HTTP_CODE=000
[ "$HTTP_CODE" = "200" ] || die "unlock HTTP $HTTP_CODE: $(head -c 200 "$TMPD/unlock.resp" 2>/dev/null)"
LOCKED=$(json_get "$TMPD/unlock.resp" '@.data.locked')
MINS=$(json_get "$TMPD/unlock.resp" '@.data.duration_minutes')
[ "$LOCKED" = "false" ] || [ "$LOCKED" = "0" ] || die "unlock returned locked=$LOCKED: $(head -c 200 "$TMPD/unlock.resp")"
log "unlock ok locked=$LOCKED duration_minutes=$MINS"

sleep 1

# --- 6) updateSubscription ---
printf '{"query":"mutation($id:ID!){ updateSubscription(id:$id){ id tag } }","variables":{"id":"%s"}}' \
    "$(json_escape "$DAED_SUB_ID")" > "$TMPD/daed-upd.json"
HTTP_CODE=$(curl -sk --connect-timeout 10 --max-time 120 \
    -X POST "$DAED_URL" -H 'Content-Type: application/json' \
    -H "Authorization: $DAED_TOKEN" \
    --data-binary @"$TMPD/daed-upd.json" \
    -o "$TMPD/daed-upd.resp" -w '%{http_code}') || HTTP_CODE=000
[ "$HTTP_CODE" = "200" ] || die "updateSubscription HTTP $HTTP_CODE: $(head -c 200 "$TMPD/daed-upd.resp" 2>/dev/null)"
UPD_TAG=$(json_get "$TMPD/daed-upd.resp" '@.data.updateSubscription.tag')
[ -n "$UPD_TAG" ] || die "updateSubscription failed: $(head -c 300 "$TMPD/daed-upd.resp")"
if jsonfilter -i "$TMPD/daed-upd.resp" -e '@.errors' 2>/dev/null | grep -q .; then
    die "updateSubscription GraphQL errors: $(head -c 300 "$TMPD/daed-upd.resp")"
fi
log "daed updateSubscription ok tag=$UPD_TAG"

log "=== wugui-sub-update success ==="
exit 0
