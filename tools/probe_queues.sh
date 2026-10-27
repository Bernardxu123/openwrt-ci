#!/bin/sh
echo "=== bridge membership ==="
brctl show 2>/dev/null || bridge link show 2>/dev/null
echo
echo "=== ip link brief ==="
ip -br link show
echo
echo "=== ip addr (pon/pppoe) ==="
ip -br addr show | grep -E 'pon|pppoe|br-lan|phy'
echo
echo "=== rps/xps on queues ==="
for dev in pon0 eth0 lan1 br-lan phy0-ap0 phy1-ap0; do
  echo "--- $dev ---"
  for q in /sys/class/net/$dev/queues/*/; do
    n=$(basename "$q")
    rps=$(cat "$q/rps_cpus" 2>/dev/null)
    rfc=$(cat "$q/rps_flow_cnt" 2>/dev/null)
    xps=$(cat "$q/xps_cpus" 2>/dev/null)
    echo "  $n rps_cpus=$rps rps_flow_cnt=$rfc xps_cpus=$xps"
  done
done
echo
echo "=== steering debug (ucode -d) ==="
sh /usr/libexec/network/packet-steering.uc -d 2 2>&1 | head -40
echo
echo "=== cpulets? ==="
ls /usr/libexec/ 2>/dev/null | head -20
ls /etc/init.d/ | head -40
