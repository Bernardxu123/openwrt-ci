import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 修改 OpenClash UCI 配置
cmds = [
    "# 1. 关闭 UDP QUIC 拦截（允许 HTTP/3）",
    "uci set openclash.config.disable_udp_quic='0'",
    "# 2. 启用 IPv6 代理",
    "uci set openclash.config.ipv6_enable='1'",
    "# 3. 启用自定义 DNS（让 yaml DNS 配置生效）",
    "uci set openclash.config.enable_custom_dns='1'",
    "# 4. 提交配置",
    "uci commit openclash",
    "# 5. 验证修改",
    "uci show openclash.config | grep -E 'udp_quic|ipv6_enable|custom_dns'",
]

for cmd in cmds:
    if cmd.startswith('#'):
        continue
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(f"\n=== {cmd} ===")
    if out:
        print(out)
    if err:
        print(f"ERR: {err}")

client.close()
