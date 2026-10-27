#!/usr/bin/env python3
"""Fetch one file from the router over SSH (dropbear has no sftp-server, so
the file is base64-streamed over an exec channel).

Usage: python tools/router_sftp_get.py <remote_path> <local_path>
"""
import base64
import sys

import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    remote, local = sys.argv[1], sys.argv[2]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD,
                   look_for_keys=False, allow_agent=False, timeout=10)
    try:
        _, stdout, stderr = client.exec_command(
            f"openssl base64 -in {remote}", timeout=120)
        payload = base64.b64decode(stdout.read())
        err = stderr.read().decode("utf-8", "replace").strip()
        if err:
            print(f"[remote stderr] {err}", file=sys.stderr)
        with open(local, "wb") as fh:
            fh.write(payload)
        print(f"OK {remote} -> {local} ({len(payload)} bytes)")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
