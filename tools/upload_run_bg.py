#!/usr/bin/env python3
"""Upload a shell script to the router via stdin (no SFTP), run it in background (nohup)."""
import sys
import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"


def main():
    local = sys.argv[1]
    remote = sys.argv[2]
    dur = sys.argv[3] if len(sys.argv) > 3 else "125"
    with open(local, "rb") as f:
        data = f.read()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)

    # 1) write file via cat > remote  (stdin)
    stdin, stdout, stderr = c.exec_command(f"cat > {remote}", timeout=30)
    stdin.write(data)
    stdin.channel.shutdown_write()
    stdout.read()
    e = stderr.read().decode("utf-8", "replace")
    if e:
        print("[stderr-write]", e)

    # 2) chmod + launch detached
    cmd = f"chmod +x {remote}; rm -rf /tmp/cpusample; nohup sh {remote} /tmp/cpusample {dur} > /tmp/cpusample.log 2>&1 & echo STARTED; sleep 2; ls -la /tmp/cpusample"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
    print(stdout.read().decode("utf-8", "replace"))
    e = stderr.read().decode("utf-8", "replace")
    if e:
        print("[stderr]", e)
    c.close()


if __name__ == "__main__":
    main()
