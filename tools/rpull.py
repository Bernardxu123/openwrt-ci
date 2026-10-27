#!/usr/bin/env python3
"""Pull a file from the router over SSH and save it locally."""
import sys

import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def main() -> int:
    remote, local = sys.argv[1], sys.argv[2]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)
    _, o, e = c.exec_command(f"cat {remote}")
    data = o.read()
    err = e.read().decode("utf-8", "replace")
    c.close()
    if err.strip():
        print("[stderr]", err.strip())
    with open(local, "wb") as fh:
        fh.write(data)
    print(f"{remote} -> {local} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
