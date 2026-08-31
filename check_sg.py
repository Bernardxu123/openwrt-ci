import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

# 检查当前配置中的 proxy-groups
stdin, stdout, stderr = client.exec_command("grep -B1 -A3 '新加坡' /etc/openclash/config/6-15-solo.yaml", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")

with open("D:/AI/路由/groups_check.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("done")
client.close()
