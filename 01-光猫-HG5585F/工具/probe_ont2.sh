#!/bin/sh
# 确认光猫 192.168.1.1 的管理服务端口与 HTTP 响应

PROBE_IP=192.168.99.1
DEV=wan

cleanup() {
    ip addr del ${PROBE_IP}/24 dev ${DEV} 2>/dev/null
}
trap cleanup EXIT INT TERM

ip addr add ${PROBE_IP}/24 dev ${DEV} 2>/dev/null
ping -c 1 -W 1 -I ${DEV} 192.168.1.1 >/dev/null 2>&1

echo "== 邻居确认 =="
ip neigh show 192.168.1.1 dev ${DEV}

echo
echo "== 端口扫描 192.168.1.1 =="
for p in 22 23 80 443 8080 8443; do
    if timeout 3 nc -w 2 192.168.1.1 ${p} </dev/null >/dev/null 2>&1; then
        echo "  ${p}  CONNECTED"
    else
        echo "  ${p}  closed/filtered"
    fi
done

echo
echo "== HTTP GET / =="
timeout 8 wget -T 5 -S -O - http://192.168.1.1/ 2>&1 | head -25

echo
echo "== 清理 =="
cleanup
echo done