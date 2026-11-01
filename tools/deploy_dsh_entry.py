#!/usr/bin/env python3
"""把 DSH 手机入口（IPv6 直连）的路由器侧改动幂等部署到 QWRT 路由器。

做六件事（全部幂等）：
 1. 备份现有 /etc/dsh-nginx/nginx.conf、upstream.conf、watchdog、ddns 脚本、init 到
    /root/bak-dsh-<日期>/（已存在则不覆盖备份）
 2. 推送 nginx.conf（HTTP/2 + 上游 keepalive + /assets 强缓存 + gzip + 快速 502）
 3. 推送 /etc/dsh-nginx/upstream.conf（缺失才写默认 3081）、init.d-dsh-nginx、
    dsh-watchdog.sh（端口自动发现/DDNS 一致性/证书告警）、update_cloudflare_dsh.sh（12h 对账）
 4. 删除抢流量的 DNAT：firewall.dsh_pocket(3081→PC IPv6)、firewall.dsh_pocket2(3082→PC IPv6)
 5. ddns check_interval 5 → 2 分钟
 6. nginx -t → 重启 dsh-nginx → 跑一次 watchdog 对齐真实端口 → 输出自检

用法：
    python tools/deploy_dsh_entry.py            # 部署 + 自检
    python tools/deploy_dsh_entry.py --dry-run  # 只打印将要做什么
    python tools/deploy_dsh_entry.py --no-uci   # 只推文件，不动防火墙/ddns 配置
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

import paramiko

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from ssh_run import HOST, PASSWORD, USER  # noqa: E402

SRC = ROOT / "04-代理-nikki" / "dsh-pocket-ipv6"
BACKUP_DIR = "/root/bak-dsh-20261101"

FILES = [
    (SRC / "nginx.conf", "/etc/dsh-nginx/nginx.conf", "644"),
    (SRC / "upstream.conf", "/etc/dsh-nginx/upstream.conf", "644"),
    (SRC / "init.d-dsh-nginx", "/etc/init.d/dsh-nginx", "755"),
    (SRC / "dsh-watchdog.sh", "/usr/bin/dsh-watchdog.sh", "755"),
    (SRC / "update_cloudflare_dsh.sh", "/usr/lib/ddns/update_cloudflare_dsh.sh", "755"),
]

UCI_FIREWALL_DELETES = ["firewall.dsh_pocket", "firewall.dsh_pocket2"]


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 90) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def put(client: paramiko.SSHClient, local: Path, remote: str, mode: str, dry: bool) -> None:
    data = local.read_bytes()
    if dry:
        print(f"  [dry] put {local.name} -> {remote} ({len(data)} B, mode {mode})")
        return
    # OpenWrt 没有 sftp：用 exec 的 stdin 写文件
    stdin, stdout, stderr = client.exec_command(f"cat > {shlex.quote(remote)}", timeout=60)
    stdin.write(data)
    stdin.flush()
    stdin.channel.shutdown_write()
    rc = stdout.channel.recv_exit_status()
    if rc != 0:
        raise RuntimeError(f"write {remote} failed rc={rc}: {stderr.read().decode('utf-8', 'replace')}")
    rc2, _, err2 = run(client, f"chmod {mode} {shlex.quote(remote)} && ls -l {shlex.quote(remote)}")
    print(f"  put {local.name} -> {remote} ({len(data)} B)")
    if rc2 != 0:
        raise RuntimeError(f"chmod {remote} failed: {err2}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-uci", action="store_true", help="只推文件，不改防火墙/ddns uci")
    args = ap.parse_args()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)
    try:
        print("[0/6] 备份")
        rc, out, err = run(
            client,
            f"mkdir -p {BACKUP_DIR} && "
            f"[ -f {BACKUP_DIR}/nginx.conf ] || cp /etc/dsh-nginx/nginx.conf {BACKUP_DIR}/ ; "
            f"[ -f {BACKUP_DIR}/upstream.conf ] || cp /etc/dsh-nginx/upstream.conf {BACKUP_DIR}/ 2>/dev/null ; "
            f"[ -f {BACKUP_DIR}/init.d-dsh-nginx ] || cp /etc/init.d/dsh-nginx {BACKUP_DIR}/ ; "
            f"[ -f {BACKUP_DIR}/dsh-watchdog.sh ] || cp /usr/bin/dsh-watchdog.sh {BACKUP_DIR}/ ; "
            f"[ -f {BACKUP_DIR}/update_cloudflare_dsh.sh ] || cp /usr/lib/ddns/update_cloudflare_dsh.sh {BACKUP_DIR}/ ; "
            f"uci export firewall > {BACKUP_DIR}/firewall.export ; uci export ddns > {BACKUP_DIR}/ddns.export ; "
            f"echo backup-ok",
        )
        print("  " + out.strip())
        if rc != 0:
            print("  [warn] 备份命令非 0：" + err.strip())

        print("[1/6] 推送文件")
        for local, remote, mode in FILES:
            if remote == "/etc/dsh-nginx/upstream.conf" and not args.dry_run:
                rc, out, _ = run(client, "[ -f /etc/dsh-nginx/upstream.conf ] && echo exists || echo missing")
                if "exists" in out:
                    print("  skip upstream.conf（已存在，由 watchdog 维护真实端口）")
                    continue
            put(client, local, remote, mode, args.dry_run)

        if not args.no_uci and not args.dry_run:
            print("[2/6] 删除抢流量的 DNAT（保留 Allow-DSH-Pocket-IPv6）")
            deletes = " ; ".join(f"uci -q delete {s}" for s in UCI_FIREWALL_DELETES)
            rc, out, err = run(client, f"{deletes} ; uci commit firewall && echo firewall-ok", timeout=60)
            print("  " + (out.strip() or err.strip()))
            if rc != 0:
                print("  [warn] 防火墙 uci 失败：" + err.strip())

            print("[3/6] DDNS 检查间隔 → 30 分钟（IPv6 只在重拨/重启变；ifup 有 95-ddns hotplug 立即触发）")
            rc, out, err = run(
                client,
                "uci set ddns.dsh_ipv6.check_interval=30 ; uci commit ddns && "
                "uci get ddns.dsh_ipv6.check_interval",
                timeout=60,
            )
            print("  check_interval=" + out.strip())

            print("[3b/6] 看门狗 cron 2 → 5 分钟")
            rc, out, err = run(
                client,
                "sed -i 's|^\\*/2 \\* \\* \\* \\* /usr/bin/dsh-watchdog.sh|*/5 * * * * /usr/bin/dsh-watchdog.sh|' "
                "/etc/crontabs/root ; /etc/init.d/cron restart >/dev/null 2>&1 ; "
                "grep dsh-watchdog /etc/crontabs/root",
                timeout=60,
            )
            print("  " + out.strip())

        if not args.dry_run:
            print("[4/6] 防火墙 reload")
            rc, out, err = run(client, "/etc/init.d/firewall reload >/dev/null 2>&1; echo fw-reload-done", timeout=90)
            print("  " + out.strip())

            print("[5/6] nginx -t + 重启 dsh-nginx + 对齐上游端口")
            rc, out, err = run(client, "/usr/sbin/nginx -t -c /etc/dsh-nginx/nginx.conf 2>&1; echo rc=$?")
            print("  " + out.strip())
            if "rc=0" not in out:
                print("  [error] nginx -t 失败，回滚：" + err.strip())
                return 2
            run(client, "/etc/init.d/dsh-nginx restart >/dev/null 2>&1", timeout=90)
            rc, out, err = run(client, "/usr/bin/dsh-watchdog.sh; echo watchdog-ok", timeout=90)
            print("  " + out.strip())
            run(client, "/etc/init.d/ddns restart >/dev/null 2>&1", timeout=90)

            print("[6/6] 自检")
            checks = [
                "pidof nginx >/dev/null && echo 'nginx   : running' || echo 'nginx   : FAILED'",
                "netstat -lntp 2>/dev/null | grep -q ':3081' && echo '3081    : listening' || echo '3081    : FAILED'",
                "cat /etc/dsh-nginx/upstream.conf",
                "nft list chain inet fw4 dstnat_wan 2>/dev/null | grep -E 'dport (3081|3082)' || echo 'dnat    : none (ok)'",
                "nft list chain inet fw4 input_wan 2>/dev/null | grep '3081' || echo 'allow   : MISSING'",
                "ps w 2>/dev/null | grep -q '[d]ynamic_dns' && echo 'ddns    : running' || echo 'ddns    : not running'",
                "tail -n 3 /var/log/ddns/dsh_ipv6.log 2>/dev/null",
                "/usr/sbin/nginx -V 2>&1 | grep -q with-http_v2_module && echo 'http2   : module ok'",
            ]
            for c in checks:
                rc, out, err = run(client, c, timeout=60)
                print("  " + (out.strip() or err.strip()))
        else:
            print("[2-6/6] dry-run：跳过 uci / reload / 自检")

        print("done")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
