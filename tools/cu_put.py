#!/usr/bin/env python3
"""File put/get for the CU experiment router via SSH exec (raw stream).

This firmware has no SFTP subsystem and no base64 applet, so files are streamed
raw through the SSH channel.

Usage:
    python tools/cu_put.py put  local_path  remote_path
    python tools/cu_put.py get  remote_path local_path
"""
import os
import shlex
import sys

import paramiko

HOST = os.environ.get("CU_HOST", "192.168.1.1")
USER = os.environ.get("CU_USER", "root")
PWD = os.environ.get("CU_PASSWORD", "Qazswxdecf1")


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PWD, look_for_keys=False,
                   allow_agent=False, timeout=15)
    return client


def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("put", "get"):
        print(__doc__)
        sys.exit(2)
    action, a, b = sys.argv[1:4]
    client = connect()
    try:
        if action == "put":
            with open(a, "rb") as fh:
                data = fh.read()
            parent = os.path.dirname(b)
            if parent:
                code, out, err = run(client, "mkdir -p " + shlex.quote(parent))
                if code:
                    raise SystemExit(f"mkdir failed: {err}")
            # stream raw bytes into the remote file
            stdin, stdout, stderr = client.exec_command("cat > " + shlex.quote(b), timeout=60)
            stdin.write(data)
            stdin.flush()
            stdin.channel.shutdown_write()
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            if code:
                raise SystemExit(f"write failed ({code}): {err}")
            rsize = run(client, "wc -c < " + shlex.quote(b))[1].strip()
            print(f"put {a} -> {b} ({len(data)} bytes local, {rsize} remote)")
        else:
            code, out, err = run(client, "cat " + shlex.quote(a))
            if code:
                raise SystemExit(f"read failed ({code}): {err}")
            with open(b, "wb") as fh:
                fh.write(out.encode("utf-8", "replace"))
            print(f"get {a} -> {b}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
