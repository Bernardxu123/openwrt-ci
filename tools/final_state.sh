#!/bin/sh
echo "=== IRQ final state ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)]"
done
echo
echo "=== uci changes ==="
uci changes
echo
echo "=== key uci ==="
echo "  packet_steering=$(uci -q get network.globals.packet_steering)"
echo "  flow_offloading=$(uci -q get firewall.@defaults[0].flow_offloading)"
echo "  flow_offloading_hw=$(uci -q get firewall.@defaults[0].flow_offloading_hw)"
echo "  passwall enabled=$(uci -q get passwall.@global[0].enabled)"
echo
echo "=== init.d enabled ==="
ls /etc/rc.d/ 2>/dev/null | grep -E 'wifi-napi|packet_steer'
echo
echo "=== load / mem ==="
cat /proc/loadavg
grep MemAvailable /proc/meminfo
echo
echo "=== nft flowtable ==="
nft list flowtable inet fw4 ft 2>/dev/null | grep -A1 flags | head -4
echo "  PPE entries=$(wc -l < /sys/kernel/debug/ppe/entries 2>/dev/null)"
grep npu_attached /sys/kernel/debug/ppe/config 2>/dev/null
