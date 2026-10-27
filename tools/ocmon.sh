#!/bin/sh
# ocmon.sh — read-only OpenClash/mihomo memory & instance observer (round3, 2026-10-24)
# Records only. Never kills, never restarts.
L=/tmp/ocmon.log
E=/tmp/ocmon-evidence
umask 077
[ -f "$L" ] && [ "$(wc -c <"$L")" -gt 524288 ] && mv "$L" "$L.1"
up=$(cut -d. -f1 /proc/uptime)
avail=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
n=$(pidof clash | wc -w)
line="$(date '+%F %T') boot=$up avail=${avail}k pids=$n"
for p in $(pidof clash); do
    [ -d "/proc/$p" ] || continue
    rss=$(awk '/^VmRSS/{print $2}' "/proc/$p/status" 2>/dev/null)
    vdata=$(awk '/^VmData/{print $2}' "/proc/$p/status" 2>/dev/null)
    ppid=$(awk '{print $4}' "/proc/$p/stat" 2>/dev/null)
    # cgroup of pid = 5th field of /proc/PID/stat? no: use /proc/PID/cgroup
    cg=$(sed -n 's/^0:://p' "/proc/$p/cgroup" 2>/dev/null)
    # cmdline is NUL-separated: translate before printing
    cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | cut -c1-120)
    line="$line | pid=$p ppid=$ppid rss=${rss}k vdata=${vdata}k cg=${cg} cmd=${cmd}"
done
echo "$line" >> "$L"
chmod 600 "$L" 2>/dev/null

if [ "$n" -gt 1 ] || [ "${avail%k}" -lt 51200 ]; then
    mkdir -p "$E" 2>/dev/null
    f="$E/$(date +%Y%m%d-%H%M%S).txt"
    {
        echo "== trigger: pids=$n avail=${avail}k at $(date '+%F %T')"
        echo "== line: $line"
        echo "== ps =="
        ps w | grep -E "clash|openclash_watchdog" | grep -v grep
        echo "== cgroup per clash pid =="
        for p in $(pidof clash); do echo "-- pid $p"; cat "/proc/$p/cgroup" 2>/dev/null; done
        echo "== parent chain =="
        for p in $(pidof clash); do echo "-- pid $p"; tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null; echo; done
        echo "== dmesg tail =="
        dmesg | tail -40
    } > "$f" 2>&1
    chmod 600 "$f"
fi
exit 0
