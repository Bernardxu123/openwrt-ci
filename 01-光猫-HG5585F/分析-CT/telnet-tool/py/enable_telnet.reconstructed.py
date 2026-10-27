#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【重建件 · 非原始源码】
=======================
本文件由静态反编译重建：从 `HG5585F-CT-V2一键开Telnet.exe` 内嵌的 PyInstaller
PKG 归档取出入口脚本 `enable_telnet`（裸 marshal 流 / CPython 3.13.14），再用
xdis 交叉反汇编 + co_consts/co_names 还原控制流。**目标程序从未被执行。**

重建依据与置信度：
  * 字面量（URL / 路径 / 口令 / 字符串）：**逐字节取自 co_consts，可信**
  * 控制流：依据 3.13 字节码逐条还原，行为语义可信；变量名取自 co_varnames
  * 注释、排版、类型标注之外的空白：重建者添加
未还原的细节：`dis` 未能逐指令核对的少量栈操作、行号断点（行号取自 co_positions）。

原始常量（供比对）
------------------
EXPECTED_HARDWARE = 'V4.2.0'
EXPECTED_SOFTWARE = '24FHW45000'
CONTACT_QQ        = '550097676'
WINDOW_TITLE      = 'HG5585F CT V2版 一键开Telnet Xx'
TELNET_PATHS = (
    'InternetGatewayDevice.DeviceInfo.X_CT-COM_ServiceManage.TelnetEnable',
    'InternetGatewayDevice.DeviceInfo.X_CT-COM_ServiceManage.Lan.TelnetEnable',
)
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

EXPECTED_HARDWARE = "V4.2.0"
EXPECTED_SOFTWARE = "24FHW45000"
TELNET_PATHS = (
    "InternetGatewayDevice.DeviceInfo.X_CT-COM_ServiceManage.TelnetEnable",
    "InternetGatewayDevice.DeviceInfo.X_CT-COM_ServiceManage.Lan.TelnetEnable",
)
CONTACT_QQ = "550097676"
WINDOW_TITLE = "HG5585F CT V2版 一键开Telnet Xx"

# Windows 下没有 pycryptodome 依赖，改为把一段固定 PowerShell 脚本喂给
# powershell.exe 做 AES-128-CBC/PKCS7。脚本原文见 co_consts[7]（逐字节）。
POWERSHELL_AES = r"""
$ErrorActionPreference = 'Stop'
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$aes = [System.Security.Cryptography.Aes]::Create()
try {
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key = [Convert]::FromBase64String($request.key)
    $aes.IV = [Convert]::FromBase64String($request.iv)
    $data = [Convert]::FromBase64String($request.data)
    if ($request.action -eq 'encrypt') {
        $transform = $aes.CreateEncryptor()
    } else {
        $transform = $aes.CreateDecryptor()
    }
    try {
        $result = $transform.TransformFinalBlock($data, 0, $data.Length)
        [Console]::Out.Write([Convert]::ToBase64String($result))
    } finally {
        $transform.Dispose()
    }
} finally {
    $aes.Dispose()
}
"""


class ToolError(Exception):
    pass


def print_contact() -> None:
    """Print the contact once, dimmed so it stays low-key."""
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        _enable_vt()
        print(f"\x1b[2mXx QQ {CONTACT_QQ}\x1b[0m")
    else:
        print(f"Xx QQ {CONTACT_QQ}")


def _enable_vt() -> bool:
    """Turn on ANSI escape support so the footer line can be dimmed."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong(0)
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 4))
    except Exception:
        return False


def set_console_title(title: str) -> None:
    """Retitle the console window (Windows only, silently ignored elsewhere)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def press_any_key() -> None:
    """Keep the window open after a double-click launch."""
    if not (hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
        return
    if os.name == "nt":
        os.system("pause")
    else:
        input("按回车键退出...")


def aes_cbc(data: bytes, key: bytes, iv: bytes, *, decrypt: bool = False) -> bytes:
    """AES-128-CBC + PKCS7。Windows 走 PowerShell，其余平台走 openssl 子进程。"""
    if os.name == "nt":
        request = json.dumps({
            "action": "decrypt" if decrypt else "encrypt",
            "key": base64.b64encode(key).decode("ascii"),
            "iv": base64.b64encode(iv).decode("ascii"),
            "data": base64.b64encode(data).decode("ascii"),
        })
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_AES],
                input=request, text=True, capture_output=True, timeout=15, check=True,
            )
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ToolError("Windows PowerShell AES 处理失败") from exc
        return base64.b64decode(result.stdout.strip(), validate=True)

    try:
        result = subprocess.run(
            ["openssl", "enc", "-d" if decrypt else "-e", "-aes-128-cbc",
             "-K", key.hex(), "-iv", iv.hex(), "-nosalt"],
            input=data, capture_output=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ToolError("OpenSSL AES 处理失败；请确认系统已安装 openssl") from exc
    return result.stdout


def http_bytes(url: str, body: bytes | None = None) -> bytes:
    """裸 urllib；显式禁用系统代理（ProxyHandler({})），超时 6s。"""
    request = urllib.request.Request(
        url,
        body,
        {"Content-Type": "text/plain", "Connection": "close"} if body is not None else {},
        "POST" if body is not None else "GET",
    )
    # 空 ProxyHandler => 不读环境代理；避免 >ff 代理误路由到光猫
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=6) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise ToolError(f"设备返回 HTTP {exc.code}: {request.full_url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ToolError(f"无法连接设备: {request.full_url}") from exc


def local_ip_for(host: str, port: int) -> str:
    """连一下目标端口，取本机出接口源地址（UDP/TCP 均可，这里用 TCP connect）。"""
    try:
        with socket.create_connection((host, port), timeout=3) as sock:
            return str(sock.getsockname()[0])
    except OSError as exc:
        raise ToolError(f"无法连接 {host}:{port}") from exc


def derive_key_iv(mac: str) -> tuple[bytes, bytes]:
    """AES key/iv 由 MAC（12 位大写 HEX）派生 —— 只做报文编码，不是身份认证。"""
    h = hashlib.sha256(mac.encode("ascii")).hexdigest()
    key = "".join(h[2 * i + 2] for i in range(16)).encode("ascii")
    iv = "".join(h[3 * i + 3] for i in range(16)).encode("ascii")
    return key, iv


def tool_call(base_url: str, key: bytes, iv: bytes, func: str, **params: str) -> dict:
    """调用烽火私有维护接口 /fh_tool/api（AES 密文整包 + base64）。"""
    payload = {"index": "1", "func": func}
    payload.update(params)
    plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ciphertext = aes_cbc(plaintext, key, iv)
    response = http_bytes(base_url + "/fh_tool/api", base64.b64encode(ciphertext))
    try:
        decoded = aes_cbc(base64.b64decode(response.strip(), validate=True), key, iv, decrypt=True)
        result = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ToolError(f"{func} 响应无法解密或解析；设备协议可能不同") from exc
    if not isinstance(result, dict) or str(result.get("result")) != "0":
        code = result.get("result") if isinstance(result, dict) else "未知"
        raise ToolError(f"{func} 未成功，返回码 {code}")
    return result


class TelnetSession:
    """Small Telnet reader that declines optional negotiations and hides input."""

    def __init__(self, host: str, port: int = 23) -> None:
        self.sock = socket.create_connection((host, port), timeout=6)
        self.state = 0
        self.command = 0
        self.buffer = bytearray()

    def close(self) -> None:
        self.sock.close()

    def write_line(self, line: str) -> None:
        self.sock.sendall(line.encode("utf-8") + b"\n")

    def read_until(self, marker: bytes, timeout: float = 8) -> bytes:
        deadline = time.monotonic() + timeout
        out = bytearray()
        while True:
            index = self.buffer.find(marker)
            if index >= 0:
                head = bytes(self.buffer[:index + len(marker)])
                del self.buffer[:index + len(marker)]
                return out + head
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ToolError("Telnet 等待提示符超时")
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout as exc:
                raise ToolError("Telnet 等待提示符超时") from exc
            except OSError as exc:
                raise ToolError("Telnet 连接被设备关闭") from exc
            if not chunk:
                raise ToolError("Telnet 连接被设备关闭")
            out.extend(chunk)
            self.buffer.extend(chunk)
            # 逐个处理 IAC (255)；拒绝 WILL/WONT/DO/DONT，吞掉子协商
            i = 0
            while i < len(self.buffer):
                byte = self.buffer[i]
                if byte != 255:
                    i += 1
                    continue
                if i + 1 >= len(self.buffer):
                    break
                command = self.buffer[i + 1]
                if command in (251, 252, 253, 254):  # WILL WONT DO DONT
                    if i + 2 >= len(self.buffer):
                        break
                    option = self.buffer[i + 2]
                    reply = bytes([255, 252 if command in (251, 252) else 254, option])
                    try:
                        self.sock.sendall(reply)
                    except OSError:
                        pass
                    del self.buffer[i:i + 3]
                    continue
                if command == 250:  # SB ... IAC SE
                    end = self.buffer.find(bytes([255, 240]), i)
                    if end < 0:
                        break
                    del self.buffer[i:end + 2]
                    continue
                if command == 255:  # 转义的字面 255
                    i += 2
                    continue
                del self.buffer[i:i + 2]


def persist_telnet(host: str, mac: str, username: str, password: str | None = None) -> None:
    """登录 Telnet，用 cfg_cmd 把两个 TR-069 开关写成 1 并回读校验（持久化）。"""
    if not password:
        # 出厂默认口令 = 固定前缀 + MAC 末 6 位
        password = "FH-nE7jA%5m" + mac[-6:]
    session = TelnetSession(host, 23)
    try:
        session.read_until(b"Login:")
        session.write_line(username)
        session.read_until(b"Password:")
        session.write_line(password)
        session.read_until(b"$")
        for path in TELNET_PATHS:
            session.write_line("cfg_cmd set " + path + " 1")
            if b"set success!" not in session.read_until(b"$"):
                raise ToolError("持久化写入失败: " + path)
            session.write_line("cfg_cmd get " + path)
            if b"value=1" not in session.read_until(b"$"):
                raise ToolError("持久化回读失败: " + path)
        session.write_line("exit")
    finally:
        session.close()


def wait_for_telnet(host: str) -> None:
    """接口返回成功后，轮询 23 端口最多 12 次（每次 1s）等 Telnet 握手。"""
    for _ in range(12):
        try:
            with socket.create_connection((host, 23), timeout=2) as sock:
                sock.settimeout(2)
                if sock.recv(32):
                    return
        except OSError:
            pass
        time.sleep(1)
    raise ToolError("接口返回成功，但 23 端口未出现 Telnet 握手")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HG5585F 一键开启并持久化 Telnet")
    parser.add_argument("--host", default="192.168.1.1", help="光猫 LAN 地址")
    parser.add_argument("--web-port", type=int, default=8080, help="管理页端口")
    parser.add_argument("--probe", action="store_true", help="只读验证协议，不修改设备")
    parser.add_argument("--runtime-only", action="store_true",
                        help="只开启本次运行，不登录 Telnet 写入配置")
    parser.add_argument("--telnet-user", default="telnetadmin")
    parser.add_argument("--telnet-password", default=None,
                        help="自定义 Telnet 密码（不建议在命令行里传）")
    parser.add_argument("--telnet-password-stdin", action="store_true",
                        help="从标准输入读取自定义 Telnet 密码")
    return parser


def run(args: argparse.Namespace) -> int:
    host = str(ipaddress.ip_address(args.host))
    if not 1 <= args.web_port <= 65535:
        raise ToolError("管理端口超出范围")
    source = local_ip_for(host, args.web_port)
    # 只校验"本机源地址与目标同 /24"，不做任何网段遍历/扫描
    if ipaddress.ip_address(source) not in ipaddress.ip_network(f"{host}/24", strict=False):
        raise ToolError(f"目标不在当前直连 LAN；本机源地址为 {source}")
    base = f"http://{host}:{args.web_port}"

    # 1) 从 Web 后台无鉴权接口读设备 MAC（AES 密钥的唯一输入）
    info = json.loads(http_bytes(base + "/cgi-bin/ajax?ajaxmethod=web_get_brmad"))
    mac = info.get("brmad", "")
    if not re.fullmatch("[0-9A-F]{12}", mac):
        raise ToolError("无法读取有效的设备 MAC")
    key, iv = derive_key_iv(mac)

    # 2) 版本闸门：只认 HG5585F-CT V2 的 V4.2.0 / 24FHW45000
    device = tool_call(base, key, iv, "GetDevInfo")
    hw = device.get("hardwareversion")
    sw = device.get("softwareversion")
    if (hw, sw) != (EXPECTED_HARDWARE, EXPECTED_SOFTWARE):
        raise ToolError(f"设备版本与已验证目标不符：硬件 {hw}，软件 {sw}")
    print(f"设备验证通过：硬件 {hw}，软件 {sw}")

    if args.probe:
        print("只读探测完成，未修改设备。")
        return 0

    # 3) 运行时开 Telnet
    tool_call(base, key, iv, "TelnetEnable", telnet="1")
    wait_for_telnet(host)
    print("Telnet 已开启，23 端口握手正常。")
    if args.runtime_only:
        print("当前为运行时开启；重启后需要再次运行。")
        return 0

    # 4) 登录 Telnet，cfg_cmd 写持久化开关
    custom_password = (sys.stdin.readline().rstrip("\r\n")
                       if args.telnet_password_stdin else args.telnet_password)
    persist_telnet(host, mac, args.telnet_user, custom_password)
    print("总开关和 LAN 开关已写入并回读为 1；此固件已验证重启后自动开启。")
    return 0


def ask(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [默认 {default}]：").strip()
    return answer or default


def wizard() -> argparse.Namespace:
    """Guide a double-click user through the few options that matter."""
    args = build_parser().parse_args([])
    print("=" * 52)  # 常量: 52 个 =
    print(" HG5585F CT V2版 · 一键开启 Telnet")
    print(f" 适用版本：硬件 {EXPECTED_HARDWARE} / 软件 {EXPECTED_SOFTWARE}")
    print("请先确认：电脑已用网线直连光猫 LAN 口，且能打开管理页面。")
    host = ask("光猫 LAN 地址", "192.168.1.1").replace("http://", "").rstrip("/")
    try:
        args.host = str(ipaddress.ip_address(host))
    except ValueError:
        print("  地址格式不对，请输入形如 192.168.1.1 的 IP。")
    port = ask("管理页端口", "8080")
    try:
        args.web_port = int(port)
        if not 1 <= args.web_port <= 65535:
            raise ValueError
    except ValueError:
        print("  端口需在 1~65535 之间。")
    mode = ask("执行方式（1=只读探测 / 2=仅本次生效 / 3=持久化）", "3")
    args.probe = mode == "1"
    args.runtime_only = mode == "2"
    user = ask("Telnet 用户名 [默认 " + args.telnet_user + "]：", args.telnet_user)
    args.telnet_user = user.strip() or args.telnet_user
    use_custom = input("是否使用自定义 Telnet 密码？[y/N]：").strip().lower()
    if use_custom == "y":
        args.telnet_password = getpass.getpass("密码（输入不回显）：")
    return args


def main() -> int:
    set_console_title(WINDOW_TITLE)
    if len(sys.argv) > 1:
        code = run(build_parser().parse_args())
        print_contact()
        return code
    try:
        args = wizard()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        return 130
    print()
    try:
        input("确认无误后按回车键开始，Ctrl+C 可随时中止...")
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        return 130
    print()
    code = run(args)
    print()
    print_contact()
    press_any_key()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
