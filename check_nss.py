import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.31.1", username="root", password="Qazswxdecf1", timeout=10)

cmds = [
    "# NSS 驱动版本",
    "cat /sys/module/qca_nss_drv/version 2>/dev/null || echo 'not found'",
    "# NSS 内核模块信息",
    "modinfo qca_nss_drv 2>/dev/null | head -10",
    "# NSS 相关模块",
    "lsmod | grep nss | head -10",
    "# NSS offload 状态",
    "cat /sys/module/ath11k/parameters/nss_offload 2>/dev/null",
    "# NSS ECM 状态",
    "cat /sys/kernel/debug/ecm/ecm_db_count 2>/dev/null || echo 'ecm not available'",
    "# 检查 NSS 固件版本",
    "cat /sys/firmware/qcom/nss_fw_version 2>/dev/null || dmesg | grep -i nss | head -5",
]

for cmd in cmds:
    if cmd.startswith('#'):
        continue
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(f"\n=== {cmd} ===")
    if out:
        print(out)
    if err:
        print(f"ERR: {err}")

client.close()
