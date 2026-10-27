#!/bin/sh
# v2 sampler: per-core CPU + softirq per core + per-thread utime/stime + per-CPU IRQ + net counters
OUT=/tmp/s2
DUR="${1:-100}"
mkdir -p $OUT
: > $OUT/stat.raw
: > $OUT/softirq.raw
: > $OUT/threads.raw
: > $OUT/irq.raw
: > $OUT/net.raw

th_snapshot() {
	for p in /proc/[0-9]*; do
		pid=${p#/proc/}
		[ -r "$p/cmdline" ] || continue
		name=$(tr '\0' ' ' < $p/cmdline 2>/dev/null)
		case "$name" in
			*napi/*|*xray*|*ksoftirqd*|*hostapd*) ;;
			*) continue ;;
		esac
		read -r a b c d e f g h i j k l m n o q r s t u v w x y z aa bb cc dd << EOF
$(cat $p/stat 2>/dev/null)
EOF
		[ -z "${m:-}" ] && continue
		ut=$((m+n))
		st=$((o+p))
		echo "$pid|$ut$st|$name"
	done
}

i=0
while [ $i -lt "$DUR" ]; do
	ts=$(cat /proc/uptime | cut -d' ' -f1)
	echo "S $ts $(grep -E '^cpu[0-9]+ ' /proc/stat | tr '\n' ' ')" >> $OUT/stat.raw
	echo "F $ts $(grep -E 'NET_RX|NET_TX|TASKLET|SCHED' /proc/softirqs 2>/dev/null | tr '\n' ' ')" >> $OUT/softirq.raw
	echo "I $ts $(grep -E 'airoha_eth|mt7915e' /proc/interrupts 2>/dev/null | tr '\n' ' ')" >> $OUT/irq.raw
	th_snapshot | while IFS='|' read pid st name; do
		echo "T $ts $pid $st $name" >> $OUT/threads.raw
	done
	echo "N $ts $(for d in /sys/class/net/*/statistics; do dev=$(basename "$(dirname "$d")"); printf '%s:%s:%s ' "$dev" "$(cat $d/rx_bytes 2>/dev/null)" "$(cat $d/tx_bytes 2>/dev/null)"; done)" >> $OUT/net.raw
	i=$((i+1))
	sleep 1
done
echo DONE >> $OUT/stat.raw
