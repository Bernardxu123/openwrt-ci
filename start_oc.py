import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 启用并启动 OpenClash
cmds = [
    "uci set openclash.config.enable='1'",
    "uci commit openclash",
    "/etc/init.d/openclash start 2>&1",
]

for cmd in cmds:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    print(f"{cmd}: {'OK' if not err else err}")

time.sleep(5)

# 检查进程
stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(f"\n进程: {out if out else '无'}")

client.close()
