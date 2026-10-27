#!/bin/sh
# Per-core CPU + IRQ + net counters sampler for ponwrt (AN7581, 4x A53)
# Usage: sh cpu_percore_sample.sh <outdir> <duration_sec>
OUTDIR="${1:-/tmp/cpusample}"
DUR="${2:-125}"
mkdir -p "$OUTDIR"

STAT="$OUTDIR/procstat.raw"
NET="$OUTDIR/net.raw"
IRQ="$OUTDIR/interrupts.raw"
IRQEND="$OUTDIR/interrupts.end"
TOP="$OUTDIR/top.snap"
META="$OUTDIR/meta.txt"

{
  echo "date=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "uptime=$(cat /proc/uptime)"
  echo "kernel=$(uname -r)"
  echo "nproc=$(grep -c '^processor' /proc/cpuinfo)"
  echo "steering=$(uci -q get system.packet_steering)"
  echo "flow_hw=$(uci -q get firewall.@defaults[0].flow_offloading_hw 2>/dev/null)"
  echo "passwall=$(uci -q get passwall.@global[0].enabled)"
  echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
  echo "--- taskset of napi threads ---"
  for p in $(ps w | awk '/napi\/phy[0-9]+-/ {print $1}'); do
    echo "pid=$p cmd=$(tr '\0' ' ' < /proc/$p/cmdline) affinity=$(taskset -p $p 2>/dev/null | awk '{print $6}')"
  done
  echo "--- irq baseline ---"
  grep -E 'mt7915|airoha_eth|arch_timer|GICv3' /proc/interrupts | head -40
} > "$META" 2>&1

cp /proc/interrupts "$IRQ"

: > "$STAT"
: > "$NET"

i=0
while [ "$i" -lt "$DUR" ]; do
  {
    printf 'S %s ' "$(cat /proc/uptime | cut -d' ' -f1)"
    grep -E '^cpu[0-9]+ ' /proc/stat | tr '\n' '|'
    printf 'P %s\n' "$(grep -E '^procs_running|^procs_blocked' /proc/stat | tr '\n' ' ')"
  } >> "$STAT"

  {
    printf 'N %s ' "$(cat /proc/uptime | cut -d' ' -f1)"
    for d in /sys/class/net/*/statistics; do
      dev=$(basename "$(dirname "$d")")
      rx=$(cat "$d/rx_bytes" 2>/dev/null)
      tx=$(cat "$d/tx_bytes" 2>/dev/null)
      rp=$(cat "$d/rx_packets" 2>/dev/null)
      tp=$(cat "$d/tx_packets" 2>/dev/null)
      printf '%s:%s:%s:%s:%s ' "$dev" "$rx" "$tx" "$rp" "$tp"
    done
    printf '\n'
  } >> "$NET"

  i=$((i+1))
  sleep 1
done

cp /proc/interrupts "$IRQEND"

# 3 top snapshots (t0 / t~mid / t~end)
top -bn1 | head -20 >> "$TOP" 2>&1
echo "=== END ===" >> "$TOP"

# per-process CPU time snapshot at end (utime+stime jiffies)
{
  printf '%-8s %-10s %s\n' PID RSS COMM
  for p in /proc/[0-9]*; do
    pid=${p#/proc/}
    read -r _ comm rest < "$p/stat" 2>/dev/null || continue
    ut=$(awk '{print $14+$15}' "$p/stat" 2>/dev/null)
    st=$(awk '{print $16+$17}' "$p/stat" 2>/dev/null)
    rss=$(awk '{print $24*4}' "$p/stat" 2>/dev/null)
    [ -n "$ut" ] && printf '%-8s %-10s %s\n' "$pid" "${rss}K" "$comm"
  done
} > "$OUTDIR/procstat.end" 2>&1

echo "DONE $(date '+%H:%M:%S')" >> "$META"
