#!/bin/sh
# Per-thread CPU attribution sampler: tracks utime+stime of key threads + per-core /proc/stat
OUT=/tmp/attr
mkdir -p $OUT
: > $OUT/threads.raw
: > $OUT/stat.raw

snap_threads() {
	for p in /proc/[0-9]*; do
		pid=${p#/proc/}
		name=$(tr '\0' ' ' < $p/cmdline 2>/dev/null)
		case "$name" in
			*napi/*) ;;
			*xray*) ;;
			*hostapd*) ;;
			*ksoftirqd*) ;;
			*) continue ;;
		esac
		st=$(awk '{print $14+$15}' $p/stat 2>/dev/null)
		[ -z "$st" ] && continue
		echo "$pid|$name|$st"
	done
}

i=0
while [ $i -lt 90 ]; do
	ts=$(cat /proc/uptime | cut -d' ' -f1)
	# per-core stat
	echo "S $ts $(grep -E '^cpu[0-9]+ ' /proc/stat | tr '\n' ' ')" >> $OUT/stat.raw
	# thread cpu time
	snap_threads | while IFS='|' read pid name st; do
		echo "T $ts $pid $st $name" >> $OUT/threads.raw
	done
	i=$((i+1))
	sleep 1
done
echo DONE >> $OUT/stat.raw
