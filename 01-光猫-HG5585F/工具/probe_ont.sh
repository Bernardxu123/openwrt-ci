#!/bin/sh
# 在 WAN 物理口上临时挂地址，探测桥接后的光猫管理 IP
# 用完自动清理，不改任何持久配置

PROBE_IP=192.168.99.1
MASK=24
DEV=wan

cleanup() {
    ip addr del ${PROBE_IP}/${MASK} dev ${DEV} 2>/dev/null
}
trap cleanup EXIT INT TERM

ip addr add ${PROBE_IP}/${MASK} dev ${DEV} 2>/dev/null

echo "== 现有 wan 上的邻居 =="
ip neigh show dev ${DEV}

echo
echo "== ping 广播式铺 ARP =="
for c in 192.168.1.1 192.168.1.2 192.168.1.100 192.168.1.254 \
         192.168.2.1 192.168.2.2 192.168.2.100 192.168.2.254 \
         192.168.0.1 192.168.10.1 192.168.20.1 192.168.100.1 \
         192.168.100.2 192.168.1.100 ; do
    ping -c 1 -W 1 -I ${DEV} ${c} >/dev/null 2>&1
done

echo "-- 邻居表 --"
ip neigh show dev ${DEV}

echo
echo "== TCP 80 探测（带 3s 超时）=="
for c in 192.168.1.1 192.168.2.1 192.168.1.2 192.168.100.1 192.168.1.254; do
    if timeout 3 nc ${c} 80 </dev/null >/dev/null 2>&1; then
        echo "${c}:80  CONNECTED"
    else
        echo "${c}:80  no"
    fi
done

echo
echo "== 清理 =="
cleanup
echo done