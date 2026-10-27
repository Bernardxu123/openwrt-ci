#!/bin/sh
echo "=== steering UCI (network globals) ==="
uci show network 2>/dev/null | grep -i -E 'steering|globals'
echo
echo "=== effective smp_affinity (hex, single cpu?) vs list ==="
for irq in 19 23 27 53 54 11; do
  echo "irq $irq: smp_affinity=$(cat /proc/irq/$irq/smp_affinity 2>/dev/null)  list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null)  eff=$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)  desc=$(awk -v i=$irq: '$1==i {for(j=2;j<=5;j++) printf "%s ", $j}' /proc/interrupts)"
done
echo
echo "=== napi thread counts by name ==="
ps w | grep -o 'napi/[a-z0-9_-]*' | sort | uniq -c
echo
echo "=== wifi napi taskset (phy0) ==="
for p in $(ps w | awk '/napi\/phy[0-9]+-/ {print $1}'); do
  echo "pid=$p $(tr '\0' ' ' < /proc/$p/cmdline) -> $(taskset -p $p 2>/dev/null)"
done
echo
echo "=== qdma_eth napi taskset (first 8) ==="
i=0
for p in $(ps w | awk '/napi\/qdma_eth-/ {print $1}'); do
  i=$((i+1)); [ $i -gt 8 ] && break
  echo "pid=$p -> $(taskset -p $p 2>/dev/null)"
done
echo
echo "=== PPE flow offload ==="
ls /sys/kernel/debug/ppe/ 2>/dev/null
for f in /sys/kernel/debug/ppe/*/npu_attached /sys/kernel/debug/ppe/npu_attached; do [ -f "$f" ] && echo "$f = $(cat $f)"; done
echo "--- ppe dirs ---"
find /sys/kernel/debug/ppe -maxdepth 2 -type d 2>/dev/null | head -20
echo "--- flow counters ---"
for f in $(find /sys/kernel/debug/ppe -maxdepth 3 -iname '*count*' -o -iname '*stat*' 2>/dev/null | head -20); do echo "$f = $(cat $f 2>/dev/null)"; done
echo
echo "=== napi rx counters ==="
for d in /sys/class/net/*/statistics; do
  dev=$(basename "$(dirname "$d")")
  case "$dev" in br-lan|phy0-ap0|phy1-ap0|pon0|pon0.995|pppoe-wan|eth0|lan1|lan2|lan3|lan4) echo "$dev rx=$(cat $d/rx_bytes) tx=$(cat $d/tx_bytes)";; esac
done
echo
echo "=== dsa/eth link ==="
for i in phy0 phy1; do echo "--- $i ---"; cat /sys/class/net/$i-ap0/operstate 2>/dev/null; done
echo "=== wlan stations ==="
iwinfo 2>/dev/null | head -60
