import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/debug_out.txt", "w", encoding="utf-8") as log:

    # 检查配置文件
    log.write("=== 配置文件前15行 ===\n")
    stdin, stdout, stderr = client.exec_command("head -15 /etc/openclash/config/6-15-solo.yaml", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 proxy-groups 数量
    log.write("\n=== proxy-groups 名称 ===\n")
    stdin, stdout, stderr = client.exec_command("grep 'name:' /etc/openclash/config/6-15-solo.yaml", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 检查 DNS 配置
    log.write("\n=== DNS 配置 ===\n")
    stdin, stdout, stderr = client.exec_command("grep -A10 '^dns:' /etc/openclash/config/6-15-solo.yaml | head -15", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out + "\n")

    # 手动尝试启动
    log.write("\n=== 手动启动 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash start 2>&1", timeout=60)
    stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    log.write(f"err: {err}\n" if err else "OK\n")

    import time
    time.sleep(4)

    # 检查进程
    log.write("\n=== 启动后进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

    # 检查 init 状态
    log.write("\n=== init 状态 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status 2>&1", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无输出\n")

client.close()
print("done")
