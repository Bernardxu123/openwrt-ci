import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 检查当前 OpenClash UCI 配置
cmds = [
    "uci show openclash.config | grep -E 'en_mode|operation_mode|ipv6|udp_quic|flow|dns_custom|proxy_mode|core_version' | head -20",
]

for cmd in cmds:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    print(f"\n=== {cmd} ===")
    if out:
        print(out)

client.close()
