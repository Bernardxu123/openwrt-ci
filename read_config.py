import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

stdin, stdout, stderr = client.exec_command("cat /etc/openclash/config/6-15-solo.yaml", timeout=30)
out = stdout.read().decode("utf-8", errors="replace")

with open("D:/AI/路由/6-15-solo.yaml", "w", encoding="utf-8") as f:
    f.write(out)

print(f"saved {len(out)} chars")
client.close()
