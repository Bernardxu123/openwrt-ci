#!/usr/bin/env python3
"""Run shell commands on the Vidda TV (70V1F-S) via network ADB and print output.

用法（仿 ssh_run.py）:
    python tools/tv_adb.py "命令1" "命令2"
    echo 命令 | python tools/tv_adb.py
"""
import os
import subprocess
import sys

TV = "192.168.31.115:5555"
ADB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "platform-tools", "adb.exe")


def main():
    cmds = sys.argv[1:]
    if not cmds:
        cmds = [sys.stdin.read()]
    subprocess.run([ADB, "start-server"], capture_output=True)
    conn = subprocess.run([ADB, "connect", TV], capture_output=True, text=True)
    print(f"# {conn.stdout.strip()}")
    for cmd in cmds:
        try:
            r = subprocess.run([ADB, "-s", TV, "shell", cmd], capture_output=True, text=True, timeout=90)
            print(f"$ {cmd}")
            if r.stdout:
                print(r.stdout, end="" if r.stdout.endswith("\n") else "\n")
            if r.stderr:
                print("[stderr]", r.stderr, end="" if r.stderr.endswith("\n") else "\n")
        except subprocess.TimeoutExpired:
            print(f"$ {cmd}\n[timeout 90s]")


if __name__ == "__main__":
    main()
