#!/usr/bin/env python3
"""SSH helper for the 新加坡自建 VPS (161.118.196.196:5522).

Credentials are parsed from 凭据.md (never hard-coded here).

Usage:
  python tools/vps_ssh.py exec "<shell command>" [more commands...]
  python tools/vps_ssh.py tunnel 290 [--bind 127.0.0.1] [--local-port 290]

`tunnel` starts a local port forward (default 290 -> VPS 127.0.0.1:290) and blocks
until Ctrl-C, which is how the 3x-ui panel is reachable (panel firewall is lo-only).
"""
import os
import re
import select
import socket
import sys
import threading

import paramiko

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED = os.path.join(ROOT, "凭据.md")

HOST = "161.118.196.196"
PORT = 5522
USER = "root"


def load_password() -> str:
    with open(CRED, "r", encoding="utf-8") as f:
        for line in f:
            if "VPS（甲骨文新加坡）" in line and "5522" in line:
                m = re.search(r"root\s*/\s*([^\s，,；;|]+)", line)
                if m:
                    return m.group(1)
    raise SystemExit("未在 凭据.md 中找到 VPS 密码")


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=load_password(),
        look_for_keys=False,
        allow_agent=False,
        timeout=20,
    )
    return client


def do_exec(cmds) -> int:
    client = connect()
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
    return 0


def do_forward(remote_port: int, bind: str, local_port: int) -> int:
    client = connect()
    transport = client.get_transport()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((bind, local_port))
    server.listen(20)
    print(f"tunnel: {bind}:{local_port} -> {HOST}:127.0.0.1:{remote_port} (Ctrl-C to stop)", flush=True)

    def handle(client_sock):
        try:
            chan = transport.open_channel(
                "direct-tcpip", ("127.0.0.1", remote_port), client_sock.getpeername()
            )
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"[tunnel] open_channel failed: {exc}", flush=True)
            client_sock.close()
            return
        if chan is None:
            client_sock.close()
            return
        while True:
            r, _, x = select.select([client_sock, chan], [], [client_sock, chan], 5)
            if client_sock in r:
                data = client_sock.recv(4096)
                if not data:
                    break
                chan.sendall(data)
            if chan in r:
                data = chan.recv(4096)
                if not data:
                    break
                client_sock.sendall(data)
            if x:
                break
        chan.close()
        client_sock.close()

    try:
        while True:
            sock, addr = server.accept()
            threading.Thread(target=handle, args=(sock,), daemon=True).start()
    except KeyboardInterrupt:
        print("stopping tunnel", flush=True)
    finally:
        server.close()
        client.close()
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    if mode == "exec":
        return do_exec(sys.argv[2:])
    if mode == "tunnel":
        remote_port = int(sys.argv[2]) if len(sys.argv) > 2 else 290
        bind = "127.0.0.1"
        local_port = remote_port
        rest = sys.argv[3:]
        if "--bind" in rest:
            bind = rest[rest.index("--bind") + 1]
        if "--local-port" in rest:
            local_port = int(rest[rest.index("--local-port") + 1])
        return do_forward(remote_port, bind, local_port)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
