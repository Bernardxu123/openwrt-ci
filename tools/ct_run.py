#!/usr/bin/env python3
"""Run a local shell script on the production CT router (192.168.31.1) via SSH.

Usage: python tools/ct_run.py path/to/script.sh
The whole file content is sent as one remote command (script text).
"""
import os
import sys

import paramiko

HOST = os.environ.get("CT_HOST", "192.168.31.1")
USER = "root"
PWD = "Qazswxdecf1"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        cmd = fh.read()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PWD, look_for_keys=False,
                   allow_agent=False, timeout=15)
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print("[stderr]", err, end="" if err.endswith("\n") else "\n")
        print(f"[exit {code}]")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
