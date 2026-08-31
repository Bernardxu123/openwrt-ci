import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/start_debug.txt", "w", encoding="utf-8") as log:

    # 手动执行 openclash.sh 看完整输出
    log.write("=== 执行 openclash.sh ===\n")
    stdin, stdout, stderr = client.exec_command("cd /usr/share/openclash && bash -x openclash.sh 2>&1 | head -50", timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(f"OUT: {out}\n")

    # 检查 TMP_CONFIG_FILE 是否生成
    log.write("\n=== 检查临时配置 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /etc/openclash/tmp_config.yaml 2>/dev/null || echo 'not generated'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 RAW_CONFIG_FILE
    log.write("\n=== RAW_CONFIG_FILE ===\n")
    stdin, stdout, stderr = client.exec_command("grep 'RAW_CONFIG_FILE' /usr/share/openclash/openclash.sh | head -5", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 config_choose 函数
    log.write("\n=== config_choose 函数 ===\n")
    stdin, stdout, stderr = client.exec_command("grep -A20 'config_choose()' /usr/share/openclash/openclash.sh | head -25", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 直接执行 start_service
    log.write("\n=== 直接执行 start_service ===\n")
    stdin, stdout, stderr = client.exec_command("bash -c '. /usr/share/openclash/openclash.sh; start_service' 2>&1 | head -30", timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(f"OUT: {out}\n")

client.close()
print("done")
