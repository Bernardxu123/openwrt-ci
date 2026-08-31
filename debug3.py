import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/debug2.txt", "w", encoding="utf-8") as log:

    # 检查 openclash 日志
    log.write("=== openclash 日志 ===\n")
    stdin, stdout, stderr = client.exec_command("cat /var/log/openclash.log 2>/dev/null | tail -30 || cat /tmp/openclash.log 2>/dev/null | tail -30 || echo 'no log file'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 logread
    log.write("\n=== logread openclash ===\n")
    stdin, stdout, stderr = client.exec_command("logread | grep -i openclash | tail -20", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 clash 核心日志
    log.write("\n=== clash core log ===\n")
    stdin, stdout, stderr = client.exec_command("cat /etc/openclash/run.log 2>/dev/null | tail -30 || cat /tmp/clash.log 2>/dev/null | tail -30 || echo 'no clash log'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 init 脚本
    log.write("\n=== init 脚本状态 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /etc/init.d/openclash", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 尝试直接运行 clash 检查配置
    log.write("\n=== 直接运行 clash 测试配置 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/6-15-solo.yaml --check 2>&1 | head -20", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    log.write(f"OUT: {out}\n")
    log.write(f"ERR: {err}\n")

client.close()
print("done")
