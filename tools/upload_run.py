#!/usr/bin/env python3
"""Upload a shell script to the router via stdin (no SFTP) and run it in foreground."""
import sys
import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def main():
    local = sys.argv[1]
    remote = sys.argv[2]
    with open(local, "rb") as f:
        data = f.read()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)

    stdin, stdout, stderr = c.exec_command(f"cat > {remote}", timeout=30)
    stdin.write(data)
    stdin.channel.shutdown_write()
    stdout.read()
    stderr.read()

    stdin, stdout, stderr = c.exec_command(f"sh {remote}", timeout=120)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(out)
    if err:
        print("[stderr]", err)
    c.close()


if __name__ == "__main__":
    main()
