#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 HG5585F-CT（原厂系统）设置/还原 /tmp/shadow 的 root 口令，
为「TTL 串口 getty 用 root 登录」铺路。

原理
----
telnetd 认的是烽火私有的 /var/tel_passwd（还有额外校验），改它 root 登不进去；
但串口 getty 走标准 busybox login，只读 /etc/passwd + /etc/shadow。
/etc/shadow 是指向 /tmp/shadow 的符号链接，/tmp 是 777 且无 sticky 位
→ 用 `mv -f` 的 rename() 可以整体替换 root 拥有的文件。

前提（CU 机实测，CT 待验证）
--------------------------
  /proc/sys/kernel/osrelease = 5.4.55   （stock2ubi 版本校验会过）
  /proc/consoles = ttyS0 -W-           （串口有 getty，可登录）
  telnet 可达，且能用 admin / Fh@… 登录到 opuser 受限 shell

⚠️ /tmp 是 tmpfs，**一重启就还原** → 「改口令 → 串口登录 root → 跑 stock2ubi」
   必须在同一次开机内完成。

用法
----
    python ont-setrootpw-ct.py --ip 192.168.1.1 --user admin --pass "Fh@123456" --status
    python ont-setrootpw-ct.py --ip 192.168.1.1 --user admin --pass "Fh@123456" --set --root-password "Ct@Test2026"
    python ont-setrootpw-ct.py --ip 192.168.1.1 --user admin --pass "Fh@123456" --restore
"""
import argparse
import os
import re
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BAK_DIR = os.path.join(ROOT, "备份", "shadow")

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA, OPT_TTYPE = 1, 3, 24
PROMPT = re.compile(r"^[^\r\n]{0,40}[#>$]\s*$", re.M)


class Shell:
    def __init__(self, host, user, password, port=23, timeout=8):
        self.user = user
        self.password = password
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""

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
        return acc.decode("latin-1", "replace")

    def send(self, s):
        self.s.sendall((s + "\r\n").encode("latin-1", "replace"))

    def login(self):
        self.pump(1.5)
        self.send(self.user)
        self.pump(1.0)
        self.send(self.password)
        t0 = time.time()
        while time.time() - t0 < 10:
            if PROMPT.search(self.pump(0.5)):
                return True
        return False

    def run(self, cmd, maxwait=15.0):
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

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def q(s):
    return s.replace("&", r"\&")


def status(sh):
    out = sh.run("cat /etc/shadow")
    root = next((l for l in out.splitlines() if l.startswith("root:")), "")
    hashv = root.split(":")[1] if ":" in root else ""
    parts = hashv.split("$")
    algo = parts[1] if len(parts) > 1 else "?"
    salt = parts[2] if len(parts) > 2 else ""
    bak = sh.run("ls -l /tmp/shadow.ontbak 2>&1")
    have_bak = ("No such file" not in bak) and ("shadow.ontbak" in bak)
    print("  root 条目：%s" % (root[:70] + ("..." if len(root) > 70 else "")))
    print("  算法 = $%s$   salt = %s" % (algo, salt))
    print("  设备备份 /tmp/shadow.ontbak：%s" % ("存在" if have_bak else "无"))
    return root, hashv


def find_openssl(sh):
    for p in ("/fhrom/bin/openssl", "openssl", "/usr/bin/openssl", "/bin/openssl"):
        out = sh.run("%s version 2>&1" % p, maxwait=8)
        if "OpenSSL" in out:
            print("  openssl: %s" % p)
            return p
    return None


def do_set(sh, password):
    print("== 1) 读取当前 root ==")
    root_line, hashv = status(sh)
    if not root_line:
        print("  [错误] 读不到 /etc/shadow 的 root 行")
        return 1
    parts = hashv.split("$")
    if len(parts) < 3:
        print("  [错误] root 哈希不是 crypt 格式：%s" % hashv)
        return 1
    algo, salt = parts[1], parts[2]
    if "$" in salt:
        print("  [错误] salt 含 $，shell 传参会炸，停止")
        return 1

    print("\n== 2) 备份原 shadow ==")
    sh.run("cat /etc/shadow > /tmp/shadow.ontbak")
    os.makedirs(BAK_DIR, exist_ok=True)
    local = os.path.join(BAK_DIR, "shadow.ontbak")
    with open(local, "w", encoding="utf-8", newline="\n") as f:
        f.write(sh.run("cat /etc/shadow") + "\n")
    print("  设备: /tmp/shadow.ontbak    本地: %s" % local)

    print("\n== 3) 生成同 salt 哈希 ==")
    openssl = find_openssl(sh)
    if not openssl:
        print("  [错误] 设备上找不到 openssl；改用本地 openssl 生成后再手动 sed（见 05 文档）")
        return 1
    qp = "'" + password.replace("'", "") + "'"
    hs = sh.run("%s passwd -%s -salt '%s' %s" % (openssl, algo, salt, qp))
    newhash = hs.strip().splitlines()[-1].strip() if hs.strip() else ""
    if not newhash.startswith("$" + algo + "$"):
        print("  [错误] openssl 没返回合法哈希：%r" % hs[:200])
        return 1
    print("  新哈希 = %s..." % newhash[:46])

    print("\n== 4) 替换 /tmp/shadow（mv -f rename 覆盖）==")
    sh.run("cat /etc/shadow | sed 's|^root:[^:]*:|root:%s:|' > /tmp/shadow.new" % q(newhash))
    sh.run("mv -f /tmp/shadow.new /tmp/shadow")
    now = next((l for l in sh.run("cat /etc/shadow").splitlines() if l.startswith("root:")), "")
    if newhash not in now:
        print("  [失败] 替换后校验不通过")
        return 1
    print("  校验通过 OK")

    print("\n== 5) 确认前提 ==")
    print("  osrelease : %s" % sh.run("cat /proc/sys/kernel/osrelease"))
    print("  consoles  : %s" % sh.run("cat /proc/consoles"))
    print("  root shell: %s" % sh.run("cat /etc/passwd | grep ^root:"))
    print("\n" + "=" * 60)
    print("  现在接 TTL 串口，用 root / %s 登录串口 getty。" % password)
    print("  /tmp 是 tmpfs：全部做完前不要重启！")
    print("=" * 60)
    return 0


def do_restore(sh):
    bak = sh.run("cat /tmp/shadow.ontbak 2>&1")
    if "No such file" in bak or not bak.strip():
        print("  [错误] 设备上没有 /tmp/shadow.ontbak，无法还原")
        return 1
    sh.run("cat /tmp/shadow.ontbak > /tmp/shadow.r")
    sh.run("mv -f /tmp/shadow.r /tmp/shadow")
    root_line = next((l for l in sh.run("cat /etc/shadow").splitlines() if l.startswith("root:")), "")
    print("  已还原。当前 root 条目：%s..." % root_line[:60])
    return 0


def main():
    ap = argparse.ArgumentParser(description="HG5585F-CT 改/还原 /tmp/shadow 的 root 口令")
    ap.add_argument("--ip", default="192.168.1.1")
    ap.add_argument("--user", default="admin", help="telnet 用户名")
    ap.add_argument("--pass", dest="telnet_password", default="", help="telnet 口令（Fh@ + MAC 后六位）")
    ap.add_argument("--port", type=int, default=23)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", action="store_true")
    g.add_argument("--restore", action="store_true")
    g.add_argument("--status", action="store_true")
    ap.add_argument("--root-password", default="Ct@Test2026", help="要设置的 root 新口令")
    a = ap.parse_args()

    if not a.telnet_password:
        print("[错误] 必须给 --pass（telnet 口令）", file=sys.stderr)
        return 2

    print("== 0) 连 %s:%d（user=%s）==" % (a.ip, a.port, a.user))
    try:
        sh = Shell(a.ip, a.user, a.telnet_password, a.port)
    except OSError as e:
        print("  [错误] 连接失败：%s" % e)
        return 1
    try:
        if not sh.login():
            print("  [错误] telnet 登录失败：核对口令 / 先开 Telnet（fhtool-ct.py --telnet-on）")
            return 1
        print("  ok\n")
        if a.status:
            status(sh)
            return 0
        if a.set:
            return do_set(sh, a.root_password)
        return do_restore(sh)
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
