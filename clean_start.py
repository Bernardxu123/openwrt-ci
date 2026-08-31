import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/clean_start.txt", "w", encoding="utf-8") as log:

    # 清理锁文件和残留进程
    log.write("=== 清理锁文件 ===\n")
    stdin, stdout, stderr = client.exec_command("rm -f /tmp/openclash_* /tmp/clash_* 2>/dev/null; killall -9 clash mihomo 2>/dev/null; echo 'cleaned'", timeout=30)
    stdout.read()
    log.write("OK\n")

    # 直接通过 init.d 启动
    log.write("\n=== 通过 init.d 启动 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash start", timeout=60)
    stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    log.write(f"OK\n" if not err else f"ERR: {err}\n")

    import time
    time.sleep(5)

    # 检查进程
    log.write("\n=== 进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo|openclash_watch' | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

    # 检查 init 状态
    log.write("\n=== init 状态 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无输出\n")

    # 检查日志
    log.write("\n=== 日志 ===\n")
    stdin, stdout, stderr = client.exec_command("cat /tmp/openclash_start.log 2>/dev/null | tail -20", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无日志\n")

client.close()
print("done")
