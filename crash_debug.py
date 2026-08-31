import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/crash_debug.txt", "w", encoding="utf-8") as log:

    # 检查 OpenClash 脚本
    log.write("=== openclash start 命令 ===\n")
    stdin, stdout, stderr = client.exec_command("grep -A30 'start_service' /etc/init.d/openclash 2>/dev/null | head -40 || grep -A30 'start' /etc/init.d/openclash | head -40", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查配置文件是否存在 clash 启动 yaml
    log.write("\n=== 运行配置文件 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /etc/openclash/*.yaml 2>/dev/null", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 config.yaml 是否生成
    log.write("\n=== /etc/openclash/config.yaml ===\n")
    stdin, stdout, stderr = client.exec_command("head -30 /etc/openclash/config.yaml 2>/dev/null || echo 'not generated'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 run 目录
    log.write("\n=== run 目录 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /etc/openclash/run/ 2>/dev/null | head -10", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 手动尝试生成配置
    log.write("\n=== 手动生成配置 ===\n")
    stdin, stdout, stderr = client.exec_command("/usr/share/openclash/openclash.sh 2>&1 | head -20", timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(f"OUT: {out}\n")

    # 再次检查进程
    log.write("\n=== 当前进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo|openclash' | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

client.close()
print("done")
