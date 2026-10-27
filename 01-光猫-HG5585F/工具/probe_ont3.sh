#!/bin/sh
# 这次用同子网地址 192.168.1.2 探，验证光猫是否只认自己 LAN 子网的源

DEV=wan
MYIP=192.168.1.2

cleanup() {
    ip addr del ${MYIP}/24 dev ${DEV} 2>/dev/null
}
trap cleanup EXIT INT TERM

ip addr add ${MYIP}/24 dev ${DEV} 2>/dev/null
ping -c 1 -W 1 -I ${DEV} 192.168.1.1 >/dev/null 2>&1

echo "== 端口 =="
for p in 22 23 80 443 8080; do
    if timeout 3 nc -w 2 192.168.1.1 ${p} </dev/null >/dev/null 2>&1; then
        echo "  ${p}  CONNECTED"
    else
        echo "  ${p}  closed/filtered"
    fi
done

echo
echo "== HTTP GET / =="
timeout 8 wget -T 5 -S -O - http://192.168.1.1/ 2>&1 | head -30

echo
echo "== 清理 =="
cleanup
echo done