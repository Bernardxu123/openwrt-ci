#!/usr/bin/env python3
"""批量写入 DHCP 静态租约 + 静态设备 DNS 名（2026-10-23 设备清单）。

设计原则：全部按设备"当前 IP"原样钉死，不改任何设备 IP、不改 DHCP 池。

用法（在 PC 工作区根目录执行）：
  python tools/pin_leases_20261023.py --check     # 只读校验，对照期望清单
  python tools/pin_leases_20261023.py --dry-run   # 打印将执行的配置脚本
  python tools/pin_leases_20261023.py --apply     # 写入并 reload dnsmasq
  python tools/pin_leases_20261023.py --rollback  # 用备份恢复 dhcp + hosts
"""
import argparse
import sys

import paramiko

HOST = "192.168.31.1"
USER = "root"
PASSWORD = "Qazswxdecf1"
SUFFIX = ".bak-20261023"
MARK_BEGIN = "# --- static devices 20261023 ---"
MARK_END = "# --- end static devices 20261023 ---"

# (uci section, mac, ip, 说明)
LEASES = [
    # --- A 组：已有保留，仅校验 ---
    ("pc_wlan", "68:3e:26:0d:d0:22", "192.168.31.222", "主力 PC WiFi(Intel AX201,当前在用)"),
    ("pc_eth", "80:fa:5b:90:d1:c0", "192.168.31.218", "主力 PC 有线(Realtek,当前禁用)"),
    ("xiaomi_ap", "a4:a9:30:81:e9:2e", "192.168.31.138", "小米 BE6500 Pro AP"),
    ("tablet", "e6:33:6a:a9:24:e3", "192.168.31.122", "华为平板 DMG-W00(随机MAC)"),
    ("mi14pro", "88:6c:60:1f:ee:60", "192.168.31.221", "小米14Pro(真实MAC)"),
    ("roborock", "24:9e:7d:7b:a9:ff", "192.168.31.153", "石头扫地机"),
    ("vidda_tv", "88:6c:60:a2:ee:60", "192.168.31.208", "Vidda S70 电视"),
    # --- B 组：新增，按当前租约 IP 钉死 ---
    ("p30pro", "f2:8f:50:45:16:81", "192.168.31.155", "HUAWEI P30 Pro(随机MAC)"),
    ("mate60", "52:35:01:99:73:1e", "192.168.31.124", "华为 SGT-AL10(随机MAC)"),
    ("mi14pro2", "ce:70:9d:c2:3e:0d", "192.168.31.214", "小米14Pro 二号/随机MAC"),
    ("oppo_reno6", "ac:76:4c:f6:f8:7d", "192.168.31.198", "OPPO Reno6 5G"),
    ("soundbox_lx06", "d4:da:21:49:9a:1b", "192.168.31.101", "小爱音箱 LX06"),
    ("soundbox_oh2p", "58:ea:1f:2c:40:9d", "192.168.31.182", "小爱音箱 OH2P"),
    ("camera_cm", "78:df:72:43:7f:36", "192.168.31.220", "创米摄像头"),
    ("microwave", "54:48:e6:6a:ee:c7", "192.168.31.239", "米家微波炉"),
    ("cooker", "40:31:3c:e6:9f:8b", "192.168.31.102", "米家电饭煲"),
    ("haier_ac1", "a0:82:22:2d:cb:82", "192.168.31.164", "海尔空调 1"),
    ("haier_ac2", "a0:82:22:00:e3:8e", "192.168.31.240", "海尔空调 2"),
    # --- C 组：自配静态 IP（无租约）保护性保留，防动态池撞车 ---
    ("dev170", "58:b6:23:d1:6e:ae", "192.168.31.170", "自配静态设备"),
    ("dev219", "64:9e:31:dd:66:fa", "192.168.31.219", "自配静态设备"),
    ("dev145", "ac:8c:46:ed:05:e7", "192.168.31.145", "自配静态设备"),
    ("dev146", "d4:f0:ea:26:45:8f", "192.168.31.146", "自配静态设备"),
    ("dev179", "d4:f0:ea:1e:d0:91", "192.168.31.179", "自配静态设备"),
]

# 需要删除的旧段（命名与实际网卡错位的遗留）
RETIRE = {"pc_wifi"}

# 永远不会走 DHCP 的设备（自配静态 IP / 网卡禁用）→ 只能靠 /etc/hosts 提供名字
STATIC_DNS = [
    ("192.168.31.138", "ap ap.lan xiaomi_ap xiaomi_ap.lan"),
    ("192.168.31.218", "pc_eth pc_eth.lan"),
    ("192.168.31.170", "dev170 dev170.lan"),
    ("192.168.31.219", "dev219 dev219.lan"),
    ("192.168.31.145", "dev145 dev145.lan"),
    ("192.168.31.146", "dev146 dev146.lan"),
    ("192.168.31.179", "dev179 dev179.lan"),
]


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD,
              look_for_keys=False, allow_agent=False, timeout=15)
    return c


def run(client, cmd, timeout=120):
    _in, out, err = client.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    rc = out.channel.recv_exit_status()
    return o, e, rc


def run_script(client, script, timeout=180):
    _in, out, err = client.exec_command("sh -s", timeout=timeout)
    _in.write(script)
    _in.channel.shutdown_write()
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    rc = out.channel.recv_exit_status()
    return o, e, rc


def parse_uci(out):
    """uci -q show dhcp -> {section: {opt: value}}, 只关心 host 段。"""
    sections = {}
    for line in out.splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        parts = key.split(".")
        if len(parts) < 2 or parts[0] != "dhcp":
            continue
        sec = parts[1]
        val = val.strip().strip("'")
        if len(parts) == 2 and val == "host":
            sections.setdefault(sec, {})
        elif len(parts) == 3 and sec in sections:
            sections[sec][parts[2]] = val
    return sections


def validate(sections):
    """检查表内重复，以及表外段占用同 IP/同 MAC。"""
    problems = []
    by_ip, by_mac = {}, {}
    for name, mac, ip, desc in LEASES:
        if ip in by_ip:
            problems.append(f"表内 IP 重复: {ip} ({by_ip[ip]} / {name})")
        if mac in by_mac:
            problems.append(f"表内 MAC 重复: {mac} ({by_mac[mac]} / {name})")
        by_ip[ip] = name
        by_mac[mac] = name

    wanted_secs = {n for n, _, _, _ in LEASES}
    for sec, opt in sections.items():
        if sec in wanted_secs or sec in RETIRE:
            continue
        dip = opt.get("ip", "")
        if dip in by_ip:
            problems.append(f"冲突: 现有段 {sec}({dip}) 与 {by_ip[dip]} 同 IP")
        dmac = opt.get("mac", "").lower()
        if dmac in by_mac:
            problems.append(f"冲突: 现有段 {sec}({dmac}) 与 {by_mac[dmac]} 同 MAC")
    return problems


def build_script(sections):
    cmds = ["set -e",
            f"[ -f /etc/config/dhcp{SUFFIX} ] || cp /etc/config/dhcp /etc/config/dhcp{SUFFIX}",
            f"[ -f /etc/hosts{SUFFIX} ] || cp /etc/hosts /etc/hosts{SUFFIX}"]
    for old in sorted(RETIRE):
        cmds.append(f"uci -q delete dhcp.{old} || true")
    for name, mac, ip, _desc in LEASES:
        if name not in sections:
            cmds.append(f"uci set dhcp.{name}=host")
        cmds.append(f"uci set dhcp.{name}.name='{name}'")
        cmds.append(f"uci set dhcp.{name}.mac='{mac}'")
        cmds.append(f"uci set dhcp.{name}.ip='{ip}'")
    cmds.append("uci commit dhcp")
    cmds.append(f"sed -i '/^{MARK_BEGIN}$/,/^{MARK_END}$/d' /etc/hosts")
    cmds.append("cat >> /etc/hosts <<'HOSTSEOF'")
    cmds.append(MARK_BEGIN)
    for ip, names in STATIC_DNS:
        cmds.append(f"{ip}\t{names}")
    cmds.append(MARK_END)
    cmds.append("HOSTSEOF")
    cmds.append("/etc/init.d/dnsmasq reload || killall -HUP dnsmasq")
    cmds.append("sleep 2")
    cmds.append("echo CONFIG_DONE")
    return "\n".join(cmds) + "\n"


def check(client):
    out, err, rc = run(client, "uci -q show dhcp")
    if rc != 0:
        print("读取 uci 失败:", err)
        return 1
    sections = parse_uci(out)
    problems = validate(sections)
    for sec in sorted(RETIRE & set(sections)):
        print(f"  [待清理] {sec} 为命名错位旧段，将删除")
    print(f"现有 host 段: {len(sections)}，期望: {len(LEASES)}")
    bad = 0
    for name, mac, ip, desc in LEASES:
        cur = sections.get(name)
        if not cur:
            print(f"  [缺失] {name:14s} {ip:15s} {desc}")
            bad += 1
            continue
        cmac = cur.get("mac", "").lower()
        cip = cur.get("ip", "")
        if cmac != mac.lower() or cip != ip:
            print(f"  [不一致] {name:14s} 期望 {mac}/{ip} 实际 {cmac}/{cip}")
            bad += 1
        else:
            print(f"  [OK]   {name:14s} {ip:15s} {desc}")
    for p in problems:
        print("!!", p)
    return 1 if (bad or problems) else 0


def check_dns(client):
    print("\n-- DNS 名字解析 --")
    for q in ("pc_eth.lan", "ap.lan", "dev170.lan", "p30pro.lan"):
        o, _e, _rc = run(client, f"nslookup {q} 127.0.0.1 2>&1")
        ip, lines = "", o.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("Name:") and i + 1 < len(lines) and lines[i + 1].strip().startswith("Address"):
                ip = lines[i + 1].split(":", 1)[-1].strip()
                break
        print(f"  {q:16s} -> {ip or 'NXDOMAIN'}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = connect()
    try:
        if args.rollback:
            script = (
                "set -e\n"
                f"cp /etc/config/dhcp{SUFFIX} /etc/config/dhcp\n"
                f"cp /etc/hosts{SUFFIX} /etc/hosts\n"
                "uci commit dhcp\n"
                "/etc/init.d/dnsmasq reload || killall -HUP dnsmasq\n"
                "sleep 2\necho ROLLBACK_DONE\n")
            o, e, rc = run_script(client, script)
            print(o.strip() or e.strip())
            return 0 if rc == 0 else 1

        out, err, rc = run(client, "uci -q show dhcp")
        sections = parse_uci(out)
        problems = validate(sections)
        if problems:
            for p in problems:
                print("!!", p)
            print("发现冲突，中止。")
            return 2

        if args.check:
            code = check(client)
            check_dns(client)
            return code

        script = build_script(sections)
        if args.dry_run:
            print(script)
            return 0

        print("写入配置 ...")
        o, e, rc = run_script(client, script)
        print(o.strip())
        if e.strip():
            print("[stderr]", e.strip())
        if rc != 0 or "CONFIG_DONE" not in o:
            print("配置脚本执行失败，rc=", rc)
            return 1

        # 应用后校验
        code = check(client)
        check_dns(client)
        out, _e, _rc = run(client, "uci -q show dhcp | grep -c '=host'")
        print("\nhost 段总数:", out.strip())
        out, _e, _rc = run(client, "grep -c '^dhcp-host' /var/etc/dnsmasq.conf.* 2>/dev/null | head -1")
        print("dnsmasq 生效 dhcp-host 行数:", out.strip())
        return code
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
