#!/usr/bin/env python3
"""Byte-exact pull of router files (SFTP if available, else SSH `cat`).

The router's dropbear has no sftp-server, so the default path is
`exec_command("cat <remote>")` and we write the raw bytes locally.

Usage:
  python tools/router_sftp_pull.py <remote> <local> [<remote> <local> ...]

Prints sha256 + size of each local file so callers can compare with `sha256sum` on the router.
"""
import hashlib
import os
import shlex
import sys

import paramiko

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ssh_run  # noqa: E402  (provides HOST/USER/PASSWORD)


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def fetch(client: paramiko.SSHClient, remote: str) -> bytes:
    stdin, stdout, stderr = client.exec_command(f"cat {shlex.quote(remote)}", timeout=60)
    blob = stdout.read()
    err = stderr.read().decode("utf-8", "replace").strip()
    status = stdout.channel.recv_exit_status()
    if status != 0:
        raise SystemExit(f"cat failed ({status}) for {remote}: {err}")
    return blob


def main() -> int:
    args = sys.argv[1:]
    if not args or len(args) % 2:
        print(__doc__)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        ssh_run.HOST,
        username=ssh_run.USER,
        password=ssh_run.PASSWORD,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    try:
        for i in range(0, len(args), 2):
            remote, local = args[i], args[i + 1]
            blob = fetch(client, remote)
            os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
            with open(local, "wb") as f:
                f.write(blob)
            print(f"{sha256_bytes(blob)}  {len(blob):>7}  {local}  <-  {remote}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
