#!/usr/bin/env python3
"""Push a local file to the router over SSH by streaming it into `cat > remote`.

Dropbear has no sftp-server, so this uses an exec channel with stdin.
Usage: python tools/router_push.py <local_path> <remote_path> [mode]
"""
import sys

import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    local, remote = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "644"
    with open(local, "rb") as fh:
        payload = fh.read()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD,
                   look_for_keys=False, allow_agent=False, timeout=10)
    try:
        cmd = f"cat > {remote}.tmp && mv {remote}.tmp {remote} && chmod {mode} {remote} && wc -c < {remote}"
        stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        stdin.write(payload)
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", "replace").strip()
        err = stderr.read().decode("utf-8", "replace").strip()
        print(f"remote_bytes={out}")
        if err:
            print(f"[stderr] {err}", file=sys.stderr)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
