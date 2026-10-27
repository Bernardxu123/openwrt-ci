#!/bin/sh
echo "=== nft flowtable offload flags ==="
nft list flowtable inet fw4 ft 2>/dev/null | grep -A2 flags | head -20
echo "--- flowtable count ---"
nft list flowtable inet fw4 ft 2>/dev/null | grep -c "flow add"
echo
echo "=== PPE config ==="
cat /sys/kernel/debug/ppe/config 2>/dev/null
echo "--- ppe entries count ---"
wc -l /sys/kernel/debug/ppe/entries 2>/dev/null
echo
echo "=== napi threads per phy (full ps) ==="
ps w | grep -i 'napi' | grep -v grep | awk '{print $1, $NF}' | sort -k2 | uniq -c -f1 | head -20
echo "--- exact phy thread names ---"
ps w | grep -o 'napi/phy[0-9]-[0-9]*' | sort -u
echo
echo "=== /proc/softirqs NET_RX per cpu ==="
grep -E '^NET_RX|^NET_TX' /proc/softirqs 2>/dev/null
echo
echo "=== current per-cpu irq totals (kernel accounting) ==="
awk '/^cpu[0-9]/ {print "cpu" NR-1, "user="$2, "sys="$4, "idle="$5, "irq="$7, "softirq="$8}' /proc/stat
echo
echo "=== xray / passwall cpu time (from /proc) ==="
for p in $(pgrep -f 'xray|chinadns' 2>/dev/null); do
  echo "pid=$p $(tr '\0' ' ' < /proc/$p/cmdline | cut -c1-60) utime=$(awk '{print $14}' /proc/$p/stat) stime=$(awk '{print $15}' /proc/$p/stat)"
done
echo
echo "=== wlan stats (mt76 debugfs) ==="
for f in /sys/kernel/debug/ieee80211/phy0/mt76xx/debugfs/tx_bytes /sys/kernel/debug/ieee80211/phy1/mt76xx/debugfs/tx_bytes; do echo "$f = $(cat $f 2>/dev/null)"; done
for f in /sys/kernel/debug/ieee80211/phy0/mt76xx/debugfs/rx_bytes /sys/kernel/debug/ieee80211/phy1/mt76xx/debugfs/rx_bytes; do echo "$f = $(cat $f 2>/dev/null)"; done
echo
echo "=== dmesg tail (irq/steering hints) ==="
dmesg | grep -i -E 'steering|rps|xps|affinity|airoha_eth|npu|ppe' | tail -25
