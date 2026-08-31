import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

cmds = [
    "# 安装必需软件包",
    "opkg install kmod-nft-tproxy tcpdump-mini vnstat2 2>&1 | tail -10",
    "# 启用软件 flow offloading",
    "uci set firewall.@defaults[0].flow_offloading='1'",
    "uci commit firewall",
    "# 验证",
    "uci get firewall.@defaults[0].flow_offloading",
]

for cmd in cmds:
    if cmd.startswith('#'):
        continue
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(f"\n=== {cmd} ===")
    if out:
        print(out)
    if err:
        print(f"ERR: {err}")

client.close()
