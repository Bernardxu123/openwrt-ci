#!/bin/sh
# 立即关闭光猫管理通道，恢复到只有 PPPoE 的干净状态
DEV=wan

echo "关闭前："
ip -4 addr show dev ${DEV} | grep inet

if [ -f /tmp/ont_ttl.pid ]; then
    kill "$(cat /tmp/ont_ttl.pid)" 2>/dev/null && echo "已杀掉 TTL 定时器 $(cat /tmp/ont_ttl.pid)"
    rm -f /tmp/ont_ttl.pid
fi
rm -f /tmp/ont_persist

/tmp/ont_close.sh 2>/dev/null

echo
echo "关闭后（应为空）："
ip -4 addr show dev ${DEV} | grep inet
ip route show 192.168.1.0/24
echo
echo "PPPoE 状态："
ubus call network.interface.wan status | grep -E '"up"|"address"' | head -3