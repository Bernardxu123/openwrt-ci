#!/bin/sh
# 刷机后恢复 DSH 手机入口依赖（nginx-ssl 包和 /usr/sbin/nginx 不随 sysupgrade 保留）
# 适用：QWRT/OpenWrt 重刷后，/etc/dsh-nginx、ddns 配置、cert、token 通过 sysupgrade keep 保留，
#       但 nginx-ssl/libpcre2/libxml2-16 等包会丢，导致 3081 无监听。
# 用法：在路由器上 sh /usr/bin/dsh-restore.sh
#       或 PC 上：python ssh_run.py 'sh /usr/bin/dsh-restore.sh'
# 前置：/etc/cf-dns.token 存在（若整机重置丢了，需要重新放 token）
set -u

echo "[1/5] opkg update + 补装 nginx-ssl / ddns-scripts"
opkg update >/dev/null 2>&1
opkg list-installed 2>/dev/null | grep -q "^nginx-ssl " || opkg install nginx-ssl
opkg list-installed 2>/dev/null | grep -q "^ddns-scripts " || opkg install ddns-scripts luci-app-ddns

echo "[2/5] 停用 nginx-ssl 自带 init（它会抢 80/443，和 uhttpd/mihomo 冲突）"
/etc/init.d/nginx stop 2>/dev/null || true
/etc/init.d/nginx disable 2>/dev/null || true
killall nginx 2>/dev/null || true
sleep 1

echo "[3/5] 启动 dsh-nginx（/var 是 tmpfs，先建目录）"
mkdir -p /var/lib/nginx/body /var/lib/nginx/proxy /var/lib/nginx/fastcgi \
         /var/lib/nginx/uwsgi /var/lib/nginx/scgi /var/log
[ -f /etc/dsh-nginx/upstream.conf ] || \
    echo 'server 192.168.31.218:3081 max_fails=2 fail_timeout=10s;' > /etc/dsh-nginx/upstream.conf
[ -f /etc/dsh-nginx/port ] || echo 3081 > /etc/dsh-nginx/port
/etc/init.d/dsh-nginx enable 2>/dev/null || true
/etc/init.d/dsh-nginx restart
sleep 2

echo "[4/5] 补齐 cron 与 sysupgrade keep"
grep -q "dsh-watchdog.sh" /etc/crontabs/root || echo "*/5 * * * * /usr/bin/dsh-watchdog.sh" >> /etc/crontabs/root
grep -q "acme.sh --cron" /etc/crontabs/root || echo "17 3 * * * /etc/acme.sh/acme.sh --cron --home /etc/acme.sh >/dev/null 2>&1" >> /etc/crontabs/root
/etc/init.d/cron restart >/dev/null 2>&1 || true
for p in /etc/dsh-nginx/ /etc/init.d/dsh-nginx /etc/rc.d/S99dsh-nginx /usr/bin/dsh-watchdog.sh \
         /usr/bin/dsh-restore.sh /usr/lib/ddns/update_cloudflare_dsh.sh /etc/cf-dns.token \
         /etc/dsh-ddns-last /etc/dsh-cf-zone.id /etc/dsh-cf-record.id /etc/acme.sh/ \
         /etc/dsh-nginx/cert/ /etc/crontabs/root; do
    grep -qxF "$p" /etc/sysupgrade.conf || echo "$p" >> /etc/sysupgrade.conf
done

echo "[5/5] 状态检查"
pidof nginx >/dev/null 2>&1 && echo "  nginx   : running" || echo "  nginx   : FAILED"
netstat -lntp 2>/dev/null | grep -q ":3081" && echo "  3081    : listening" || echo "  3081    : FAILED"
ps w 2>/dev/null | grep -q "[d]ynamic_dns" && echo "  ddns    : running" || echo "  ddns    : not running"
[ -f /etc/cf-dns.token ] && echo "  token   : present" || echo "  token   : MISSING（需要重新放 /etc/cf-dns.token）"
[ -f /etc/dsh-nginx/cert/dsh.fullchain.pem ] && echo "  cert    : present" || echo "  cert    : MISSING"
curl -sk -m 8 -o /dev/null -w "  local   : https=%{http_code}\n" https://dsh.290490.xyz:3081/ 2>/dev/null || echo "  local   : curl failed"
