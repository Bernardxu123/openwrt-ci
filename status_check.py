import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/status_check.txt", "w", encoding="utf-8") as log:

    # 检查进程
    log.write("=== 进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

    # 检查 init 状态
    log.write("\n=== init 状态 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无输出\n")

    # 检查端口
    log.write("\n=== 端口 ===\n")
    stdin, stdout, stderr = client.exec_command("netstat -tlnp 2>/dev/null | grep -E '7890|7891|7892|7893|7874'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无监听\n")

    # 检查配置文件新加坡组
    log.write("\n=== 新加坡组确认 ===\n")
    stdin, stdout, stderr = client.exec_command("grep -B1 -A3 '新加坡' /etc/openclash/config/6-15-solo.yaml", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "未找到\n")

    # 检查 openclash 日志
    log.write("\n=== 最近 openclash 日志 ===\n")
    stdin, stdout, stderr = client.exec_command("logread 2>/dev/null | grep -i openclash | tail -15", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无日志\n")

client.close()
print("done")
