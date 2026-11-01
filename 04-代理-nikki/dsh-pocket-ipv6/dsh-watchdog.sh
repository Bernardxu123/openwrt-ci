#!/bin/sh
# DSH 远程入口 + DDNS 看门狗（部署到 /usr/bin/dsh-watchdog.sh，cron 每 2 分钟）
# 1) nginx 不在就重启（/var/lib/nginx 是 tmpfs，重启后可能缺目录）
# 2) ddns 守护进程不在就后台拉起（-S <section> -- start 是前台常驻，必须放后台）
# 3) DSH Pocket 端口漂移（默认 3081，被占会 +1..+9）→ 自动改写 nginx 上游并 reload
# 4) pppoe-wan 的 IPv6 与最近成功推送值持续 15 分钟不一致 → 告警并重启 ddns
# 5) TLS 证书剩余 <14 天 → 告警（每小时检查一次）
#
# ★ 端口探测必须用 curl：PC 侧未监听端口会被 Windows 防火墙静默丢包，
#   BusyBox wget 的 -T 不覆盖 connect，会挂到 TCP 超时（2026-11-01 踩坑）。

PC=192.168.31.218
PORTFILE=/etc/dsh-nginx/port
UPSTREAM=/etc/dsh-nginx/upstream.conf
MISMATCH_MARK=/tmp/.dsh-watchdog-ddns-mismatch
CERT_MARK=/tmp/.dsh-watchdog-cert
SCAN_MARK=/tmp/.dsh-watchdog-scan
CERT=/etc/dsh-nginx/cert/dsh.fullchain.pem
LOCK=/var/lock/dsh-watchdog.lock

now() { date +%s; }

# ---- 单实例锁（上一轮卡死超过 5 分钟可抢占）----
if ! mkdir "$LOCK" 2>/dev/null; then
    TS=$(cat "$LOCK/ts" 2>/dev/null)
    case "$TS" in ''|*[!0-9]*) TS=0;; esac
    [ $(( $(now) - TS )) -lt 300 ] && exit 0
    rm -rf "$LOCK"
    mkdir "$LOCK" 2>/dev/null || exit 0
fi
now > "$LOCK/ts"
trap 'rm -rf "$LOCK"' EXIT INT TERM

# ---- 1) nginx ----
if ! pidof nginx >/dev/null 2>&1; then
    logger -t dsh-watchdog "nginx not running, restarting"
    /etc/init.d/dsh-nginx restart >/dev/null 2>&1
fi

# ---- 2) ddns 守护 ----
if ! pgrep -f "dynamic_dns_updater.sh.*dsh_ipv6" >/dev/null 2>&1; then
    logger -t dsh-watchdog "ddns daemon not running, starting"
    rm -f /var/run/ddns/dsh_ipv6.pid
    ( /usr/lib/ddns/dynamic_dns_updater.sh -S dsh_ipv6 -- start >/dev/null 2>&1 & )
fi

# ---- 3) Pocket 端口自动发现（轻量：每轮只探当前端口，探不通才扫描，且扫描 10 分钟一次）----
CUR=$(cat "$PORTFILE" 2>/dev/null)
PORT_OK=0
[ -n "$CUR" ] && curl -s -m 2 --connect-timeout 1 -o /dev/null "http://$PC:$CUR/" 2>/dev/null && PORT_OK=1
if [ "$PORT_OK" = "0" ]; then
    LAST_SCAN=$(cat "$SCAN_MARK" 2>/dev/null)
    case "$LAST_SCAN" in ''|*[!0-9]*) LAST_SCAN=0;; esac
    if [ $(( $(now) - LAST_SCAN )) -ge 600 ]; then
        now > "$SCAN_MARK"
        NEW=""
        for p in 3081 3082 3083 3084; do
            [ "$p" = "$CUR" ] && continue
            if curl -s -m 2 --connect-timeout 1 -o /dev/null "http://$PC:$p/" 2>/dev/null; then NEW=$p; break; fi
        done
        if [ -n "$NEW" ]; then
            printf 'server %s:%s max_fails=2 fail_timeout=10s;\n' "$PC" "$NEW" > "$UPSTREAM.new"
            mv "$UPSTREAM.new" "$UPSTREAM"
            echo "$NEW" > "$PORTFILE"
            if /usr/sbin/nginx -t -c /etc/dsh-nginx/nginx.conf >/dev/null 2>&1; then
                /usr/sbin/nginx -c /etc/dsh-nginx/nginx.conf -s reload >/dev/null 2>&1
                sleep 1
                # 2026-11-01 实测：OpenSSL 偶发 SSL_CTX_new 失败会让 reload 静默失效（旧 worker 继续用旧上游）
                CODE=$(curl -sk -m 3 -o /dev/null -w '%{http_code}' -H "Host: dsh.290490.xyz" "https://[::1]:3081/" 2>/dev/null)
                case "$CODE" in
                    200|302) logger -t dsh-watchdog "pocket upstream -> $PC:$NEW (was ${CUR:-none}), nginx reloaded (probe $CODE)" ;;
                    *)  logger -t dsh-watchdog -p user.warn "reload did not take effect (probe ${CODE:-fail}), restarting nginx"
                        /etc/init.d/dsh-nginx restart >/dev/null 2>&1 ;;
                esac
            else
                logger -t dsh-watchdog -p user.err "nginx -t failed after upstream change to $NEW"
            fi
        fi
    fi
fi

# ---- 4) IPv6 与 DDNS 缓存一致性（持续 15 分钟才算异常）----
WAN6=$(ip -6 addr show dev pppoe-wan scope global 2>/dev/null | awk '/inet6/{sub(/\/.*/,"",$2); print $2; exit}')
LAST=$(cat /etc/dsh-ddns-last 2>/dev/null)
if [ -n "$WAN6" ] && [ "$WAN6" != "$LAST" ]; then
    if [ ! -f "$MISMATCH_MARK" ]; then
        now > "$MISMATCH_MARK"
    else
        SINCE=$(cat "$MISMATCH_MARK" 2>/dev/null)
        case "$SINCE" in ''|*[!0-9]*) SINCE=$(now); echo "$SINCE" > "$MISMATCH_MARK";; esac
        if [ $(( $(now) - SINCE )) -ge 900 ]; then
            logger -t dsh-watchdog -p user.warn "IPv6 mismatch >15min: wan=$WAN6 last=${LAST:-none}, restarting ddns"
            /etc/init.d/ddns restart >/dev/null 2>&1
            rm -f "$MISMATCH_MARK"
        fi
    fi
else
    rm -f "$MISMATCH_MARK"
fi

# ---- 5) 证书到期（每小时一次）----
if [ -f "$CERT" ]; then
    CHECKED=$(cat "$CERT_MARK" 2>/dev/null)
    case "$CHECKED" in ''|*[!0-9]*) CHECKED=0;; esac
    if [ $(( $(now) - CHECKED )) -ge 3600 ]; then
        now > "$CERT_MARK"
        openssl x509 -checkend 1209600 -noout -in "$CERT" 2>/dev/null || \
            logger -t dsh-watchdog -p user.warn "TLS cert expires in <14 days"
    fi
fi
