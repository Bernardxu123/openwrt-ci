import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

cmds = [
    "cat /proc/swaps",
    "cat /sys/block/zram0/disksize 2>/dev/null || echo 'no zram0'",
    "ls /sys/class/thermal/thermal_zone*/temp 2>/dev/null",
    "for f in /sys/class/thermal/thermal_zone*/temp; do echo \"$f: $(cat $f)\"; done",
    "uci show openclash | head -30",
    "uci show firewall | grep -c 'rule'",
    "cat /etc/config/openclash 2>/dev/null | head -5",
    "grep -c 'proxy_group' /tmp/installed.txt 2>/dev/null || true",
]

for cmd in cmds:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(f"\n=== {cmd} ===")
    if out:
        print(out)
    if err:
        print(f"ERR: {err}")

client.close()
