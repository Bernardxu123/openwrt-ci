#!/usr/bin/env python3
"""部署 wugui-sub-update.sh 到路由器并配置 cron / 关闭 daed 乌龟内置 cron。

用法:
  python wugui/deploy_wugui_sub.py --dry          # 只打印将执行的步骤
  python wugui/deploy_wugui_sub.py                # 实际部署（不含写真实密码）
  python wugui/deploy_wugui_sub.py --run-once     # 部署后立刻跑一次全链路
  python wugui/deploy_wugui_sub.py --write-conf   # 连同真实凭据写入 /etc/wugui-sub.conf

凭据来源（优先级）: wugui/secrets.local.py（勿入库）> 环境变量
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parent))

HOST = os.environ.get("ROUTER_HOST", "192.168.31.1")
USER = os.environ.get("ROUTER_USER", "root")
PASSWORD = os.environ.get("ROUTER_PASS", "Qazswxdecf1")

try:  # pragma: no cover
    from secrets_local import (  # type: ignore
        WUGUI_EMAIL as DEFAULT_WUGUI_EMAIL,
        WUGUI_PASSWORD as DEFAULT_WUGUI_PASSWORD,
        DAED_PASS as DEFAULT_DAED_PASS,
        DAED_USER as DEFAULT_DAED_USER,
        DAED_SUB_ID as DEFAULT_DAED_SUB_ID,
        DAED_SUB_TAG as DEFAULT_DAED_SUB_TAG,
        WUGUI_API as DEFAULT_WUGUI_API,
        DAED_URL as DEFAULT_DAED_URL,
    )
except Exception:
    DEFAULT_WUGUI_EMAIL = os.environ.get("WUGUI_EMAIL", "")
    DEFAULT_WUGUI_PASSWORD = os.environ.get("WUGUI_PASSWORD", "")
    DEFAULT_DAED_PASS = os.environ.get("DAED_PASS", "")
    DEFAULT_DAED_USER = os.environ.get("DAED_USER", "root")
    DEFAULT_DAED_SUB_ID = os.environ.get("DAED_SUB_ID", "Y3Vyc29yMw")
    DEFAULT_DAED_SUB_TAG = os.environ.get("DAED_SUB_TAG", "乌龟")
    DEFAULT_WUGUI_API = os.environ.get("WUGUI_API", "https://wgjsq08.vip/wuguiapi")
    DEFAULT_DAED_URL = os.environ.get("DAED_URL", "http://192.168.31.1:2023/graphql")

if not DEFAULT_WUGUI_EMAIL or not DEFAULT_WUGUI_PASSWORD or not DEFAULT_DAED_PASS:
    raise SystemExit(
        "缺少凭据：请创建 wugui/secrets.local.py（见 wugui-sub.conf.example）或设置 "
        "WUGUI_EMAIL / WUGUI_PASSWORD / DAED_PASS 环境变量"
    )

SCRIPT_LOCAL = Path(__file__).resolve().parent / "wugui-sub-update.sh"
SCRIPT_REMOTE = "/usr/bin/wugui-sub-update.sh"
CONF_REMOTE = "/etc/wugui-sub.conf"
CRON_LINE = "50 5 * * * /usr/bin/wugui-sub-update.sh"
CRON_MARK = "wugui-sub-update"

SECRETS = (DEFAULT_DAED_PASS, DEFAULT_WUGUI_PASSWORD, PASSWORD)


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def build_conf() -> str:
    """Shell-sourceable KEY='value' lines (single-quoted, safe for spaces/$/#)."""
    rows = [
        ("WUGUI_EMAIL", DEFAULT_WUGUI_EMAIL),
        ("WUGUI_PASSWORD", DEFAULT_WUGUI_PASSWORD),
        ("WUGUI_API", DEFAULT_WUGUI_API),
        ("DAED_URL", DEFAULT_DAED_URL),
        ("DAED_USER", DEFAULT_DAED_USER),
        ("DAED_PASS", DEFAULT_DAED_PASS),
        ("DAED_SUB_ID", DEFAULT_DAED_SUB_ID),
        ("DAED_SUB_TAG", DEFAULT_DAED_SUB_TAG),
    ]
    return "".join(f"{k}={sh_quote(v)}\n" for k, v in rows)


def redact(text: str) -> str:
    for secret in SECRETS:
        if secret:
            text = text.replace(secret, "***")
    return text


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, look_for_keys=False, allow_agent=False, timeout=15)
    return client


def run(client: paramiko.SSHClient, cmd: str, dry: bool) -> tuple[int, str, str]:
    print(f"$ {redact(cmd)}")
    if dry:
        return 0, "", ""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out:
        print(redact(out), end="" if out.endswith("\n") else "\n")
    if err:
        print("[stderr]", redact(err), end="" if err.endswith("\n") else "\n")
    return code, out, err


def sftp_put_text(client: paramiko.SSHClient, text: str, remote: str, dry: bool, mode: int = 0o644) -> None:
    print(f">>> write {remote} ({len(text)} bytes, mode {oct(mode)})")
    if dry:
        return
    sftp = client.open_sftp()
    try:
        with sftp.file(remote, "w") as f:
            f.write(text)
        sftp.chmod(remote, mode)
    finally:
        sftp.close()


def sftp_put(client: paramiko.SSHClient, local: Path, remote: str, dry: bool, mode: int = 0o755) -> None:
    print(f">>> put {local} -> {remote} (mode {oct(mode)})")
    if dry:
        return
    sftp_put_text(client, local.read_text(encoding="utf-8"), remote, dry, mode)


def disable_daed_wugui_cron(client: paramiko.SSHClient, dry: bool) -> None:
    """关掉 daed 乌龟订阅内置 cron。JSON 用 Python json.dumps 生成，避免 shell 转义。"""
    tok_payload = json.dumps(
        {
            "query": "query($u:String!,$p:String!){ token(username:$u,password:$p) }",
            "variables": {"u": DEFAULT_DAED_USER, "p": DEFAULT_DAED_PASS},
        }
    )
    cron_payload = json.dumps(
        {
            "query": "mutation($id:ID!,$e:String!,$en:Boolean!){ updateSubscriptionCron(id:$id,cronExp:$e,cronEnable:$en){ id cronEnable } }",
            "variables": {"id": DEFAULT_DAED_SUB_ID, "e": "0 6 * * *", "en": False},
        }
    )
    sftp_put_text(client, tok_payload, "/tmp/dd-tok.json", dry)
    sftp_put_text(client, cron_payload, "/tmp/dd-cron.json", dry)
    script = f"""
set -e
DAED={sh_quote(DEFAULT_DAED_URL)}
TOKEN=$(curl -s --connect-timeout 5 --max-time 15 -X POST "$DAED" \\
  -H 'Content-Type: application/json' \\
  --data-binary @/tmp/dd-tok.json | jsonfilter -e '@.data.token')
echo "daed_token_len=${{#TOKEN}}"
curl -s --connect-timeout 5 --max-time 15 -X POST "$DAED" \\
  -H 'Content-Type: application/json' \\
  -H "Authorization: $TOKEN" \\
  --data-binary @/tmp/dd-cron.json
echo
"""
    run(client, script, dry)


def ensure_cron(client: paramiko.SSHClient, dry: bool) -> None:
    run(
        client,
        f"grep -q '{CRON_MARK}' /etc/crontabs/root 2>/dev/null || "
        f"echo '{CRON_LINE} # {CRON_MARK}' >> /etc/crontabs/root; "
        "/etc/init.d/cron restart",
        dry,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="只打印命令，不执行")
    ap.add_argument("--run-once", action="store_true", help="部署后立刻跑一次")
    ap.add_argument("--write-conf", action="store_true", help="写入含真实凭据的 /etc/wugui-sub.conf")
    ap.add_argument("--disable-daed-cron", action="store_true", help="仅关闭 daed 乌龟 cron")
    args = ap.parse_args()

    if not SCRIPT_LOCAL.exists():
        print("missing", SCRIPT_LOCAL, file=sys.stderr)
        return 2

    dry = args.dry
    client = connect()
    try:
        sftp_put(client, SCRIPT_LOCAL, SCRIPT_REMOTE, dry, 0o755)
        if args.write_conf:
            print(f">>> write {CONF_REMOTE} (contains secrets)")
            sftp_put_text(client, build_conf(), CONF_REMOTE, dry, 0o600)
        else:
            run(
                client,
                f"[ -f {CONF_REMOTE} ] || echo 'CREATE {CONF_REMOTE} from wugui-sub.conf.example'",
                dry,
            )
        ensure_cron(client, dry)
        disable_daed_wugui_cron(client, dry)
        if args.disable_daed_cron:
            return 0
        if args.run_once:
            run(client, f"chmod +x {SCRIPT_REMOTE}; {SCRIPT_REMOTE}; echo EXIT:$?", dry)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
