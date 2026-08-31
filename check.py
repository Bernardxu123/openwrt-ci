import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

cmds = [
    "lsmod 2>/dev/null | grep -i nss | head -5",
    "cat /sys/module/ath11k/parameters/nss_offload 2>/dev/null",
    "nft --version",
    "cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null",
    "cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null",
    "zramctl 2>/dev/null | head -5",
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
