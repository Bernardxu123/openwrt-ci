#!/usr/bin/env python3
"""Upload/download a file to/from the CT router (192.168.31.1) via raw SSH stream.

This firmware has no reliable SFTP subsystem; we stream bytes through the channel.

Usage:
    python tools/ct_put.py put  local_path  remote_path
    python tools/ct_put.py get  remote_path local_path
"""
import os
import shlex
import sys

import paramiko

HOST = os.environ.get("CT_HOST", "192.168.31.1")
USER = "root"
PWD = "Qazswxdecf1"


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("put", "get"):
        print(__doc__)
        return 2
    action, a, b = sys.argv[1:4]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PWD, look_for_keys=False,
                   allow_agent=False, timeout=15)
    try:
        if action == "put":
            size = os.path.getsize(a)
            stdin, stdout, stderr = client.exec_command("cat > " + shlex.quote(b), timeout=600)
            sent = 0
            with open(a, "rb") as fh:
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    stdin.write(chunk)
                    sent += len(chunk)
                    stdin.flush()
            stdin.channel.shutdown_write()
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            if code:
                raise SystemExit(f"put failed ({code}): {err}")
            sftp_p = client.exec_command(f"wc -c < {shlex.quote(b)}")[1].read().decode().strip()
            print(f"put {a} ({size} B) -> {b} (remote {sftp_p} B)")
        else:
            stdin, stdout, stderr = client.exec_command("cat " + shlex.quote(a), timeout=600)
            data = stdout.read()
            with open(b, "wb") as fh:
                fh.write(data)
            print(f"get {a} -> {b} ({len(data)} B)")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
