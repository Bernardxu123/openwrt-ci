#!/usr/bin/env python3
"""Run commands on the OpenWrt router via SSH (paramiko) and print output."""
import sys
import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds = sys.argv[1:]
    if not cmds:
        cmds = [sys.stdin.read()]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=10)
    try:
        for cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            print(f"$ {cmd}")
            if out:
                print(out, end="" if out.endswith("\n") else "\n")
            if err:
                print("[stderr]", err, end="" if err.endswith("\n") else "\n")
    finally:
        client.close()


if __name__ == "__main__":
    main()
