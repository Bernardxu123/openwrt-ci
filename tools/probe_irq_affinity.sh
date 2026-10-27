#!/bin/sh
echo "=== packet_steering init script ==="
cat /etc/init.d/packet_steering 2>/dev/null
echo
echo "=== uci steering ==="
uci show system 2>/dev/null | grep -i steering
uci -q get system.packet_steering
echo "(end)"
echo
echo "=== irq -> affinity map ==="
for d in /proc/irq/*/; do
  irq=$(basename "$d")
  aff=$(cat "$d/smp_affinity_list" 2>/dev/null)
  [ -z "$aff" ] && continue
  desc=$(cat "/proc/interrupts" 2>/dev/null | awk -v i="$irq:" '$1==i {for(j=2;j<=NF;j++) printf "%s ", $j; print ""}')
  echo "irq=$irq aff=$aff  $desc"
done | head -80
echo
echo "=== napi threads ==="
ps w | grep -i napi | grep -v grep
echo
echo "=== airoha_eth.4 irq affinity (line 27) ==="
for irq in $(awk '/airoha_eth\.4|mt7915e/{print $1}' /proc/interrupts | tr -d ':'); do
  echo "irq $irq -> $(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null)"
done
echo
echo "=== flow offload status ==="
uci -q get firewall.@defaults[0].flow_offloading
uci -q get firewall.@defaults[0].flow_offloading_hw
ls /sys/kernel/debug/ 2>/dev/null | head -20
echo "--- npu_attached ---"
cat /sys/kernel/debug/airoha_npu/npu_attached 2>/dev/null
find /sys/kernel/debug -maxdepth 2 -iname '*ppe*' 2>/dev/null | head
echo "--- flow offload tables ---"
find /sys/kernel/debug -maxdepth 2 -type d -iname '*flow*' 2>/dev/null | head
for f in $(find /sys/kernel/debug -maxdepth 3 -iname '*flow*count*' 2>/dev/null | head -5); do echo "$f = $(cat $f)"; done
echo
echo "=== cpu freq ==="
for c in 0 1 2 3; do echo "cpu$c cur=$(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq 2>/dev/null) min=$(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_min_freq 2>/dev/null) max=$(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_max_freq 2>/dev/null)"; done
echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
