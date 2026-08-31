import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/fix_enable.txt", "w", encoding="utf-8") as log:

    # 1. 启用 OpenClash
    log.write("=== 启用 OpenClash ===\n")
    stdin, stdout, stderr = client.exec_command("uci set openclash.config.enable='1' && uci commit openclash", timeout=30)
    stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    log.write(f"OK\n" if not err else f"ERR: {err}\n")

    # 2. 启动 OpenClash
    log.write("\n=== 启动 OpenClash ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash start 2>&1", timeout=60)
    stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    log.write(f"OK\n" if not err else f"ERR: {err}\n")

    time.sleep(6)

    # 3. 检查进程
    log.write("\n=== 进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

    # 4. 检查端口
    log.write("\n=== 端口 ===\n")
    stdin, stdout, stderr = client.exec_command("netstat -tlnp 2>/dev/null | grep -E '7890|7891|7892|7893|7874'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无监听\n")

    # 5. 检查 init 状态
    log.write("\n=== init 状态 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无输出\n")

client.close()
print("done")
