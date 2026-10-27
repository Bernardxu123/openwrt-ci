#!/usr/bin/env python3
"""
烽火 HG5585F Telnet 多命令会话。自动跟随提示符切换（$ → Config\\factorydir# → ...）。

用法:
  python tools/ont_shell.py --cmds "load_cli factory" "show admin_pwd"
  python tools/ont_shell.py --file cmds.txt
  python tools/ont_shell.py --get /dev/mtd13 --out factory_mtd13.bin   # 二进制回传
"""
import argparse
import re
import socket
import sys
import time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA, OPT_TTYPE = 1, 3, 24
PROMPT = re.compile(r"^[^\r\n]{0,40}[#>$]\s*$", re.M)


class Shell:
    def __init__(self, host, port=23, user="admin", password="Fh@163280", timeout=8):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""
        self.host, self.user, self.password = host, user, password

    def _negotiate(self):
        out = b""
        while IAC in self.buf:
            i = self.buf.index(IAC)
            if i + 2 >= len(self.buf):
                break
            cmd, opt = self.buf[i + 1], self.buf[i + 2]
            if cmd == DO:
                self.s.sendall(bytes([IAC, WILL, OPT_TTYPE] if opt == OPT_TTYPE else [IAC, WONT, opt]))
                self.buf = self.buf[:i] + self.buf[i + 3:]
            elif cmd == WILL:
                self.s.sendall(bytes([IAC, DO, opt] if opt in (OPT_ECHO, OPT_SGA) else [IAC, DONT, opt]))
                self.buf = self.buf[:i] + self.buf[i + 3:]
            elif cmd in (DONT, WONT):
                self.buf = self.buf[:i] + self.buf[i + 2:]
            elif cmd == SB:
                j = self.buf.find(bytes([IAC, SE]), i)
                if j == -1:
                    break
                self.buf = self.buf[:i] + self.buf[j + 2:]
            elif cmd == IAC:
                out += self.buf[:i + 1]
                self.buf = self.buf[i + 1:]
            else:
                self.buf = self.buf[:i] + self.buf[i + 2:]
        out += self.buf
        self.buf = b""
        return out

    def pump(self, seconds):
        acc = b""
        end = time.time() + seconds
        while time.time() < end:
            if not self.buf:
                self.s.settimeout(max(0.2, end - time.time()))
                try:
                    c = self.s.recv(8192)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not c:
                    break
                self.buf += c
            t = self._negotiate()
            if t:
                acc += t
        return acc.decode("latin-1", "replace")

    def wait_prompt(self, maxwait=8.0):
        acc = ""
        end = time.time() + maxwait
        while time.time() < end:
            acc += self.pump(0.5)
            if PROMPT.search(acc.split("\n")[-1] if acc.split("\n") else ""):
                m = PROMPT.search(acc)
                if m:
                    return acc
            if PROMPT.search(acc):
                return acc
        return acc

    def login(self):
        self.pump(1.5)
        self.send(self.user)
        self.pump(1.0)
        self.send(self.password)
        self.wait_prompt(8)

    def send(self, s, newline="\r\n"):
        self.s.sendall((s + newline).encode("latin-1", "replace"))

    def run(self, cmd, maxwait=8.0):
        self.send(cmd)
        time.sleep(0.5)
        out = self.wait_prompt(maxwait)
        lines = out.replace("\r\n", "\n").split("\n")
        # 去掉回显的命令行与最后的提示符
        if lines and cmd[:12] in lines[0]:
            lines = lines[1:]
        while lines and PROMPT.match(lines[-1] or ""):
            lines.pop()
        return "\n".join(lines).strip("\n")

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.1.1")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="Fh@163280")
    ap.add_argument("--cmds", nargs="*", default=[])
    ap.add_argument("--file")
    ap.add_argument("--wait", type=float, default=8.0)
    a = ap.parse_args()

    cmds = a.cmds
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            cmds = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]

    sh = Shell(a.host, user=a.user, password=a.password)
    try:
        sh.login()
        for c in cmds:
            print(f"\n$ {c}")
            print("-" * 4)
            print(sh.run(c, a.wait))
    finally:
        sh.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())