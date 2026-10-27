#!/usr/bin/env python3
"""
烽火 HG5585F Telnet 客户端：做 IAC 协商、试登录、可选执行只读命令。
默认只尝试登录并打印提示符，不发送任何写命令。

用法:
  python tools/ont_telnet.py                       # 试一组常见口令组合
  python tools/ont_telnet.py --cmd "cfg_cmd get X" # 登录后执行只读命令
  python tools/ont_telnet.py --user X --pass Y
"""
import argparse
import re
import socket
import sys
import time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA, OPT_TTYPE, OPT_NAWS, OPT_LINEMODE = 1, 3, 24, 31, 34


class Telnet:
    def __init__(self, host, port=23, timeout=6):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""

    def _negotiate(self):
        """吃掉协商字节，只回必要的 WILL/WONT。返回累积的文本。"""
        out = b""
        while IAC in self.buf:
            i = self.buf.index(IAC)
            if i + 2 >= len(self.buf):
                break
            cmd = self.buf[i + 1]
            opt = self.buf[i + 2]
            if cmd == DO:
                if opt == OPT_TTYPE:
                    self.sock.sendall(bytes([IAC, WILL, OPT_TTYPE]))
                else:
                    self.sock.sendall(bytes([IAC, WONT, opt]))
                self.buf = self.buf[:i] + self.buf[i + 3:]
            elif cmd == WILL:
                if opt in (OPT_ECHO, OPT_SGA):
                    self.sock.sendall(bytes([IAC, DO, opt]))
                else:
                    self.sock.sendall(bytes([IAC, DONT, opt]))
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

    def read_until(self, patterns, maxwait=6.0):
        rx = re.compile("|".join(patterns), re.I)
        end = time.time() + maxwait
        acc = b""
        while time.time() < end:
            if not self.buf:
                try:
                    self.sock.settimeout(max(0.3, end - time.time()))
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                self.buf += chunk
            text = self._negotiate()
            if text:
                acc += text
            m = rx.search(acc.decode("latin-1", "replace"))
            if m:
                return acc.decode("latin-1", "replace"), m.lastgroup
        return acc.decode("latin-1", "replace"), None

    def send(self, s):
        self.sock.sendall((s + "\r\n").encode("latin-1", "replace"))
        time.sleep(0.4)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def try_login(host, user, password, cmd=None):
    t = Telnet(host)
    try:
        txt, _ = t.read_until([r"[Nn]ame\\s*[:：]?", r"[Pp]assword", r"[Uu]ser", r"login"], 6)
        t.send(user)
        txt2, _ = t.read_until([r"[Pp]assword", r"[Pp]ass"], 6)
        if not re.search(r"[Pp]assword|[Pp]ass", txt2):
            return False, "未出现 Password 提示", txt + txt2
        t.send(password)
        txt3, _ = t.read_until([r"[#$>]\s*$", r"[Pp]assword", r"[Ll]ogin", r"[Ii]nvalid", r"[Ee]rror"], 8)
        full = txt + txt2 + txt3
        if re.search(r"[Pp]assword", txt3):
            return False, "口令被拒", full
        if re.search(r"[#$>]\s*$", txt3, re.M):
            res = f"登录成功，提示符 {re.findall(r'[#$>]\s*$', txt3, re.M)[-1].strip()!r}"
            if cmd:
                t.send(cmd)
                out, _ = t.read_until([r"[#$>]\s*$"], 10)
                return True, res, full + out
            return True, res, full
        return False, "无 shell 提示符", full
    finally:
        t.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.1.1")
    ap.add_argument("--user", dest="username")
    ap.add_argument("--pass", dest="password")
    ap.add_argument("--cmd")
    a = ap.parse_args()

    if a.username and a.password:
        combos = [(a.username, a.password)]
    else:
        tail = ["163280", "163281"]           # MAC 末六位；末位 0 → +1 的已知约定
        combos = [(u, p) for u in ("telnetadmin", "admin", "root")
                  for p in ("Fh@" + tail[0], "Fh@" + tail[1], "FH" + tail[0], "fh" + tail[1])]

    for user, pw in combos:
        print(f"\n>>> 试 {user} / {pw}")
        try:
            ok, msg, full = try_login(a.host, user, pw, a.cmd)
        except Exception as e:
            print(f"    异常 {type(e).__name__}: {e}")
            continue
        print(f"    {msg}")
        if ok:
            print("    --- 会话片段 ---")
            print("    " + full.replace("\r\n", "\n    ")[-1200:])
            if not a.cmd:
                print("\n[提示] 加 --cmd \"<只读命令>\" 可执行，例如 --cmd \"cfg_cmd get InternetGatewayDevice.DeviceInfo.X_CT-COM_ServiceManage.TelnetEnable\"")
            return 0
    print("\n全部组合失败")
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())