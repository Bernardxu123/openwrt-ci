#!/bin/sh
echo "=== phy1 (5G) station dump with byte counters ==="
iw dev phy1-ap0 station dump 2>/dev/null | grep -E "^Station|bytes:|signal:|tx bitrate:|rx bitrate:"
echo
echo "=== phy0 (2.4G) station dump ==="
iw dev phy0-ap0 station dump 2>/dev/null | grep -E "^Station|bytes:|signal:" | head -40
echo
echo "=== ap0 netdev counters now ==="
for d in pon0 pon0.995 pppoe-wan br-lan phy0-ap0 phy1-ap0; do
  echo "$d rx=$(cat /sys/class/net/$d/statistics/rx_bytes) tx=$(cat /sys/class/net/$d/statistics/tx_bytes)"
done
echo
echo "=== 5s live rate check ==="
a_r=$(cat /sys/class/net/pon0/statistics/rx_bytes); a_t=$(cat /sys/class/net/pon0/statistics/tx_bytes)
b_r=$(cat /sys/class/net/br-lan/statistics/rx_bytes); b_t=$(cat /sys/class/net/br-lan/statistics/tx_bytes)
p1_r=$(cat /sys/class/net/phy1-ap0/statistics/rx_bytes); p1_t=$(cat /sys/class/net/phy1-ap0/statistics/tx_bytes)
p0_r=$(cat /sys/class/net/phy0-ap0/statistics/rx_bytes); p0_t=$(cat /sys/class/net/phy0-ap0/statistics/tx_bytes)
sleep 5
c_r=$(cat /sys/class/net/pon0/statistics/rx_bytes); c_t=$(cat /sys/class/net/pon0/statistics/tx_bytes)
d_r=$(cat /sys/class/net/br-lan/statistics/rx_bytes); d_t=$(cat /sys/class/net/br-lan/statistics/tx_bytes)
q1_r=$(cat /sys/class/net/phy1-ap0/statistics/rx_bytes); q1_t=$(cat /sys/class/net/phy1-ap0/statistics/tx_bytes)
q0_r=$(cat /sys/class/net/phy0-ap0/statistics/rx_bytes); q0_t=$(cat /sys/class/net/phy0-ap0/statistics/tx_bytes)
echo "pon0 rx=$(( (c_r-a_r)*8/5/1000000 ))Mbps tx=$(( (c_t-a_t)*8/5/1000000 ))Mbps"
echo "brlan rx=$(( (d_r-b_r)*8/5/1000000 ))Mbps tx=$(( (d_t-b_t)*8/5/1000000 ))Mbps"
echo "phy1  rx=$(( (q1_r-p1_r)*8/5/1000000 ))Mbps tx=$(( (q1_t-p1_t)*8/5/1000000 ))Mbps"
echo "phy0  rx=$(( (q0_r-p0_r)*8/5/1000000 ))Mbps tx=$(( (q0_t-p0_t)*8/5/1000000 ))Mbps"
