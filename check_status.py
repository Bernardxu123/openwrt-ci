import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 检查 mihomo 进程
print("=== mihomo 进程 ===")
stdin, stdout, stderr = client.exec_command("ps | grep -E 'mihomo|openclash' | grep -v grep", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out if out else "无进程")

# 检查 OpenClash 状态
print("\n=== OpenClash init 状态 ===")
stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status 2>&1", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out if out else "无输出")

# 检查日志
print("\n=== 最近日志 ===")
stdin, stdout, stderr = client.exec_command("logread | grep -iE 'openclash|mihomo|error' | tail -15", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out if out else "无日志")

# 检查配置文件是否正确
print("\n=== 检查上传的配置文件行数 ===")
stdin, stdout, stderr = client.exec_command("wc -l /etc/openclash/config/6-15-solo.yaml", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out)

client.close()
