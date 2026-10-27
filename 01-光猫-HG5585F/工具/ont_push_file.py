#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给光猫送文件：PC  →  LibWrt(192.168.1.2)  →  光猫(192.168.1.1)

为什么不直接 PC→光猫：
  光猫侧在 192.168.1.0/24（桥接在路由器 wan 口上），PC 在 192.168.31.0/24。
  要让光猫访问 PC 就得在路由器上加 masquerade，等于把整个内网开放给光猫。
  **中转做法不用任何 NAT**：路由器 wan 口已经有 192.168.1.2，和光猫同网段。

流程：
  1) scp 文件到路由器 /tmp/ontdl/
  2) 在路由器上用 uhttpd/httpd 起一个只服务该目录的 HTTP（绑 192.168.1.2:8081）
  3) 打印光猫侧该敲的 wget 命令；加 --run 直接通过 telnet 下发

用法：
    python 光猫-HG5585F/tools/ont_push_file.py 光猫-HG5585F/downloads/an758x-stock2ubi
    python 光猫-HG5585F/tools/ont_push_file.py <file> --run
    python 光猫-HG5585F/tools/ont_push_file.py --serve-only
"""
import argparse
import os
import posixpath
import subprocess
import sys
import time

ROUTER_HOST, ROUTER_USER, ROUTER_PASSWORD = "192.168.31.1", "root", "Qazswxdecf1"
SERVE_IP, SERVE_PORT = "192.168.1.2", 8081
ONT_IP, ONT_USER, ONT_PASS = "192.168.1.1", "admin", "Fh@163280"
ONT_DLDIR = "/tmp/ontdl"


def sh(cmd, timeout=180):
    p = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
    return p.stdout + (("\n[stderr] " + p.stderr) if p.stderr.strip() else "")


def router(script):
    import paramiko
    cl = paramiko.SSHClient()
    cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cl.connect(ROUTER_HOST, username=ROUTER_USER, password=ROUTER_PASSWORD,
                look_for_keys=False, allow_agent=False, timeout=10)
    try:
        sftp = cl.open_sftp()
        try:
            sftp.mkdir(ONT_DLDIR)
        except Exception:
            pass
        sftp.close()
        _, so, se = cl.exec_command("sh -c " + repr_q(script), timeout=180)
        return so.read().decode("utf-8", "replace") + se.read().decode("utf-8", "replace")
    finally:
        cl.close()


def repr_q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def upload(path):
    import paramiko
    name = os.path.basename(path)
    cl = paramiko.SSHClient()
    cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cl.connect(ROUTER_HOST, username=ROUTER_USER, password=ROUTER_PASSWORD,
                look_for_keys=False, allow_agent=False, timeout=10)
    try:
        sftp = cl.open_sftp()
        try:
            sftp.mkdir(ONT_DLDIR)
        except Exception:
            pass
        print("  scp → %s/%s" % (ONT_DLDIR, name))
        sftp.put(path, posixpath.join(ONT_DLDIR, name))
        sftp.close()
    finally:
        cl.close()
    print(router("ls -l %s/%s" % (ONT_DLDIR, name)))
    return name


def serve():
    # 本机 uhttpd 版本【默认就 fork 到后台】（-f 才是前台），且没有 -d / -m / -t 选项。
    # 绝对不能用 `uhttpd ... &`：那样进程会随 ssh 会话结束被杀掉。
    script = r"""
killall uhttpd 2>/dev/null
mkdir -p /tmp/www
cp -f %s/* /tmp/www/ 2>/dev/null
uhttpd -p %s:%d -h /tmp/www
sleep 2
echo "--- listen ---"
netstat -ltn 2>/dev/null | grep %d || echo "NO LISTEN"
""" % (ONT_DLDIR, SERVE_IP, SERVE_PORT, SERVE_PORT)
    print(router(script))


def ont_wget(name):
    # 光猫的受限 shell 按【命令名】拉黑名单（dd/rm/cp/ln/head/uname/which/id/df/wget…），
    # 裸 `wget` 会被拦。但 /fhrom/bin/wget 是真的 GNU Wget 1.21.4，用绝对路径就绕过了。
    return ("cd /tmp && /fhrom/bin/wget -q -O /tmp/%s http://%s:%d/%s "
            "&& chmod +x /tmp/%s && ls -l /tmp/%s") % (
        name, SERVE_IP, SERVE_PORT, name, name, name)


def ont_run(cmd):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ont_shell import Shell
    # 注意：ont_shell.Shell.login() 没有返回值（只调 wait_prompt），所以这里自己判断
    for attempt in range(3):
        s = Shell(ONT_IP, user=ONT_USER, password=ONT_PASS)
        try:
            s.pump(1.5)
            s.send(ONT_USER); s.pump(1.0)
            s.send(ONT_PASS)
            buf = s.wait_prompt(10)
            if "$" in buf or "#" in buf or ">" in buf:
                print("  " + s.run(cmd, maxwait=120))
                return 0
            print("  登录未拿到提示符，重试 %d" % (attempt + 1))
        finally:
            s.close()
        time.sleep(3)
    print("  [错误] telnet 登录失败")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--run", action="store_true", help="下发 wget 命令到光猫")
    ap.add_argument("--serve-only", action="store_true")
    a = ap.parse_args()

    if a.serve_only or not a.file:
        serve()
        return 0

    path = os.path.abspath(a.file)
    if not os.path.isfile(path):
        print("  找不到 %s" % path); return 1
    print("== 1) 上传到路由器 ==")
    name = upload(path)
    print("\n== 2) 路由器起 HTTP（%s:%d，只服务 /tmp/www）==" % (SERVE_IP, SERVE_PORT))
    serve()
    cmd = ont_wget(name)
    print("\n== 3) 光猫侧执行（telnet admin/Fh@163280）==")
    print("  " + cmd)
    if a.run:
        print()
        return ont_run(cmd)
    return 0


if __name__ == "__main__":
    os.system("chcp 65001 > nul")
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())