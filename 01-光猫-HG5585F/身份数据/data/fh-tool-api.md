# /fh_tool/api 私有维护接口 · 烽火 HG5585F 实测

> 恩山原帖：<https://www.right.com.cn/forum/forum.php?mod=viewthread&tid=8491420>
> 作者 Enceka（2026-09-30），附件 `HG5585F-CT-Telnet.zip`，验证目标为 **CT 版 V4.2.0 / 24FHW45000**
> 本文件为**在 HG5585F 联通 CU（WKE2.094.906 / V03.00.M0000）上的实测复现**，与原帖有出入处已标注。

## 与原帖的差异

| 项 | 原帖（CT 版） | 本机实测（CU 版） |
|---|---|---|
| 接口端口 | `192.168.1.1:8080` | **`http://192.168.1.1/`（80）**，8080 根本不开 |
| 固件 | V4.2.0 / 24FHW45000 | WKE2.094.906 / V03.00.M0000（build 2025-10-06） |
| 持久化命令 | `cfg_cmd set ...X_CT-COM_ServiceManage.TelnetEnable 1` | **无效**：`X_CT-COM_*` 是中国电信 TR-069 私有节点，本机 `GetParamVal failed, error code = -1` |
| `X_FH_TelnetForceOffTime` | 文档称 86400（24h 强制关） | **节点存在但值为空** → 大概率未启用 |
| `web_get_brmad` | 用来取 MAC | 80 端口返回 **403**（需登录态）；改用机身标签 MAC 绕过 |
| `info4` | 未说明 | `yvVMNy!iNcvTHthD`，开关前后**不变** → 不是 Telnet 口令 |
| Telnet 登录 | `telnetadmin` / 固定前缀+MAC 后 6 位 | **`admin` / `Fh@163280`**（MAC 末六位，原样不加 1） |

原帖 4# 楼说"不适用最新款设备"——**对读接口不成立**，2025-10 构建的固件上 `GetDevInfo` 仍返回 `result:0`。

## 报文格式（已验证）

```
① h   = sha256(MAC_ascii).hexdigest()          # 64 个小写 hex
② key = ''.join(h[2i+2] for i in range(16))     # 16 个 ASCII 字节，不是 hex 解码成 8 字节
   iv  = ''.join(h[3i+3] for i in range(16))     # 16 个 ASCII 字节
③ 明文 = 紧凑 UTF-8 JSON（separators=(',',':')）
④ 密文 = AES-128-CBC + PKCS#7
⑤ body = base64(密文)
⑥ POST http://<ONT>/fh_tool/api   Content-Type: text/plain
⑦ 响应：base64 解码 → AES-CBC 解密 → JSON → 检查 result == 0
```

本机实测值（MAC = `D069FF163280`，12 位无冒号大写）：

```
key = defb7190b3a328c8
iv  = cff1cb634c1f5616
```

## 已验证的调用

| func | 明文 | 用途 | 结果 |
|---|---|---|---|
| `GetDevInfo` | `{"index":"1","func":"GetDevInfo"}` | 只读，回读版本/serialnum/port_num | ✅ `result:0` |
| `GetTelnetInfo` | `{"index":"1","func":"GetTelnetInfo"}` | 只读，Telnet 状态 | ✅ `result:0` |
| `TelnetEnable` | `{"index":"1","func":"TelnetEnable","telnet":"1"}` | **写**，开 TCP/23 | ✅ `result:0` 且握手 `\xff\xfd\x01\xff\xfd\x21\xff\xfb\x01\xff\xfb\x03` |

原帖强调「API 成功码不足以证明端口已开」——本机也做了实际连接验证，第一次探测就出现标准 Telnet 协商字节。

## 安全说明

AES 密钥完全由设备 MAC 派生，而 MAC 是公开信息 → **这只是报文编码，不是身份认证**。
HTTP 与 Telnet 均无 TLS。**只在自己管理的局域网内使用，不要把 8080/23 暴露到公网。**

## 工具

- `tools/fhtool_probe.py` —— 只读探测（GetDevInfo / GetTelnetInfo），不发写方法
- `tools/fhtool_telnet.py` —— 发 TelnetEnable(1) + 验 TCP/23 + 读回 TelnetInfo