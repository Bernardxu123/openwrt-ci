import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 检查进程
print("=== 进程状态 ===")
stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out if out else "无进程")

# 检查配置文件
print("\n=== 配置文件行数 ===")
stdin, stdout, stderr = client.exec_command("wc -l /etc/openclash/config/6-15-solo.yaml", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out)

# 检查日志
print("\n=== 最近日志 ===")
stdin, stdout, stderr = client.exec_command("logread | grep -iE 'openclash|clash|mihomo' | tail -10", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out if out else "无日志")

client.close()
