import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/oc_log.txt", "w", encoding="utf-8") as log:

    # 检查启动日志
    log.write("=== openclash 启动日志 ===\n")
    stdin, stdout, stderr = client.exec_command("cat /tmp/openclash_start.log 2>/dev/null | tail -50", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无日志\n")

    # 检查 openclash 日志
    log.write("\n=== openclash.log ===\n")
    stdin, stdout, stderr = client.exec_command("cat /tmp/openclash.log 2>/dev/null | tail -50", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无日志\n")

    # 检查 config.yaml 是否生成
    log.write("\n=== config.yaml ===\n")
    stdin, stdout, stderr = client.exec_command("cat /etc/openclash/config.yaml 2>/dev/null | head -30", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "未生成\n")

    # 检查 config_path 配置
    log.write("\n=== config_path ===\n")
    stdin, stdout, stderr = client.exec_command("uci get openclash.config.config_path", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(f"path={out}\n")

    # 检查文件是否存在
    log.write("\n=== 配置文件检查 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /etc/openclash/config/6-15-solo.yaml", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

client.close()
print("done")
