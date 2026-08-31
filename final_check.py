import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

with open("D:/AI/路由/final_check.txt", "w", encoding="utf-8") as log:

    # 检查当前状态
    log.write("=== 进程 ===\n")
    stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无进程\n")

    log.write("\n=== init 状态 ===\n")
    stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash status", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "inactive\n")

    log.write("\n=== enable 配置 ===\n")
    stdin, stdout, stderr = client.exec_command("uci get openclash.config.enable", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(f"enable={out}\n")

    log.write("\n=== 端口 ===\n")
    stdin, stdout, stderr = client.exec_command("netstat -tlnp 2>/dev/null | grep -E '7890|7891|7892|7893|7874'", timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    log.write(out if out else "无监听\n")

    # 如果没进程，尝试启动
    if not out or "无进程" in out:
        log.write("\n=== 尝试启动 ===\n")
        stdin, stdout, stderr = client.exec_command("/etc/init.d/openclash start 2>&1", timeout=60)
        stdout.read()
        err = stderr.read().decode("utf-8", errors="replace")
        log.write(f"start: {err if err else 'OK'}\n")
        time.sleep(5)

        log.write("\n=== 启动后进程 ===\n")
        stdin, stdout, stderr = client.exec_command("ps | grep -E 'clash|mihomo' | grep -v grep", timeout=30)
        out = stdout.read().decode("utf-8", errors="replace")
        log.write(out if out else "无进程\n")

client.close()
print("done")
