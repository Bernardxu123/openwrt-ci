import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 读取本地配置
with open("D:/AI/路由/6-15-solo-v3.yaml", "r", encoding="utf-8") as f:
    config = f.read()

# 上传配置
stdin, stdout, stderr = client.exec_command("cat > /etc/openclash/config/6-15-solo.yaml", timeout=30)
stdin.write(config)
stdin.close()
stdout.read()
err = stderr.read().decode("utf-8", errors="replace")
print(f"上传配置: {'OK' if not err else err}")

# 启用并启动 OpenClash
stdin, stdout, stderr = client.exec_command("uci set openclash.config.enable='1' && uci commit openclash", timeout=30)
stdout.read()
print("启用 OpenClash")

time.sleep(1)

# 启动
stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash start 2>&1", timeout=60)
stdout.read()
err = stderr.read().decode("utf-8", errors="replace")
print(f"启动: {'OK' if not err else err}")

time.sleep(6)

# 检查进程
stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(f"进程:\n{out if out else '无进程'}")

# 检查端口
stdin, stdout, stderr = client.exec_command("netstat -tlnp 2>/dev/null | grep -E '7890|7891|7892|7893|7874'", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(f"端口:\n{out if out else '无监听'}")

client.close()
