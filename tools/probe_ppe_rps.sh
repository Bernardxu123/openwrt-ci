#!/bin/sh
echo "=== PPE entries sample (types/ports) ==="
head -8 /sys/kernel/debug/ppe/entries 2>/dev/null
echo "..."
echo "--- type histogram ---"
awk '{print $1}' /sys/kernel/debug/ppe/entries 2>/dev/null | sort | uniq -c
echo
echo "=== phy rps/xps ==="
for dev in phy0-ap0 phy1-ap0 br-lan; do
  echo "--- $dev ---"
  for q in /sys/class/net/$dev/queues/*/; do
    n=$(basename "$q")
    echo "  $n rps_cpus=$(cat $q/rps_cpus 2>/dev/null) rps_flow_cnt=$(cat $q/rps_flow_cnt 2>/dev/null) xps=$(cat $q/xps_cpus 2>/dev/null)"
  done
done
echo
echo "=== airoha_eth irq -> cpu binding (queue irq) ==="
for irq in 19 23 27 53 54; do
  echo "irq $irq eff_list=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)] eff=[$(cat /proc/irq/$irq/effective_affinity 2>/dev/null)] nodename=[$(cat /proc/irq/$irq/node 2>/dev/null)]"
done
echo
echo "=== cpulets / irqbalance present? ==="
ls /usr/sbin/cpulets /usr/sbin/irqbalance /sbin/irqbalance 2>/dev/null
apk list --installed 2>/dev/null | grep -i -E 'irqbalance|cpulets|lirq'
echo
echo "=== softnet_stat per-cpu (processed/rx) ==="
awk '{print "cpu"NR-1, "processed="$1, "dropped="$2, "time_squeeze="$3, "cpu_collision="$9, "received_rps="$10}' /proc/net/softnet_stat 2>/dev/null
echo
echo "=== current load ==="
cat /proc/loadavg
echo
echo "=== steering_flows uci ==="
uci -q get network.globals.steering_flows
uci -q get network.globals.packet_steering
