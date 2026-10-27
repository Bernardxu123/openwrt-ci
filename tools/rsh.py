#!/usr/bin/env python3
"""Run a shell script on the router via SSH.

Usage:
    python tools/rsh.py <script.sh>          # run local script file
    python tools/rsh.py -                    # read script from stdin
    python tools/rsh.py -c "shell command"   # run a one-liner

The script is uploaded to /tmp/rsh-<pid>.sh and executed with `sh`. Output is
streamed back verbatim. Avoids all local shell quoting problems.
"""
import base64
import hashlib
import os
import sys

import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def run(script: str, timeout: int = 180) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=USER,
        password=PASSWORD,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
    )
    try:
        tag = hashlib.sha1(script.encode("utf-8")).hexdigest()[:12]
        path = f"/tmp/rsh-{tag}.sh"
        # The router has no SFTP subsystem and no base64 applet: ship the script
        # over exec stdin and half-close the channel so `cat` sees EOF.
        chan = client.get_transport().open_session()
        chan.settimeout(timeout)
        chan.exec_command(f"cat > {path} && chmod 755 {path}")
        chan.sendall(script.encode("utf-8"))
        chan.shutdown_write()
        chan.recv_exit_status()
        chan = client.get_transport().open_session()
        chan.settimeout(timeout)
        chan.exec_command(f"sh {path}; echo \"__EXIT=$?\"")
        out = []
        while True:
            if chan.recv_ready():
                data = chan.recv(65536)
                if not data:
                    break
                out.append(data.decode("utf-8", "replace"))
            elif chan.recv_stderr_ready():
                data = chan.recv_stderr(65536)
                if data:
                    out.append(data.decode("utf-8", "replace"))
            elif chan.exit_status_ready():
                while chan.recv_ready():
                    out.append(chan.recv(65536).decode("utf-8", "replace"))
                break
            else:
                import time

                time.sleep(0.05)
        text = "".join(out)
        sys.stdout.write(text)
        return 0
    finally:
        client.close()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    arg = sys.argv[1]
    if arg == "-":
        script = sys.stdin.read()
    elif arg == "-c":
        script = sys.argv[2]
    else:
        with open(arg, encoding="utf-8") as fh:
            script = fh.read()
    if not script.strip():
        print("empty script", file=sys.stderr)
        return 2
    return run(script)


if __name__ == "__main__":
    sys.exit(main())
