import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/nss_update.txt", "w", encoding="utf-8") as log:

    # 检查是否有 nss-firmware 包可更新
    log.write("=== opkg 搜索 nss-firmware ===\n")
    stdin, stdout, stderr = client.exec_command("opkg list | grep -i nss | head -10", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无 nss 包\n")

    # 检查 nss 相关包
    log.write("\n=== opkg list-installed nss ===\n")
    stdin, stdout, stderr = client.exec_command("opkg list-installed | grep -i nss | head -10", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无已安装 nss 包\n")

    # 搜索 nss-firmware
    log.write("\n=== 搜索 nss-firmware ===\n")
    stdin, stdout, stderr = client.exec_command("opkg list | grep -i 'nss-firmware\\|nss_drv\\|qca-nss' | head -10", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "未找到\n")

    # 检查固件文件
    log.write("\n=== /lib/firmware 中的 nss 文件 ===\n")
    stdin, stdout, stderr = client.exec_command("ls -la /lib/firmware/qca-nss* 2>/dev/null || ls -la /lib/firmware/qcom/nss* 2>/dev/null || echo 'not found'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 dmesg nss 版本
    log.write("\n=== dmesg NSS 版本 ===\n")
    stdin, stdout, stderr = client.exec_command("dmesg | grep -i 'nss.*version\\|nss.*fw' | head -5", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无版本信息\n")

client.close()
print("done")
