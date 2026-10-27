#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HG5585F-CT 原厂系统 · 通用 Telnet 命令执行器（用于只读采集 / 提权前检查）。

为什么不用 telnetlib：Python 3.13+ 已移除 telnetlib；本机是 3.14。
本脚本沿用项目里已验证的 IAC 协商 + busybox login 处理。

用法
----
    python ont-telnet-ct.py --user telnetadmin --password "xxx" --cmd "id"
    python ont-telnet-ct.py --user telnetadmin --password "xxx" \
        --cmd "cat /proc/self/status" --cmd "cat /proc/mtd"

安全：只发送你给的命令；不写设备、不下载、不扫描。
"""
import argparse
import os
import re
import socket
import sys
import time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA, OPT_TTYPE = 1, 3, 24
PROMPT = re.compile(r"^[^\r\n]{0,80}[#>$]\s*$", re.M)


class Shell:
    def __init__(self, host, user, password, port=23, timeout=8):
        self.user = user
        self.password = password
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""
        self.transcript = ""

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
        acc, end = b"", time.time() + seconds
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
        text = acc.decode("latin-1", "replace")
        self.transcript += text
        return text

    def send(self, s):
        self.s.sendall((s + "\r\n").encode("latin-1", "replace"))

    def login(self):
        self.pump(1.5)
        self.send(self.user)
        self.pump(1.0)
        self.send(self.password)
        t0 = time.time()
        while time.time() - t0 < 12:
            if PROMPT.search(self.pump(0.5)):
                return True
        return False

    def run(self, cmd, maxwait=20.0):
        self.send(cmd)
        time.sleep(0.4)
        acc, end = "", time.time() + maxwait
        while time.time() < end:
            acc += self.pump(0.5)
            if PROMPT.search(acc):
                break
        lines = acc.replace("\r\n", "\n").split("\n")
        if lines and cmd[:12] in lines[0]:
            lines = lines[1:]
        while lines and PROMPT.match(lines[-1] or ""):
            lines.pop()
        return "\n".join(lines).strip("\n")

    def do_su(self, password, wait=3.0):
        """发送 su、等 Password:、送口令，返回 (是否见到提示, 原始文本)。"""
        self.send("su")
        time.sleep(0.6)
        text = self.pump(wait)
        if "assword" not in text:
            return False, text
        self.send(password)
        time.sleep(0.8)
        text2 = self.pump(wait)
        return True, text + text2

    def do_passwd(self, new_password, wait=3.0):
        """交互执行 passwd，改当前用户口令。返回 (是否成功, 原始文本)。"""
        self.send("passwd")
        time.sleep(0.6)
        text = self.pump(wait)
        if "assword" not in text:
            return False, text
        self.send(new_password)
        time.sleep(0.5)
        text += self.pump(wait)
        if "etype" in text or "gain" in text:
            self.send(new_password)
            time.sleep(0.5)
            text += self.pump(wait)
        return "changed" in text.lower(), text

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="HG5585F-CT Telnet 命令执行器")
    ap.add_argument("--ip", default="192.168.1.1")
    ap.add_argument("--port", type=int, default=23)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--cmd", action="append", default=[], help="可重复；按顺序执行")
    ap.add_argument("--su-password", default="", help="登录后先执行 su，并用此口令提权")
    ap.add_argument("--new-password", default="", help="登录后交互执行 passwd，改当前用户口令")
    ap.add_argument("--raw", action="store_true", help="登录失败时打印全部原始输出")
    a = ap.parse_args()

    try:
        sh = Shell(a.ip, a.user, a.password, a.port)
    except OSError as e:
        print(f"[连接失败] {e}", file=sys.stderr)
        return 1
    try:
        if not sh.login():
            print(f"[登录失败] {a.user}@{a.ip}:{a.port}", file=sys.stderr)
            if a.raw:
                print("---- raw transcript ----")
                print(repr(sh.transcript))
                print("------------------------")
            return 1
        print(f"[登录成功] {a.user}@{a.ip}")
        if a.su_password:
            seen, text = sh.do_su(a.su_password)
            print("\n$ su")
            print(text.strip())
            if not seen:
                print("[警告] 没看到 Password: 提示，可能已经是 root 或 su 不可用")
        if a.new_password:
            ok, text = sh.do_passwd(a.new_password)
            print("\n$ passwd")
            print(text.strip())
            print(f"[改密] {'成功' if ok else '未确认成功'}")
        for cmd in a.cmd:
            print(f"\n$ {cmd}")
            print(sh.run(cmd))
        return 0
    finally:
        sh.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        os.system("chcp 65001 > nul")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
