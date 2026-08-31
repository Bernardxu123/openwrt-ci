import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 读取修复后的配置
with open("D:/AI/路由/6-15-solo-fixed.yaml", "r", encoding="utf-8") as f:
    config_content = f.read()

# 用 stdin 通过 cat 上传
stdin, stdout, stderr = client.exec_command("cat > /etc/openclash/config/6-15-solo.yaml", timeout=30)
stdin.write(config_content)
stdin.close()
stdout.read()
err = stderr.read().decode("utf-8", errors="replace")
if err:
    print(f"Upload ERR: {err}")
else:
    print("配置上传成功 (已恢复新加坡自动组)")

# 重启 OpenClash
print("\n重启 OpenClash...")
stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash restart 2>&1", timeout=60)
stdout.read()
err = stderr.read().decode("utf-8", errors="replace")
print(f"Restart: {err if err else 'OK'}")

time.sleep(5)

# 验证
stdin, stdout, stderr = client.exec_command("ps | grep clash | grep -v grep | head -3", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")
print(f"\n进程状态:\n{out if out else 'clash 未运行'}")

client.close()
