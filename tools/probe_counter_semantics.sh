#!/bin/sh
snap() {
	for d in pon0 pon0.995 pppoe-wan br-lan phy0-ap0 phy1-ap0 eth0; do
		echo "$d rx=$(cat /sys/class/net/$d/statistics/rx_bytes 2>/dev/null) tx=$(cat /sys/class/net/$d/statistics/tx_bytes 2>/dev/null)"
	done
}
echo "=== BEFORE ==="
snap
echo
echo "=== try downloads (router-originated, direct) ==="
for U in "https://speed.cloudflare.com/__down?bytes=200000000" "http://mirrors.ustc.edu.cn/ubuntu-releases/24.04/ubuntu-24.04.2-desktop-amd64.iso" "http://speedtest.tele2.net/100MB.zip"; do
	echo "--- $U"
	T0=$(date +%s)
	curl -s -o /dev/null -m 45 "$U" 2>/dev/null
	RC=$?
	T1=$(date +%s)
	echo "    rc=$RC elapsed=$((T1-T0))s"
done
echo
echo "=== AFTER ==="
snap
echo
echo "=== PPE entry types ==="
awk '{print $1}' /sys/kernel/debug/ppe/entries 2>/dev/null | sort | uniq -c
head -5 /sys/kernel/debug/ppe/entries 2>/dev/null
