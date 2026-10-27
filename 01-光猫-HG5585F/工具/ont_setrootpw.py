#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给光猫设置 / 还原 root 口令 —— 为「串口 getty 登录拿到 root」铺路。

为什么需要这个
--------------
telnetd 认的是 /var/tel_passwd（烽火私有格式 + 额外校验），改它 root 登不进去；
但 **串口 getty 走标准 busybox login，读 /etc/passwd + /etc/shadow**，
而 /etc/shadow 是指向 /tmp/shadow 的符号链接，/tmp 是 777 且无 sticky 位
→ 用 `mv -f` 做 rename() 就能整体替换（这条已实测可行，telnetd 拒的是它自己那套）。

已实测前提
----------
  /proc/sys/kernel/osrelease = 5.4.55      → stock2ubi 版本校验会过
  /proc/consoles = ttyS0 -W-              → 串口有 getty，可登录

⚠️ 三条硬约束
------------
  * /tmp 是 tmpfs，**光猫一重启就恢复原值** → 必须在同一次开机内完成
    「改口令 → 串口登录 root → 跑 stock2ubi 备份+刷引导」这一整串。
  * 本脚本会改动光猫认证配置；`--restore` 才还原。
  * 会先备份：设备侧 /tmp/shadow.ontbak + 本地 downloads/shadow.ontbak

用法
----
    python 光猫-HG5585F/tools/ont_setrootpw.py --status
    python 光猫-HG5585F/tools/ont_setrootpw.py --set
    python 光猫-HG5585F/tools/ont_setrootpw.py --set --password '你的口令'
    python 光猫-HG5585F/tools/ont_setrootpw.py --restore
"""
import argparse
import os
import re
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BAK_DIR = os.path.join(ROOT, "downloads")

ONT_IP = "192.168.1.1"
ONT_USER, ONT_PASS = "admin", "Fh@163280"

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA, OPT_TTYPE = 1, 3, 24
PROMPT = re.compile(r"^[^\r\n]{0,40}[#>$]\s*$", re.M)


# ----------------------------------------------------------------- telnet
class Shell:
    def __init__(self, host, port=23, user=ONT_USER, password=ONT_PASS, timeout=8):
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
        self.send(ONT_USER); self.pump(1.0)
        self.send(ONT_PASS)
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
    """给 sed 替换串转义（只对 & 和分隔符 | 有意义；这里只防 &）。"""
    return s.replace("&", r"\&")


# ----------------------------------------------------------------- 主流程
def status(sh):
    out = sh.run("cat /etc/shadow")
    root = next((l for l in out.splitlines() if l.startswith("root:")), "")
    hashv = root.split(":")[1] if ":" in root else ""
    algo = hashv.split("$")[1] if hashv.startswith("$") and len(hashv.split("$")) > 1 else "?"
    salt = hashv.split("$")[2] if len(hashv.split("$")) > 2 else ""
    bak = sh.run("ls -l /tmp/shadow.ontbak 2>&1")
    have_bak = ("No such file" not in bak) and ("shadow.ontbak" in bak)
    print("  /etc/shadow root 条目：%s" % (root[:70] + ("..." if len(root) > 70 else "")))
    print("  算法 = $%s$   salt = %s" % (algo, salt))
    print("  设备备份 /tmp/shadow.ontbak：%s" % ("存在" if have_bak else "无"))
    return root, hashv


def do_set(sh, password):
    root_line, hashv = status(sh)
    if not root_line:
        print("  [错误] 读不到 /etc/shadow 的 root 条行"); return 1
    parts = hashv.split("$")
    if len(parts) < 3:
        print("  [错误] root 哈希不是 crypt 格式：%s" % hashv); return 1
    algo, salt = parts[1], parts[2]
    if "$" in salt:
        print("  [错误] salt 含 $，脚本的 shell 传参会炸，停止"); return 1

    print("\n== 2) 备份原 shadow ==")
    sh.run("cat /etc/shadow > /tmp/shadow.ontbak")
    os.makedirs(BAK_DIR, exist_ok=True)
    local = os.path.join(BAK_DIR, "shadow.ontbak")
    with open(local, "w", encoding="utf-8", newline="\n") as f:
        f.write(sh.run("cat /etc/shadow") + "\n")
    print("  设备: /tmp/shadow.ontbak    本地: %s" % local)

    print("\n== 3) 用设备自带 openssl 生成同 salt 哈希 ==")
    qp = "'" + password.replace("'", "") + "'"
    hs = sh.run("/fhrom/bin/openssl passwd -%s -salt '%s' %s" % (algo, salt, qp))
    newhash = hs.strip().splitlines()[-1].strip() if hs.strip() else ""
    if not newhash.startswith("$" + algo + "$"):
        print("  [错误] openssl 没返回合法哈希：%r" % hs[:200]); return 1
    print("  新哈希 = %s..." % newhash[:46])

    print("\n== 4) 替换 /tmp/shadow（走 mv -f rename 覆盖）==")
    sh.run("cat /etc/shadow | sed 's|^root:[^:]*:|root:%s:|' > /tmp/shadow.new" % q(newhash))
    sh.run("mv -f /tmp/shadow.new /tmp/shadow")
    now = next((l for l in sh.run("cat /etc/shadow").splitlines() if l.startswith("root:")), "")
    if newhash not in now:
        print("  [失败] 替换后校验不通过"); return 1
    print("  校验通过 ✓")

    print("\n== 5) 确认前提 ==")
    print("  osrelease : %s" % sh.run("cat /proc/sys/kernel/osrelease"))
    print("  consoles  : %s" % sh.run("cat /proc/consoles"))
    print("  shell     : %s" % sh.run("cat /etc/passwd | grep ^root:"))

    print("\n" + "=" * 62)
    print("  现在可以接 TTL 串口线，用 root / %s 登录串口 getty 了。" % password)
    print("  ⚠️ /tmp 是 tmpfs，光猫一重启本设置就消失 —— 全部做完前不要重启。")
    print("=" * 62)
    return 0


def do_restore(sh):
    bak = sh.run("cat /tmp/shadow.ontbak 2>&1")
    if "No such file" in bak or not bak.strip():
        print("  [错误] 设备上没有 /tmp/shadow.ontbak，无法还原"); return 1
    sh.run("cat /tmp/shadow.ontbak > /tmp/shadow.r")
    sh.run("mv -f /tmp/shadow.r /tmp/shadow")
    root_line = next((l for l in sh.run("cat /etc/shadow").splitlines() if l.startswith("root:")), "")
    print("  已还原。当前 root 条目：%s..." % root_line[:60])
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", action="store_true")
    g.add_argument("--restore", action="store_true")
    g.add_argument("--status", action="store_true")
    ap.add_argument("--password", default="Fh@163280")
    a = ap.parse_args()

    print("== 0) 连光猫 telnet（%s）==" % ONT_IP)
    sh = Shell(ONT_IP)
    try:
        if not sh.login():
            print("  [错误] telnet 登录失败。先确认访问通道：python tools/ont.py on")
            return 1
        print("  ok\n")
        if a.status:
            status(sh); return 0
        if a.set:
            return do_set(sh, a.password)
        return do_restore(sh)
    finally:
        sh.close()


if __name__ == "__main__":
    os.system("chcp 65001 > nul")
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())