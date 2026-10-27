#!/usr/bin/env python3
"""Fetch /tmp/cpusample/* from the router into a local dir for archival."""
import os
import sys
import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"

files = ["meta.txt", "procstat.raw", "net.raw", "interrupts.raw", "interrupts.end", "top.snap", "procstat.end"]

outdir = sys.argv[1]
os.makedirs(outdir, exist_ok=True)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)
for name in files:
    stdin, stdout, stderr = c.exec_command(f"cat /tmp/cpusample/{name} 2>/dev/null", timeout=60)
    data = stdout.read()
    stdout.channel.recv_exit_status()
    with open(os.path.join(outdir, name), "wb") as f:
        f.write(data)
    print(f"{name}: {len(data)} bytes")
c.close()
