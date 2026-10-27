#!/bin/sh
echo "=== ASSOC LIST phy1 (5G) ==="
iwinfo phy1-ap0 assoclist 2>/dev/null
echo
echo "=== ASSOC LIST phy0 (2.4G) ==="
iwinfo phy0-ap0 assoclist 2>/dev/null
echo
echo "=== NEIGHBOURS ==="
ip neigh show | grep -v FAILED
echo
echo "=== DHCP LEASES ==="
cat /tmp/dhcp.leases 2>/dev/null
echo
echo "=== counters BEFORE ==="
for d in pon0 pon0.995 pppoe-wan br-lan phy0-ap0 phy1-ap0 eth0; do
  echo "$d rx=$(cat /sys/class/net/$d/statistics/rx_bytes 2>/dev/null) tx=$(cat /sys/class/net/$d/statistics/tx_bytes 2>/dev/null)"
done
echo
echo "=== controlled download 30MB from router (direct to ISP) ==="
START=$(date +%s)
curl -s -o /dev/null -m 60 --interface pppoe-wan "http://mirrors.ustc.edu.cn/ubuntu-releases/24.04/ubuntu-24.04.2-desktop-amd64.iso" -r 0-30000000 2>/dev/null
END=$(date +%s)
echo "elapsed=$((END-START))s"
echo
echo "=== counters AFTER ==="
for d in pon0 pon0.995 pppoe-wan br-lan phy0-ap0 phy1-ap0 eth0; do
  echo "$d rx=$(cat /sys/class/net/$d/statistics/rx_bytes 2>/dev/null) tx=$(cat /sys/class/net/$d/statistics/tx_bytes 2>/dev/null)"
done
