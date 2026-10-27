#!/bin/sh
# 打开光猫管理通道：给 wan 口挂 192.168.1.2，通向光猫 192.168.1.1
# 零持久化：只改运行态，TTL 到点自动摘除；也可随时执行 ont_close.sh 立即关闭
# TTL=0：一直开启，直到手动执行 ont_close.sh

DEV=wan
IP=192.168.1.2
PFX=24
TARGET=192.168.1.0/24
TTL=${TTL:-1800}

echo "1) 先清理可能残留"
ip route del ${TARGET} dev ${DEV} 2>/dev/null
ip addr del ${IP}/${PFX} dev ${DEV} 2>/dev/null
rm -f /tmp/ont_persist

echo "2) 挂地址 + 路由"
ip addr add ${IP}/${PFX} dev ${DEV} || { echo "FAIL: addr add"; exit 1; }
ip route replace ${TARGET} dev ${DEV} src ${IP} || { echo "FAIL: route"; exit 1; }

echo "3) 邻居探测"
ping -c 2 -W 2 -I ${DEV} 192.168.1.1 >/dev/null 2>&1 && echo "  192.168.1.1 ping OK" || echo "  192.168.1.1 ping FAIL"
ip neigh show 192.168.1.1 dev ${DEV}

cat > /tmp/ont_close.sh <<'CLOSE'
#!/bin/sh
DEV=wan
IP=192.168.1.2
ip route del 192.168.1.0/24 dev ${DEV} 2>/dev/null
ip addr del ${IP}/24 dev ${DEV} 2>/dev/null
ip neigh flush to 192.168.1.0/24 dev ${DEV} 2>/dev/null
logger -t ont-tmp "TTL expired, cleaned"
echo "$(date) TTL expired, cleaned" >> /tmp/ont_access.log
rm -f /tmp/ont_ttl.pid /tmp/ont_persist
CLOSE
chmod +x /tmp/ont_close.sh

if [ "${TTL}" = "0" ]; then
    rm -f /tmp/ont_ttl.pid
    touch /tmp/ont_persist
    echo "4) 一直开启（需手动执行 ont_close.sh 关闭）"
else
    echo "4) 挂 ${TTL}s 自动清理"
    nohup sh -c "sleep ${TTL}; /tmp/ont_close.sh" >/dev/null 2>&1 &
    echo $! > /tmp/ont_ttl.pid
    echo "  自动清理 PID: $(cat /tmp/ont_ttl.pid)，${TTL}s 后执行"
fi

echo
echo "当前状态："
ip -4 addr show dev ${DEV} | grep inet
ip route show ${TARGET}
echo
echo "PC 侧直接开：http://192.168.1.1"
echo "立即关闭：python ssh_script.py tools/ont_close.sh"