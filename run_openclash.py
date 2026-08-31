import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/uci_full.txt", "w", encoding="utf-8") as log:

    # 检查完整 UCI 配置
    log.write("=== openclash UCI 配置 ===\n")
    stdin, stdout, stderr = client.exec_command("uci show openclash", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 openclash.sh 是否存在
    log.write("\n=== openclash.sh ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /usr/share/openclash/openclash.sh 2>/dev/null", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 yml_change.sh
    log.write("\n=== yml_change.sh ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /usr/share/openclash/yml_change.sh 2>/dev/null", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 手动执行 openclash.sh
    log.write("\n=== 执行 openclash.sh ===\n")
    stdin, stdout, stderr = client.exec_command("cd /usr/share/openclash && bash openclash.sh 2>&1 | head -30", timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(f"OUT: {out}\n")

    # 检查生成的配置文件
    log.write("\n=== 检查生成配置 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /etc/openclash/config.yaml 2>/dev/null || echo 'not generated'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

client.close()
print("done")
