import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/debug3.txt", "w", encoding="utf-8") as log:

    # 检查 init 脚本内容
    log.write("=== init 脚本前50行 ===\n")
    stdin, stdout, stderr = client.exec_command("head -50 /etc/init.d/openclash", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 start 函数
    log.write("\n=== start 函数 ===\n")
    stdin, stdout, stderr = client.exec_command("grep -A20 'start()' /etc/init.d/openclash | head -25", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 直接启动 clash
    log.write("\n=== 直接启动 clash ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/6-15-solo.yaml &", timeout=10)
    stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    log.write(f"err: {err}\n" if err else "started\n")

    import time
    time.sleep(3)

    # 检查进程
    log.write("\n=== 进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep clash | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

client.close()
print("done")
