#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
光猫访问通道 开关 / 状态  (FiberHome HG5585F, 联通 CU)

光猫是桥接模式，没有 DHCP，主路由 wan 口上默认只有裸 PPPoE、没有 IP，
所以访问 http://192.168.1.1 需要临时给 wan 口挂一个 192.168.1.x 的地址。
而且光猫【只认同子网源地址】—— 用别的网段探它，ARP 能到 REACHABLE 但 HTTP 全超时。

用法:
    python tools/ont.py              # 交互菜单（自己选开关）
    python tools/ont.py on           # 打开通道（默认 TTL 30 分钟自动摘）
    python tools/ont.py on --ttl 7200 # 打开，2 小时后自动摘
    python tools/ont.py on --ttl 0   # 一直开启，直到手动 off
    python tools/ont.py off          # 立即关闭
    python tools/ont.py toggle       # 开↔关 互切
    python tools/ont.py status       # 只看状态

对 PPPoE / NAT / daed 零影响：只加运行态地址和路由，不写 UCI、不 reload network。
"""
import argparse
import os
import sys

import paramiko

if os.name == "nt":  # Windows 控制台默认 GBK，中文会花屏；切到 UTF-8 码页
    os.system("chcp 65001 > nul")
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROUTER_HOST = "192.168.31.1"
ROUTER_USER = "root"
ROUTER_PASSWORD = "Qazswxdecf1"

# 设备侧脚本：输出保持纯 ASCII，中文一律由本脚本渲染，避免 Windows 控制台编码问题
REMOTE = r'''#!/bin/sh
DEV=wan
IP=192.168.1.2
PREFIX=24
NET=192.168.1.0/24
TARGET=192.168.1.1
ACT=$1
TTL=$2
[ -z "$TTL" ] && TTL=1800

has_ip()    { ip -4 addr show dev $DEV 2>/dev/null | grep -q "inet $IP/"; }
has_route() { ip route show $NET 2>/dev/null | grep -q "dev $DEV"; }

stop_timer() {
    rm -f /tmp/ont_persist
    if [ -f /tmp/ont_ttl.pid ]; then
        kill "$(cat /tmp/ont_ttl.pid)" 2>/dev/null
        rm -f /tmp/ont_ttl.pid
        echo "TIMER=stopped"
    else
        echo "TIMER=none"
    fi
}

clean() {
    ip route del $NET dev $DEV 2>/dev/null
    ip addr del $IP/$PREFIX dev $DEV 2>/dev/null
}

report() {
    has_ip    && echo "IP=yes"     || echo "IP=no"
    has_route && echo "ROUTE=yes"  || echo "ROUTE=no"
    echo "TTL=$(cat /tmp/ont_ttl.pid 2>/dev/null || echo none)"
    [ -f /tmp/ont_persist ] && echo "PERSIST=yes" || echo "PERSIST=no"
    if has_ip && has_route; then
        ping -c 2 -W 2 -I $DEV $TARGET >/dev/null 2>&1 && echo "PING=yes" || echo "PING=no"
        (nc $TARGET 80 </dev/null >/dev/null 2>&1) && echo "WEB80=yes" || echo "WEB80=no"
    else
        echo "PING=skip"
        echo "WEB80=skip"
    fi
    U=$(ubus call network.interface.wan status 2>/dev/null | grep -c '"up": true')
    A=$(ubus call network.interface.wan status 2>/dev/null | grep '"address"' | head -1 | sed 's/.*"address": "//;s/".*//')
    echo "PPP_UP=$U"
    echo "PPP_ADDR=$A"
}

case "$ACT" in
on)
    stop_timer
    clean
    if ip addr add $IP/$PREFIX dev $DEV 2>/dev/null; then
        echo "RESULT=addr_ok"
    else
        echo "RESULT=addr_fail"
        exit 1
    fi
    ip route replace $NET dev $DEV src $IP 2>/dev/null
    echo "RESULT=route_ok"

    cat > /tmp/ont_close.sh <<'CLOSE'
#!/bin/sh
ip route del 192.168.1.0/24 dev wan 2>/dev/null
ip addr del 192.168.1.2/24 dev wan 2>/dev/null
ip neigh flush to 192.168.1.0/24 dev wan 2>/dev/null
logger -t ont-access "TTL expired, cleaned"
echo "$(date '+%F %T') TTL expired, cleaned" >> /tmp/ont_access.log
rm -f /tmp/ont_ttl.pid /tmp/ont_persist
CLOSE
    chmod +x /tmp/ont_close.sh
    if [ "$TTL" = "0" ]; then
        rm -f /tmp/ont_ttl.pid
        touch /tmp/ont_persist
        echo "TTL_SET=0"
        echo "TIMER=none"
    else
        nohup sh -c "sleep $TTL; /tmp/ont_close.sh" >/dev/null 2>&1 &
        echo $! > /tmp/ont_ttl.pid
        echo "TTL_SET=$TTL"
        echo "TIMER=armed"
    fi
    report
    ;;
off)
    stop_timer
    clean
    echo "RESULT=off"
    report
    ;;
toggle)
    if has_ip; then ACT=off; else ACT=on; fi
    echo "TOGGLE=$ACT"
    exec sh /tmp/run_local.sh "$ACT" "$TTL"
    ;;
status|"")
    report
    ;;
*)
    echo "RESULT=bad_action"
    exit 2
    ;;
esac
'''


def run(action, ttl=None):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ROUTER_HOST, username=ROUTER_USER, password=ROUTER_PASSWORD,
                   look_for_keys=False, allow_agent=False, timeout=10)
    try:
        sftp = client.open_sftp()
        with sftp.open("/tmp/run_local.sh", "w") as f:
            f.write(REMOTE)
        sftp.close()
        cmd = "sh /tmp/run_local.sh %s %s" % (action, "" if ttl is None else ttl)
        _, stdout, stderr = client.exec_command(cmd, timeout=120)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
    finally:
        client.close()

    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()

    def yn(k):
        return {"yes": "有", "no": "无", "skip": "跳过"}.get(kv.get(k, ""), kv.get(k, "?"))

    print()
    print("  通道地址   192.168.1.2/24 on wan     %s" % ("已挂载" if kv.get("IP") == "yes" else "未挂载"))
    print("  路由       192.168.1.0/24 -> wan     %s" % ("已配置" if kv.get("ROUTE") == "yes" else "未配置"))
    if kv.get("PERSIST") == "yes":
        auto = "无（一直开启，需手动关闭）"
    elif kv.get("TIMER") == "armed":
        auto = "定时器 PID %s 已挂，%s 秒后自动摘除" % (kv.get("TTL"), kv.get("TTL_SET", "1800"))
    elif kv.get("TIMER") == "stopped":
        auto = "已停止"
    else:
        auto = "无"
    print("  自动清理   %s" % auto)
    print("  光猫可达   ICMP %s / Web80 %s" % (yn("PING"), yn("WEB80")))
    print("  PPPoE      %s   地址 %s" % (
        "正常在线" if kv.get("PPP_UP") == "1" else "⚠ 异常", kv.get("PPP_ADDR", "-")))
    if err.strip():
        print("\n  [stderr] %s" % err.strip()[:400])
    return kv


def interactive():
    print()
    print("=" * 58)
    print("  光猫 (烽火 HG5585F) 访问通道")
    print("=" * 58)
    run("status")
    print()
    print("  [1] 打开通道（默认 30 分钟自动摘除）")
    print("  [2] 关闭通道")
    print("  [3] 刷新状态")
    print("  [4] 一直开启（需手动关闭）")
    print("  [0] 退出")
    print()
    while True:
        try:
            c = input("  请选择 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出。\n")
            return 0
        if c == "1":
            run("on")
        elif c == "2":
            run("off")
        elif c == "3":
            run("status")
        elif c == "4":
            run("on", 0)
        elif c == "0":
            print("\n  已退出。\n")
            return 0
        else:
            print("  无效输入，请选 0/1/2/3/4")


def main():
    ap = argparse.ArgumentParser(add_help=True, description="光猫访问通道开关")
    ap.add_argument("action", nargs="?", choices=["on", "off", "toggle", "status", "menu"])
    ap.add_argument("--ttl", type=int, default=None, help="自动清理秒数，默认 1800；0 = 一直开启，需手动关闭")
    a = ap.parse_args()
    if a.action in (None, "menu"):
        return interactive()
    run(a.action, a.ttl)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except paramiko.ssh_exception.AuthenticationException:
        print("  路由器 SSH 认证失败，检查 tools 里的密码配置。")
        sys.exit(1)
    except paramiko.ssh_exception.SSHException as e:
        print("  连不上路由器 %s：%s" % (ROUTER_HOST, e))
        sys.exit(1)