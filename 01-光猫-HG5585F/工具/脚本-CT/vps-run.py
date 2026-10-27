#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 VPS 上跑一串命令（只读检查/编译用）。"""
import sys
import paramiko

HOST, PORT, USER, PWD = "161.118.196.196", 5522, "root", "Qazswxdecf1"
cmds = sys.argv[1:] or ["uname -m"]
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PWD, timeout=20)
for cmd in cmds:
    print(f"\n$ {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    if out:
        print(out.rstrip())
    if err:
        print("[stderr]", err.rstrip())
c.close()
