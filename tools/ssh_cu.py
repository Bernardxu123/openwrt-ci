#!/usr/bin/env python3
"""Run commands on the CU experiment router (ponwrt + dae) via SSH (paramiko).

Usage:
    python tools/ssh_cu.py "cmd1" "cmd2" ...
    python tools/ssh_cu.py -f script.sh          # run a local script on the router
    set CU_HOST / CU_PASSWORD env vars to override.

Default host: 192.168.1.1 (CU experiment machine). NEVER point this at 192.168.31.1 (production CT).
"""
import os
import sys

import paramiko

HOST = os.environ.get("CU_HOST", "192.168.1.1")
USER = os.environ.get("CU_USER", "root")
PASSWORD = os.environ.get("CU_PASSWORD", "Qazswxdecf1")


def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    print(f"$ {cmd}")
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err:
        print("[stderr]", err, end="" if err.endswith("\n") else "\n")
    if code:
        print(f"[exit {code}]")
    return code


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    if args[0] == "-f":
        with open(args[1], "r", encoding="utf-8") as fh:
            cmds = [fh.read()]
    else:
        cmds = args
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD,
                   look_for_keys=False, allow_agent=False, timeout=15)
    try:
        for cmd in cmds:
            run(client, cmd)
    finally:
        client.close()


if __name__ == "__main__":
    main()
