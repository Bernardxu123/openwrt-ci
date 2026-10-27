#!/bin/sh
echo "=== napi threads: full list with affinity ==="
for p in $(ps w | awk '/napi\// {print $1}'); do
  nm=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | tr -d '\n')
  case "$nm" in
    *phy*) aff=$(taskset -p $p 2>/dev/null | awk '{print $NF}'); echo "  pid=$p $nm mask=$aff";;
  esac
done
echo "=== counts by name ==="
ps w | grep -o 'napi/[a-z0-9_-]*' | sort | uniq -c
echo
echo "=== phy queues count ==="
for d in phy0-ap0 phy1-ap0; do echo "  $d rx queues: $(ls /sys/class/net/$d/queues | grep -c rx-)"; done
echo
echo "=== irq effective affinity (all relevant) ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq: smp_affinity_list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) effective_affinity_list=$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)"
done
echo
echo "=== per-cpu netdev counters which CPU handles what (softnet_stat dropped/time_squeeze) ==="
awk '{print "  cpu"NR-1, "processed="$1, "dropped="$2, "time_squeeze="$3, "cpu_collision="$9, "received_rps="$10, "rps_flows="$12}' /proc/net/softnet_stat
echo
echo "=== current NET_RX softirq distribution ==="
grep NET_RX /proc/softirqs
echo "=== TASKLET ==="
grep TASKLET /proc/softirqs
echo
echo "=== CPU freq now ==="
for c in 0 1 2 3; do echo "  cpu$c=$(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq)"; done
