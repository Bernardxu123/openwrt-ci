import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 检查配置文件语法
print("=== 检查配置文件 ===")
stdin, stdout, stderr = client.exec_command("head -30 /etc/openclash/config/6-15-solo.yaml", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out)

# 检查 openclash init 脚本
print("\n=== openclash init 状态 ===")
stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print(out if out else "无输出")
if err:
    print(f"ERR: {err}")

# 手动尝试启动
print("\n=== 手动启动 openclash ===")
stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash start 2>&1", timeout=60)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print(out if out else "无输出")
if err:
    print(f"ERR: {err}")

import time
time.sleep(3)

# 再次检查进程
print("\n=== 启动后进程 ===")
stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(out if out else "无进程")

client.close()
